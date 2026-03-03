"""
Task execution engine for Auto Task Runner v3.0.

Handles:
  - PTY-based subprocess execution (preserves colors)
  - Fallback to PIPE mode if PTY fails
  - Real-time output streaming + log file capture
  - Heartbeat thread for status updates + terminal title
  - Signal handling (CTRL+C graceful / double-CTRL+C force)
  - State persistence after every task
  - Per-task tool/model configuration
"""

import argparse
import atexit
import contextlib
import errno
import json
import logging
import os
import random
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import MAX_EXECUTION_SECONDS, PROXY_ENV_KEYS, ToolConfig, get_tool_config
from .display import (
    SPINNER_FRAMES,
    ExecutionTracker,
    console,
    is_daemon_mode,
    reset_terminal_title,
    set_terminal_title,
    show_all_done,
    show_available_models,
    show_banner,
    show_dry_run_skip,
    show_error,
    show_force_exit,
    show_heartbeat,
    show_info,
    show_interrupt,
    show_progress_bar,
    show_summary,
    show_task_cmd,
    show_task_list,
    show_task_prompt_info,
    show_task_result,
    show_task_running,
    show_task_skip,
    show_task_start,
    show_tool_not_found,
    show_warning,
)
from .notify import (
    build_batch_complete_message,
    build_interrupt_message,
    build_task_complete_message,
    build_task_failure_message,
    create_notifier,
    send_notification_safe,
)
from .renderer import render_prompt
from .state import find_start_index, get_task_stats, load_plan, save_plan

logger = logging.getLogger(__name__)

# Any AI CLI execution completing in under this threshold is treated as a
# failure (the tool almost certainly did not actually process the task).
MIN_EXECUTION_SECONDS = 10


# ─── Delay Range Parser ─────────────────────────────────────────


def parse_delay_range(value: str | None) -> tuple[int, int]:
    """Parse a ``--delay`` CLI value into a (min, max) seconds tuple.

    Accepted formats:
      - ``None``      → ``(60, 120)``  (default)
      - ``"0"``       → ``(0, 0)``     (disabled)
      - ``"30"``      → ``(30, 30)``   (fixed delay)
      - ``"60-120"``  → ``(60, 120)``  (random range)
    """
    if value is None:
        return (60, 120)

    value = value.strip()
    if value == "0":
        return (0, 0)

    if "-" in value:
        parts = value.split("-", 1)
        try:
            lo, hi = int(parts[0]), int(parts[1])
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid delay range '{value}'. Use '60-120', '30', or '0'."
            ) from None
        if lo < 0 or hi < 0:
            raise argparse.ArgumentTypeError("Delay values must be non-negative.")
        return (min(lo, hi), max(lo, hi))

    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid delay value '{value}'. Use '60-120', '30', or '0'."
        ) from None
    if n < 0:
        raise argparse.ArgumentTypeError("Delay value must be non-negative.")
    return (n, n)


# ─── Log Sanitization Patterns ───────────────────────────────────

# Regex to strip ANSI escape sequences (SGR, OSC, DEC private modes)
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"
    r"|\x1b\][^\x07]*\x07"
    r"|\x1b\[\?[0-9;]*[a-zA-Z]"
    r"|\r"  # also strip carriage returns from PTY output
)

# ── Block-based noise detection ──
# Transient network errors from CLI tools (kimi, etc.) appear as multi-line blocks:
#   Error: peer closed connection ... (incomplete chunked read)
#   <html>
#   <head><title>503 Service Temporarily Unavailable</title></head>
#   ...
#   </html>
# We detect the START of such a block and skip everything until the END.

_NOISE_BLOCK_START = re.compile(
    r"Error:\s*peer closed connection"
    r"|Error:\s*incomplete chunked read"
    r"|^\s*<html>\s*$",
    re.IGNORECASE,
)
_NOISE_BLOCK_END = re.compile(r"</html>", re.IGNORECASE)

# Single-line noise (not part of a block)
_NOISE_LINE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*Error:\s*peer closed connection", re.IGNORECASE),
    re.compile(r"^\s*\(incomplete chunked read\)\s*$", re.IGNORECASE),
]


def _is_noise_line(line: str) -> bool:
    """Check if a single line is standalone noise (outside a block)."""
    stripped = line.strip()
    if not stripped:
        return False
    return any(p.search(stripped) for p in _NOISE_LINE_PATTERNS)


def _sanitize_text(raw_text: str) -> str:
    """Strip ANSI codes and filter transient network error blocks from raw log text.

    Uses a state machine: when a noise-block-start line is seen, all lines are
    skipped until the corresponding noise-block-end (</html>).  Consecutive
    blank lines are collapsed.
    """
    text = _ANSI_RE.sub("", raw_text)
    lines = text.splitlines(keepends=True)
    clean: list[str] = []
    in_noise = False
    prev_blank = False

    for line in lines:
        stripped = line.strip()

        # ── inside a noise block → skip until end ──
        if in_noise:
            if _NOISE_BLOCK_END.search(stripped):
                in_noise = False
            continue

        # ── detect start of a new noise block ──
        if _NOISE_BLOCK_START.search(stripped):
            in_noise = True
            continue

        # ── standalone noise line ──
        if _is_noise_line(stripped):
            continue

        # ── collapse consecutive blank lines ──
        is_blank = not stripped
        if is_blank and prev_blank:
            continue
        prev_blank = is_blank

        clean.append(line)

    return "".join(clean)


def _extract_output_tail(clean_text: str, max_lines: int = 30) -> str:
    """Extract the last *max_lines* non-blank lines from sanitized text.

    This gives users a quick view of what the AI CLI actually produced.
    """
    lines = [line for line in clean_text.splitlines() if line.strip()]
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def _fmt_elapsed_short(elapsed: float) -> str:
    """Format elapsed seconds into a compact human-readable string."""
    total_secs = int(elapsed)
    hours, remainder = divmod(total_secs, 3600)
    mins, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    elif mins > 0:
        return f"{mins}m {secs:02d}s"
    else:
        return f"{secs}s"


class TaskExecutor:
    """
    Main execution engine — manages the full lifecycle of batch task execution.

    Supports both v3 (project-based) and legacy (plan-based) modes.
    """

    def __init__(self, **kwargs):
        """
        Initialize the executor.

        v3 mode kwargs:
            project_config, task_set, scheduled_tasks, run_context,
            tool_config, model, use_proxy, dry_run, heartbeat_interval,
            workspace, template_override, git_safety

        Legacy mode kwargs:
            args (argparse.Namespace from legacy parser)
        """
        if "args" in kwargs:
            self._init_legacy(kwargs["args"])
        else:
            self._init_v3(**kwargs)

        # Runtime state (shared)
        self.current_process: subprocess.Popen | None = None
        self.interrupted: bool = False
        self._timed_out: bool = False
        self._ctrl_c_count: int = 0
        self._task_needs_proxy: bool | None = None  # Per-task proxy override

        # Heartbeat thread control
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_start: float = 0
        self._heartbeat_task_no: str = ""

        # Results tracking (v3)
        self._results = {"succeeded": 0, "failed": 0, "skipped": 0, "attempted": 0}
        self._task_results: list[dict] = []

        # Live execution tracker (v3)
        self._tracker: ExecutionTracker | None = None

    def _init_v3(self, **kwargs):
        """Initialize for v3 project-based mode."""
        self._mode = "v3"

        from .project import ProjectConfig
        from .runtime import RunContext
        from .task_set import TaskSet

        self.project_config: ProjectConfig = kwargs["project_config"]
        self.task_set: TaskSet = kwargs["task_set"]
        self.scheduled_tasks = kwargs["scheduled_tasks"]
        self.run_context: RunContext = kwargs["run_context"]
        self.tool_config: ToolConfig = kwargs["tool_config"]
        self.model: str | None = kwargs.get("model")
        self.use_proxy: bool = kwargs.get("use_proxy", True)
        self.proxy_mode: str | None = kwargs.get("proxy_mode")  # "on"/"off"/None
        self.cli_tool_override: bool = kwargs.get("cli_tool_override", False)
        self.cli_model_override: bool = kwargs.get("cli_model_override", False)
        self.dry_run: bool = kwargs.get("dry_run", False)
        self.heartbeat_interval: int = kwargs.get("heartbeat_interval", 60)
        self.workspace: str = kwargs.get("workspace", "")
        self.template_override: str | None = kwargs.get("template_override")
        self.git_safety: bool = kwargs.get("git_safety", False)
        self.verbose: bool = kwargs.get("verbose", False)
        self.quiet: bool = kwargs.get("quiet", False)
        self.delay_range: tuple[int, int] = kwargs.get("delay_range", (60, 120))
        self.max_execution_seconds: int = kwargs.get("max_execution_seconds", MAX_EXECUTION_SECONDS)
        self.notify_enabled: bool | None = kwargs.get("notify_enabled")
        self.notify_each: bool = kwargs.get("notify_each", False)
        self.wecom_webhook: str | None = kwargs.get("wecom_webhook")

        self.work_dir = Path(self.workspace) if self.workspace else None

    def _init_legacy(self, args):
        """Initialize for legacy --plan mode."""
        self._mode = "legacy"
        self.args = args
        self.plan_path: Path = args.plan_path
        self.template_path: Path | None = args.template_path
        self.project_name: str = args.project
        self.tool_config = args.tool_config
        self.model: str | None = args.model  # type: ignore[no-redef]
        self.use_proxy: bool = args.use_proxy  # type: ignore[no-redef]
        self.dry_run: bool = args.dry_run  # type: ignore[no-redef]
        self.heartbeat_interval: int = args.heartbeat  # type: ignore[no-redef]

        self.work_dir: Path | None = args.work_dir_path  # type: ignore[no-redef]
        self.delay_range: tuple[int, int] = getattr(args, "delay_range", (60, 120))  # type: ignore[no-redef]
        self.max_execution_seconds: int = getattr(  # type: ignore[no-redef]
            args, "max_execution_seconds", MAX_EXECUTION_SECONDS
        )
        self.project_dir: Path | None = None
        self.tasks_dir: Path | None = None
        self.logs_dir: Path | None = None

    # ─── Results Access (v3) ─────────────────────────────────────

    def get_results(self) -> dict:
        return dict(self._results)

    def get_task_results(self) -> list[dict]:
        return list(self._task_results)

    # ─── Legacy Setup ────────────────────────────────────────────

    def _detect_work_dir(self) -> Path:
        """Auto-detect project root by searching for common markers."""
        markers = ["manage.py", "pyproject.toml", ".git", "Makefile", "package.json"]
        path = self.plan_path.parent

        while path != path.parent:
            if any((path / m).exists() for m in markers):
                return path
            path = path.parent

        return Path.cwd()

    def _setup_directories(self):
        """Create project output directories (legacy mode)."""
        if self.work_dir is None:
            self.work_dir = self._detect_work_dir()

        self.project_dir = self.plan_path.parent / self.project_name
        self.tasks_dir = self.project_dir / "tasks"
        self.logs_dir = self.project_dir / "logs"

        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_template(self, plan: dict) -> str | None:
        """Resolve and load the template content (legacy mode)."""
        if self.template_path:
            return self.template_path.read_text(encoding="utf-8")

        template_rel: str | None = plan.get("template")
        if template_rel:
            template_path = self.plan_path.parent / template_rel
            if template_path.exists():
                self.template_path = template_path
                return template_path.read_text(encoding="utf-8")
            else:
                show_warning(f"Template from plan not found: {template_path}")

        return None

    # ─── V3 Template Resolution ──────────────────────────────────

    def _resolve_template_v3(self, task) -> str | None:
        """Resolve template for a v3 task. Per-task > override > task_set > default."""
        from .project import get_project_dir

        project_dir = get_project_dir(self.project_config.project)

        # 1. Per-task template override
        if task.prompt:
            tpl_path = project_dir / str(task.prompt)
            if tpl_path.exists():
                return tpl_path.read_text(encoding="utf-8")

        # 2. CLI override
        if self.template_override:
            tpl_path = Path(self.template_override)
            if not tpl_path.is_absolute():
                tpl_path = project_dir / tpl_path
            if tpl_path.exists():
                return tpl_path.read_text(encoding="utf-8")

        # 3. Task set default template
        if self.task_set.template:
            tpl_path = project_dir / self.task_set.template
            if tpl_path.exists():
                return tpl_path.read_text(encoding="utf-8")

        # 4. Project default template
        default_tpl = project_dir / "templates" / "__init__.md"
        if default_tpl.exists():
            return default_tpl.read_text(encoding="utf-8")

        return None

    # ─── Shared Infrastructure ───────────────────────────────────

    def _check_tool_available(self, tool_name: str | None = None) -> bool:
        """Verify the CLI tool binary exists in PATH."""
        name = tool_name or self.tool_config.name
        if shutil.which(name) is None:
            show_tool_not_found(name)
            return False
        return True

    def _setup_signals(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        # NOTE: Python signals are always delivered to the main thread, and
        # the GIL guarantees that simple integer increments are atomic.
        # We keep this handler minimal (no I/O beyond the show_* helpers
        # which only write to sys.stderr) to stay within the constraints of
        # signal-safety.
        self._ctrl_c_count += 1
        self.interrupted = True

        if self._ctrl_c_count == 1:
            show_interrupt()
            self._kill_child()
        elif self._ctrl_c_count >= 2:
            show_force_exit()
            self._force_kill()
            os._exit(130)

    def _kill_child(self):
        proc = self.current_process
        if not proc or proc.poll() is not None:
            return

        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            return

        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return

        for _ in range(50):
            if proc.poll() is not None:
                return
            time.sleep(0.1)

        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(pgid, signal.SIGKILL)

    def _force_kill(self):
        proc = self.current_process
        if proc and proc.poll() is None:
            with contextlib.suppress(Exception):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)

    def _timeout_kill(self) -> None:
        """Kill the current child process due to timeout.

        Sends SIGTERM first, waits up to 5 seconds, then escalates to SIGKILL.
        """
        proc = self.current_process
        if not proc or proc.poll() is not None:
            return

        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            return

        show_warning(
            f"Task exceeded timeout ({self.max_execution_seconds}s / "
            f"{self.max_execution_seconds // 60}min) — sending SIGTERM …"
        )

        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return

        # Wait up to 5 seconds for graceful exit
        for _ in range(50):
            if proc.poll() is not None:
                return
            time.sleep(0.1)

        show_warning("Process did not exit after SIGTERM, sending SIGKILL …")
        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(pgid, signal.SIGKILL)

    def _make_env(self) -> dict:
        env = os.environ.copy()

        # Resolve effective proxy need:
        #   explicit --proxy/--no-proxy always wins,
        #   otherwise per-task tool's needs_proxy,
        #   fallback to global self.use_proxy.
        if getattr(self, "proxy_mode", None) == "on":
            needs_proxy = True
        elif getattr(self, "proxy_mode", None) == "off":
            needs_proxy = False
        elif self._task_needs_proxy is not None:
            needs_proxy = self._task_needs_proxy
        else:
            needs_proxy = self.use_proxy

        if not needs_proxy:
            keys_to_remove = [
                k
                for k in env
                if k in PROXY_ENV_KEYS or k.lower() in [v.lower() for v in PROXY_ENV_KEYS]
            ]
            for key in keys_to_remove:
                del env[key]
        return env

    def _build_command(
        self, task_file: Path, tool_config: ToolConfig | None = None, model: str | None = None
    ) -> str:
        tc = tool_config or self.tool_config
        m = model or self.model
        cmd = tc.cmd_template
        cmd = cmd.replace("{task_file}", str(task_file))
        if m:
            cmd = cmd.replace("{model}", m)
        return cmd

    # ─── Inter-task Delay (Anti-Rate-Limit) ───────────────────

    def _inter_task_delay(self, current_idx: int, remaining_tasks, *, last_success: bool = True):
        """Wait a random duration between tasks to look more human.

        Skips delay if:
          - delay_range is (0, 0)  (explicitly disabled)
          - this is the last task
          - execution was interrupted
          - dry-run mode
          - previous task failed (no point waiting — didn't hit the AI service meaningfully)
        """
        if self.dry_run or self.interrupted:
            return
        if not last_success:
            return
        lo, hi = self.delay_range
        if lo == 0 and hi == 0:
            return

        # Don't delay after the last task
        has_more = False
        if isinstance(remaining_tasks, list) and len(remaining_tasks) > 0:
            has_more = True
        elif hasattr(remaining_tasks, "__len__"):
            has_more = current_idx + 1 < len(remaining_tasks)
        if not has_more:
            return

        delay = random.randint(lo, max(lo, hi))

        # Peek at next task_no for display
        next_label = ""
        try:
            if isinstance(remaining_tasks, list) and len(remaining_tasks) > 0:
                nxt = remaining_tasks[0]
                next_label = nxt.task_no if hasattr(nxt, "task_no") else nxt.get("task_no", "")
        except (IndexError, TypeError, AttributeError):
            pass

        # Countdown loop — checks self.interrupted each second so CTRL+C
        # breaks out immediately without needing a double-press.
        import sys as _sys

        label = f"next: {next_label}" if next_label else "next task"
        daemon = is_daemon_mode()

        # In daemon mode, print one line and sleep — \r carriage returns
        # produce garbled output in supervisor log files.
        if daemon:
            _sys.stdout.write(
                f"  \u23f3 Waiting {delay}s before {label} (anti-rate-limit)...\n"
            )
            _sys.stdout.flush()
            for remaining in range(delay, 0, -1):
                if self.interrupted:
                    _sys.stdout.write(f"  \u23f3 Delay interrupted.\n")
                    _sys.stdout.flush()
                    return
                time.sleep(1)
            _sys.stdout.write(f"  \u23f3 Delay complete, resuming execution.\n")
            _sys.stdout.flush()
        else:
            for remaining in range(delay, 0, -1):
                if self.interrupted:
                    _sys.stdout.write(f"\r  \u23f3 Delay interrupted.{' ' * 50}\n")
                    _sys.stdout.flush()
                    return
                _sys.stdout.write(
                    f"\r  \u23f3 Waiting {remaining}s before {label} (anti-rate-limit)..."
                )
                _sys.stdout.flush()
                time.sleep(1)

            _sys.stdout.write(f"\r  \u23f3 Delay complete, resuming execution.{' ' * 40}\n")
            _sys.stdout.flush()

    # ─── Heartbeat ───────────────────────────────────────────────

    def _start_heartbeat(self, task_no: str):
        self._stop_heartbeat.clear()
        self._heartbeat_start = time.time()
        self._heartbeat_task_no = task_no
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_fn(self):
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=3)
            self._heartbeat_thread = None

    def _heartbeat_loop(self):
        tick = 0
        while not self._stop_heartbeat.is_set():
            self._stop_heartbeat.wait(1.0)
            if self._stop_heartbeat.is_set():
                break

            tick += 1
            elapsed = time.time() - self._heartbeat_start
            mins, secs = divmod(int(elapsed), 60)
            hours, mins_r = divmod(mins, 60)

            if hours > 0:
                time_str = f"{hours}h{mins_r:02d}m{secs:02d}s"
            else:
                time_str = f"{mins}m{secs:02d}s"

            spinner = SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]

            set_terminal_title(
                f"{spinner} {time_str} | Task {self._heartbeat_task_no} | Auto Task Runner"
            )

            if tick % self.heartbeat_interval == 0:
                show_heartbeat(self._heartbeat_task_no, elapsed, tick)

    # ─── Task Execution (PTY / PIPE) ────────────────────────────

    def _execute_with_pty(self, cmd: str, log_path: Path) -> tuple[int, float]:
        import pty as pty_module

        master_fd, slave_fd = pty_module.openpty()

        try:
            import fcntl
            import struct
            import termios

            size = struct.pack("HHHH", 50, 120, 0, 0)
            with contextlib.suppress(OSError):
                size = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, size)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, size)
        except (ImportError, OSError):
            pass

        self.current_process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=slave_fd,
            stderr=slave_fd,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            close_fds=True,
            env=self._make_env(),
            cwd=str(self.work_dir) if self.work_dir else None,
        )
        os.close(slave_fd)

        start_time = time.time()
        deadline = start_time + self.max_execution_seconds

        with open(log_path, "wb") as log_file:
            while True:
                if self.interrupted:
                    break

                # ── Timeout check ──
                if time.time() >= deadline:
                    self._timed_out = True
                    self._timeout_kill()
                    break

                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.5)
                except (ValueError, OSError):
                    break

                if ready:
                    try:
                        data = os.read(master_fd, 8192)
                        if not data:
                            break
                        try:
                            os.write(sys.stdout.fileno(), data)
                        except (BrokenPipeError, OSError):
                            pass  # stdout pipe closed (supervisor restart, etc.)
                        log_file.write(data)
                        log_file.flush()
                    except OSError as e:
                        if e.errno == errno.EIO:
                            break
                        raise

                if self.current_process.poll() is not None:
                    self._drain_fd(master_fd, log_file)
                    break

        with contextlib.suppress(OSError):
            os.close(master_fd)

        try:
            self.current_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._kill_child()

        return_code = (
            self.current_process.returncode
            if self.current_process and self.current_process.returncode is not None
            else -1
        )
        elapsed = time.time() - start_time
        self.current_process = None

        return return_code, elapsed

    def _execute_with_pipe(self, cmd: str, log_path: Path) -> tuple[int, float]:
        self.current_process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            env=self._make_env(),
            cwd=str(self.work_dir) if self.work_dir else None,
        )

        start_time = time.time()
        deadline = start_time + self.max_execution_seconds

        with open(log_path, "wb") as log_file:
            stdout = self.current_process.stdout
            assert stdout is not None
            for line in iter(stdout.readline, b""):
                if self.interrupted:
                    break
                # ── Timeout check ──
                if time.time() >= deadline:
                    self._timed_out = True
                    self._timeout_kill()
                    break
                try:
                    os.write(sys.stdout.fileno(), line)
                except (BrokenPipeError, OSError):
                    pass  # stdout pipe closed (supervisor restart, etc.)
                log_file.write(line)
                log_file.flush()

        try:
            self.current_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._kill_child()

        return_code = (
            self.current_process.returncode
            if self.current_process and self.current_process.returncode is not None
            else -1
        )
        elapsed = time.time() - start_time
        self.current_process = None

        return return_code, elapsed

    def execute_task(self, cmd: str, log_path: Path) -> tuple[int, float]:
        self._timed_out = False

        # In daemon mode, skip PTY entirely — PTY relies on a controlling
        # terminal that doesn't exist under supervisord / systemd / nohup.
        # PIPE mode is fully sufficient and avoids EIO / TIOCGWINSZ errors.
        if is_daemon_mode():
            try:
                return self._execute_with_pipe(cmd, log_path)
            finally:
                self._ensure_child_cleaned_up()

        try:
            return self._execute_with_pty(cmd, log_path)
        except Exception as e:
            logger.info("PTY mode failed (%s), falling back to PIPE mode", e)
            show_warning(
                f"PTY mode unavailable ({type(e).__name__}: {e}), "
                f"falling back to PIPE mode. "
                f"Output may lose colours / formatting."
            )
            return self._execute_with_pipe(cmd, log_path)
        finally:
            # Issue #5b: unified subprocess cleanup — ensure no zombie remains
            self._ensure_child_cleaned_up()

    @staticmethod
    def _drain_fd(fd: int, log_file):
        for _ in range(100):
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if not ready:
                    break
                data = os.read(fd, 8192)
                if not data:
                    break
                try:
                    os.write(sys.stdout.fileno(), data)
                except (BrokenPipeError, OSError):
                    pass
                log_file.write(data)
                log_file.flush()
            except OSError:
                break

    def _ensure_child_cleaned_up(self) -> None:
        """Final safety net: make sure the child process is dead and reaped.

        Called from the ``finally`` block of ``execute_task()`` to handle edge
        cases such as PTY EOF arriving before the process exits, an exception
        during PIPE reading, or any other unexpected early return.
        """
        proc = self.current_process
        if proc is None:
            return

        if proc.poll() is None:
            # Still running — send SIGTERM → wait 5s → SIGKILL
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            else:
                for _ in range(50):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if proc.poll() is None:
                    with contextlib.suppress(ProcessLookupError, OSError):
                        os.killpg(pgid, signal.SIGKILL)
            # Final reap
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)

        self.current_process = None

    # ─── Log Sanitization ────────────────────────────────────────

    @staticmethod
    def _sanitize_log(log_path: Path) -> tuple[Path | None, str]:
        """
        Post-process a raw log file:
          1. Strip ANSI escape sequences
          2. Remove transient network error blocks (503 / peer closed / nginx)
          3. Collapse consecutive blank lines
        Writes result to <name>.clean.log alongside the original raw log.

        Returns (clean_log_path, clean_text).  On error returns (None, "").
        """
        try:
            raw = log_path.read_bytes()
        except OSError:
            return None, ""

        raw_text = raw.decode("utf-8", errors="replace")
        clean_text = _sanitize_text(raw_text)

        clean_path = log_path.with_suffix(".clean.log")
        try:
            clean_path.write_text(clean_text, encoding="utf-8")
        except OSError:
            return None, clean_text

        return clean_path, clean_text

    # ─── Git Safety ──────────────────────────────────────────────

    def _git_safety_check(self):
        """Check workspace git status and create safety tag."""
        if not self.work_dir or not (self.work_dir / ".git").exists():
            show_warning("Git safety: not a git repository, skipping")
            return

        import subprocess as sp

        # Check for uncommitted changes
        result = sp.run(
            ["git", "status", "--porcelain"],
            cwd=str(self.work_dir),
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            show_warning(
                f"Git safety: workspace has uncommitted changes ({len(result.stdout.strip().splitlines())} files)"
            )

        # Create safety tag
        tag_name = f"auto-run-task/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        sp.run(
            ["git", "tag", tag_name],
            cwd=str(self.work_dir),
            capture_output=True,
        )
        show_info(f"Git safety: created tag '{tag_name}'")

    # ─── Main Entry Point ────────────────────────────────────────

    def run(self) -> int:
        """Main entry point — dispatch to v3 or legacy mode."""
        if self._mode == "v3":
            return self._run_v3()
        else:
            return self._run_legacy()

    # ─── V3 Mode ─────────────────────────────────────────────────

    def _run_v3(self) -> int:
        """Execute tasks in v3 project-based mode."""
        from .project import get_project_dir
        from .runtime import save_live_status
        from .task_set import save_task_set

        self._setup_signals()

        # ── Initialize notifier ──
        notify_enabled = self.notify_enabled
        if notify_enabled is None:
            notify_enabled = True  # default on when webhook is configured
        notifier = create_notifier(
            webhook_url=self.wecom_webhook,
            enabled=notify_enabled if notify_enabled is not False else False,
        )

        project_dir = get_project_dir(self.project_config.project)
        tasks = self.scheduled_tasks
        total = len(tasks)

        if total == 0:
            show_all_done()
            return 0

        # Git safety check
        if self.git_safety:
            self._git_safety_check()

        # Check tool availability (skip for dry-run)
        if not self.dry_run and not self._check_tool_available():
            return 1

        # Build stats for banner
        all_tasks = self.task_set.tasks
        done_count = sum(1 for t in all_tasks if t.status == "completed")
        remaining = len(all_tasks) - done_count

        # Show banner
        if not self.quiet:
            from .display import show_banner_v3

            show_banner_v3(
                project=self.project_config.project,
                task_set=self.task_set.name,
                tool=self.tool_config.name,
                model=self.model,
                workspace=str(self.work_dir or self.workspace),
                run_id=self.run_context.run_id,
                total=len(all_tasks),
                done=done_count,
                remaining=remaining,
                to_execute=total,
                use_proxy=self.use_proxy,
            )

        atexit.register(reset_terminal_title)

        # ── Create execution tracker ──
        if not self.quiet:
            self._tracker = ExecutionTracker(
                total_all=len(all_tasks),
                total_to_execute=total,
                project=self.project_config.project,
                task_set=self.task_set.name,
            )

        # Execute tasks
        succeeded = 0
        failed = 0
        skipped = 0
        run_start = time.time()

        for idx, task in enumerate(tasks):
            if self.interrupted:
                break

            task_no = task.task_no

            # Skip completed
            if task.status == "completed":
                show_task_skip(task_no)
                skipped += 1
                if self._tracker:
                    self._tracker.record_skip(task_no)
                continue

            # Show task info
            show_task_start(idx, total, task)

            # Resolve template
            template = self._resolve_template_v3(task)
            if template:
                prompt_content = render_prompt(template, task._raw)
            else:
                prompt_content = json.dumps(task._raw, ensure_ascii=False, indent=2)

            # Write prompt file
            prompt_path = self.run_context.get_prompt_path(task_no)
            prompt_path.write_text(prompt_content, encoding="utf-8")

            rel_prompt = str(prompt_path.relative_to(project_dir))
            show_task_prompt_info(rel_prompt)

            if self.dry_run:
                show_dry_run_skip(task_no)
                continue

            # Resolve per-task tool/model
            # CLI --tool/--model always wins; per-task JSON only applies
            # when the user did NOT explicitly specify on the command line.
            task_tool_config = self.tool_config
            task_model = self.model
            if task.cli.tool and not self.cli_tool_override:
                try:
                    task_tool_config = get_tool_config(task.cli.tool)
                except KeyError:
                    show_warning(
                        f"Unknown tool '{task.cli.tool}' for task {task_no}, using default"
                    )
            if task.cli.model and not self.cli_model_override:
                task_model = task.cli.model

            # Check task-specific tool availability
            if task_tool_config.name != self.tool_config.name and not self._check_tool_available(
                task_tool_config.name
            ):
                task.status = "failed"
                save_task_set(self.task_set, project_dir)
                failed += 1
                continue

            # Build command
            cmd = self._build_command(prompt_path, task_tool_config, task_model)
            show_task_cmd(cmd)

            # Update status
            task.status = "in-progress"
            save_task_set(self.task_set, project_dir)

            # Write live status for external monitoring
            save_live_status(
                self.run_context, task_no, dict(self._results), list(self._task_results)
            )

            # Log file
            log_path = self.run_context.get_log_path(task_no)

            # Execute
            show_task_running()
            self._task_needs_proxy = task_tool_config.needs_proxy
            self._start_heartbeat(task_no)
            if self._tracker:
                self._tracker.set_current_task(task_no, task.task_name)
                self._tracker.start()

            return_code, elapsed = self.execute_task(cmd, log_path)

            self._task_needs_proxy = None
            self._stop_heartbeat_fn()
            if self._tracker:
                self._tracker.stop()

            if self.interrupted:
                task.status = "interrupted"
                save_task_set(self.task_set, project_dir)

                # Send interrupt notification
                completed_count = sum(1 for t in all_tasks if t.status == "completed")
                send_notification_safe(
                    notifier,
                    build_interrupt_message(
                        project=self.project_config.project,
                        task_set=self.task_set.name,
                        current_task_no=task_no,
                        current_task_name=task.task_name,
                        completed=completed_count,
                        total=len(all_tasks),
                    ),
                )
                break

            # ── Timeout handling ──
            if self._timed_out:
                show_warning(
                    f"Task {task_no} timed out after "
                    f"{self.max_execution_seconds}s "
                    f"({self.max_execution_seconds // 60}min) — marking as FAILED."
                )
                task.status = "failed"
                task.elapsed_seconds = round(elapsed, 1)
                task.last_run_at = datetime.now().isoformat()
                save_task_set(self.task_set, project_dir)
                failed += 1

                # Sanitize log even for timed-out tasks
                clean_log, clean_text = self._sanitize_log(log_path)
                output_tail = _extract_output_tail(clean_text)
                rel_log = str(log_path.relative_to(project_dir))
                if clean_log:
                    rel_log = str(clean_log.relative_to(project_dir))
                show_task_result(task_no, False, elapsed, rel_log, output_tail)

                if self._tracker:
                    self._tracker.record_result(task_no, task.task_name, False, elapsed)

                self._task_results.append(
                    {
                        "task_no": task_no,
                        "status": "failed",
                        "duration_seconds": round(elapsed, 1),
                        "return_code": return_code,
                        "failure_reason": "timeout",
                        "log_file": f"logs/{task_no.replace('/', '_').replace(chr(92), '_')}.log",
                    }
                )
                save_live_status(
                    self.run_context, None, dict(self._results), list(self._task_results)
                )

                # Send failure notification
                send_notification_safe(
                    notifier,
                    build_task_failure_message(
                        project=self.project_config.project,
                        task_set=self.task_set.name,
                        task_no=task_no,
                        task_name=task.task_name,
                        failure_reason=f"超时 ({self.max_execution_seconds // 60}min)",
                        elapsed=_fmt_elapsed_short(elapsed),
                        tool=task_tool_config.name,
                        model=task_model,
                        return_code=return_code,
                        output_tail=output_tail,
                        log_file=rel_log,
                    ),
                )

                # Continue to next task (don't delay — no point after a timeout)
                continue

            # Record result
            success = return_code == 0

            # Guard: AI CLI finishing in < MIN_EXECUTION_SECONDS is bogus
            if success and elapsed < MIN_EXECUTION_SECONDS:
                show_warning(
                    f"Task {task_no} completed in {elapsed:.1f}s "
                    f"(< {MIN_EXECUTION_SECONDS}s minimum) — marking as FAILED. "
                    f"The AI CLI likely did not process the task."
                )
                success = False

            if success:
                task.status = "completed"
                succeeded += 1
            else:
                task.status = "failed"
                failed += 1

            # Record timing on the task object
            task.elapsed_seconds = round(elapsed, 1)
            task.last_run_at = datetime.now().isoformat()

            save_task_set(self.task_set, project_dir)

            # Sanitize log (strip ANSI codes + noise)
            clean_log, clean_text = self._sanitize_log(log_path)
            output_tail = _extract_output_tail(clean_text)

            rel_log = str(log_path.relative_to(project_dir))
            if clean_log:
                rel_clean = str(clean_log.relative_to(project_dir))
                show_task_result(task_no, success, elapsed, rel_clean, output_tail)
            else:
                show_task_result(task_no, success, elapsed, rel_log, output_tail)
            notify_log_file = rel_clean if clean_log else rel_log

            # Record to tracker
            if self._tracker:
                self._tracker.record_result(task_no, task.task_name, success, elapsed)

            # Send notification on failure or (opt-in) on each task
            if not success:
                failure_reason = (
                    f"exit code {return_code}"
                    if elapsed >= MIN_EXECUTION_SECONDS
                    else f"执行过快 ({elapsed:.1f}s < {MIN_EXECUTION_SECONDS}s)"
                )
                send_notification_safe(
                    notifier,
                    build_task_failure_message(
                        project=self.project_config.project,
                        task_set=self.task_set.name,
                        task_no=task_no,
                        task_name=task.task_name,
                        failure_reason=failure_reason,
                        elapsed=_fmt_elapsed_short(elapsed),
                        tool=task_tool_config.name,
                        model=task_model,
                        return_code=return_code,
                        output_tail=output_tail,
                        log_file=notify_log_file,
                    ),
                )
            elif success and self.notify_each:
                next_task = next((t for t in tasks[idx + 1 :] if t.status != "completed"), None)
                next_tool_name: str | None = None
                next_model_name: str | None = None
                if next_task:
                    next_tool_name = self.tool_config.name
                    next_model_name = self.model
                    if next_task.cli.tool and not self.cli_tool_override:
                        next_tool_name = next_task.cli.tool
                    if next_task.cli.model and not self.cli_model_override:
                        next_model_name = next_task.cli.model

                send_notification_safe(
                    notifier,
                    build_task_complete_message(
                        project=self.project_config.project,
                        task_set=self.task_set.name,
                        task_no=task_no,
                        task_name=task.task_name,
                        elapsed=_fmt_elapsed_short(elapsed),
                        tool=task_tool_config.name,
                        model=task_model,
                        return_code=return_code,
                        progress_done=succeeded + failed,
                        progress_total=total,
                        output_tail=output_tail,
                        log_file=notify_log_file,
                        next_task_no=next_task.task_no if next_task else None,
                        next_task_name=next_task.task_name if next_task else None,
                        next_tool=next_tool_name,
                        next_model=next_model_name,
                    ),
                )

            # Track result
            self._task_results.append(
                {
                    "task_no": task_no,
                    "status": task.status,
                    "duration_seconds": round(elapsed, 1),
                    "return_code": return_code,
                    "log_file": f"logs/{task_no.replace('/', '_').replace(chr(92), '_')}.log",
                }
            )

            # Update live status after result
            save_live_status(self.run_context, None, dict(self._results), list(self._task_results))

            # Random delay between tasks (anti-rate-limit)
            self._inter_task_delay(idx, tasks[idx + 1 :], last_success=success)

        # Cleanup
        reset_terminal_title()

        total_elapsed = time.time() - run_start
        total_done = sum(1 for t in all_tasks if t.status == "completed")

        self._results = {
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "attempted": succeeded + failed,
        }

        show_summary(
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            total=len(all_tasks),
            total_done=total_done,
            total_elapsed=total_elapsed,
            interrupted=self.interrupted,
            task_results=self._task_results,
        )

        # ── Batch completion notification ──
        if notifier and (succeeded + failed) > 0:
            run_start_str = datetime.fromtimestamp(run_start).strftime("%H:%M:%S")
            run_end_str = datetime.now().strftime("%H:%M:%S")
            failed_task_details = [r for r in self._task_results if r.get("status") == "failed"]
            send_notification_safe(
                notifier,
                build_batch_complete_message(
                    project=self.project_config.project,
                    task_set=self.task_set.name,
                    start_time=run_start_str,
                    end_time=run_end_str,
                    duration=_fmt_elapsed_short(total_elapsed),
                    succeeded=succeeded,
                    failed=failed,
                    skipped=skipped,
                    total=len(all_tasks),
                    total_done=total_done,
                    interrupted=self.interrupted,
                    failed_tasks=failed_task_details,
                ),
            )

        return 0 if failed == 0 and not self.interrupted else 1

    # ─── Legacy Mode ─────────────────────────────────────────────

    def _run_legacy(self) -> int:
        """Execute the full task pipeline in legacy mode (v2 behavior)."""
        self._setup_signals()

        try:
            plan = load_plan(self.plan_path)
        except (json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            show_error(f"Failed to load plan: {e}")
            return 1

        tasks = plan.get("tasks", [])
        if not tasks:
            show_error("No tasks found in plan!")
            return 1

        if self.args.list_tasks:
            show_task_list(tasks)
            return 0

        if self.args.list_models:
            if self.tool_config.supports_model:
                show_available_models(
                    self.tool_config.name,
                    self.tool_config.models,
                    self.tool_config.default_model,
                )
            else:
                show_info(f"Tool '{self.tool_config.name}' does not support model selection.")
            return 0

        template = self._resolve_template(plan)
        if template is None and not self.dry_run:
            show_error("No template specified! Use --template or add 'template' key in plan JSON.")
            return 1

        if not self.dry_run and not self._check_tool_available():
            return 1

        self._setup_directories()

        start_idx = find_start_index(tasks, self.args.start)
        if start_idx == -1:
            show_error(f"Task '{self.args.start}' not found!")
            available = ", ".join(t.get("task_no", "?") for t in tasks[:20])
            console.print(f"  [dim]Available: {available}[/dim]")
            return 1

        total = len(tasks)
        if start_idx >= total:
            show_all_done()
            return 0

        stats = get_task_stats(tasks)

        show_banner(
            project=self.project_name,
            tool=self.tool_config.name,
            model=self.model,
            plan_path=str(self.plan_path),
            template_path=(str(self.template_path) if self.template_path else "(from plan)"),
            total=stats["total"],
            done=stats["completed"],
            remaining=stats["remaining"],
            use_proxy=self.use_proxy,
            work_dir=str(self.work_dir),
        )

        atexit.register(reset_terminal_title)

        succeeded = 0
        failed = 0
        skipped = 0
        run_start = time.time()

        for idx in range(start_idx, total):
            if self.interrupted:
                break

            task = tasks[idx]
            task_no = task.get("task_no", f"#{idx + 1}")
            status = task.get("status", "not-started")

            if status == "completed":
                show_task_skip(task_no)
                skipped += 1
                continue

            show_task_start(idx, total, task)

            if template:
                prompt_content = render_prompt(template, task)
            else:
                prompt_content = json.dumps(task, ensure_ascii=False, indent=2)

            safe_name = task_no.replace("/", "_").replace("\\", "_")
            assert self.tasks_dir is not None
            task_file = self.tasks_dir / f"{safe_name}_task.md"
            task_file.write_text(prompt_content, encoding="utf-8")

            rel_prompt = str(task_file.relative_to(self.plan_path.parent))
            show_task_prompt_info(rel_prompt)

            if self.dry_run:
                show_dry_run_skip(task_no)
                continue

            cmd = self._build_command(task_file)
            show_task_cmd(cmd)

            task["status"] = "in-progress"
            save_plan(self.plan_path, plan)

            now = datetime.now()
            log_name = f"{safe_name}_{now.strftime('%H:%M')}.log"
            assert self.logs_dir is not None
            log_path = self.logs_dir / log_name

            show_task_running()
            self._start_heartbeat(task_no)

            return_code, elapsed = self.execute_task(cmd, log_path)

            self._stop_heartbeat_fn()

            if self.interrupted:
                task["status"] = "not-started"
                save_plan(self.plan_path, plan)
                break

            # ── Timeout handling (legacy) ──
            if self._timed_out:
                show_warning(
                    f"Task {task_no} timed out after "
                    f"{self.max_execution_seconds}s "
                    f"({self.max_execution_seconds // 60}min) — marking as FAILED."
                )
                task["status"] = "failed"
                failed += 1
                save_plan(self.plan_path, plan)

                clean_log, clean_text = self._sanitize_log(log_path)
                output_tail = _extract_output_tail(clean_text)
                if clean_log:
                    rel_log = str(clean_log.relative_to(self.plan_path.parent))
                else:
                    rel_log = str(log_path.relative_to(self.plan_path.parent))
                show_task_result(task_no, False, elapsed, rel_log, output_tail)

                current_done = sum(1 for t in tasks if t.get("status") == "completed")
                show_progress_bar(current_done, total)
                continue

            success = return_code == 0

            # Guard: AI CLI finishing in < MIN_EXECUTION_SECONDS is bogus
            if success and elapsed < MIN_EXECUTION_SECONDS:
                show_warning(
                    f"Task {task_no} completed in {elapsed:.1f}s "
                    f"(< {MIN_EXECUTION_SECONDS}s minimum) — marking as FAILED. "
                    f"The AI CLI likely did not process the task."
                )
                success = False

            if success:
                task["status"] = "completed"
                succeeded += 1
            else:
                task["status"] = "failed"
                failed += 1

            save_plan(self.plan_path, plan)

            # Sanitize log (strip ANSI codes + noise)
            clean_log, clean_text = self._sanitize_log(log_path)
            output_tail = _extract_output_tail(clean_text)

            if clean_log:
                rel_log = str(clean_log.relative_to(self.plan_path.parent))
            else:
                rel_log = str(log_path.relative_to(self.plan_path.parent))
            show_task_result(task_no, success, elapsed, rel_log, output_tail)

            current_done = sum(1 for t in tasks if t.get("status") == "completed")
            show_progress_bar(current_done, total)

            # Random delay between tasks (anti-rate-limit)
            remaining_tasks = [t for t in tasks[idx + 1 :] if t.get("status") != "completed"]
            self._inter_task_delay(idx, remaining_tasks, last_success=success)

        reset_terminal_title()

        total_elapsed = time.time() - run_start
        total_done = sum(1 for t in tasks if t.get("status") == "completed")

        show_summary(
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            total=total,
            total_done=total_done,
            total_elapsed=total_elapsed,
            interrupted=self.interrupted,
        )

        return 0 if failed == 0 and not self.interrupted else 1
