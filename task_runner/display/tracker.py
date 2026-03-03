"""
Live execution tracker and heartbeat display.
"""

import time
from datetime import datetime

from rich import box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel

from .core import SPINNER_FRAMES, _format_elapsed, console, is_daemon_mode


class _TrackerRenderable:
    """Dynamic renderable wrapper so Rich Live re-renders on every refresh."""

    def __init__(self, tracker: "ExecutionTracker"):
        self._tracker = tracker

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self._tracker._render()


def show_heartbeat(task_no: str, elapsed: float, frame_idx: int = 0):
    """Print a heartbeat line during long-running tasks."""
    time_str = _format_elapsed(elapsed)
    spinner = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]
    ts = datetime.now().strftime("%H:%M:%S")

    console.print(f"  [dim]{spinner} [{ts}] Task {task_no} running... ({time_str} elapsed)[/dim]")


class ExecutionTracker:
    """Real-time execution tracker using Rich Live display.

    Shows a persistent panel with:
    - Overall progress bar & statistics
    - Current task info with live elapsed timer
    - Per-task result history
    """

    def __init__(self, total_all: int, total_to_execute: int, project: str, task_set: str):
        self.total_all = total_all
        self.total_to_execute = total_to_execute
        self.project = project
        self.task_set = task_set
        self.completed = 0
        self.failed = 0
        self.skipped = 0

        # Current task tracking
        self._current_task_no: str = ""
        self._current_task_name: str = ""
        self._current_start: float = 0.0
        self._current_start_str: str = ""
        self._running: bool = False

        # Result history (last N tasks)
        self._task_history: list[dict] = []

        # Live display
        self._live: Live | None = None
        self._enabled: bool = True

    def start(self):
        """Start the live display.

        Disabled in daemon mode — Rich Live uses cursor manipulation
        that corrupts supervisor/pipe-captured logs.
        """
        if not self._enabled or is_daemon_mode():
            return
        self._live = Live(
            _TrackerRenderable(self),
            console=console,
            refresh_per_second=2,
            transient=True,
        )
        self._live.start()

    def stop(self):
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def set_current_task(self, task_no: str, task_name: str):
        """Mark a task as currently executing."""
        self._current_task_no = task_no
        self._current_task_name = task_name
        self._current_start = time.time()
        self._current_start_str = datetime.now().strftime("%H:%M:%S")
        self._running = True
        self._refresh()

    def record_result(self, task_no: str, task_name: str, success: bool, elapsed: float):
        """Record a completed task result."""
        self._running = False
        status = "✅" if success else "❌"
        self._task_history.append(
            {
                "task_no": task_no,
                "task_name": task_name,
                "status": status,
                "elapsed": elapsed,
                "success": success,
                "finished_at": datetime.now().strftime("%H:%M:%S"),
            }
        )
        if success:
            self.completed += 1
        else:
            self.failed += 1
        self._refresh()

    def record_skip(self, task_no: str):
        """Record a skipped task."""
        self.skipped += 1
        self._refresh()

    def _refresh(self):
        """Update the live display."""
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Panel:
        """Render the live execution panel."""
        parts = []

        # ── Progress Overview ──
        processed = self.completed + self.failed + self.skipped
        total = self.total_to_execute

        pct = (processed / total * 100) if total > 0 else 0
        bar_width = 30
        filled = int(bar_width * processed / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)

        progress_line = (
            f"  [bold cyan]Progress[/bold cyan] │ "
            f"[bold green]{bar}[/bold green] "
            f"[bold]{processed}[/bold]/{total} ({pct:.0f}%)"
        )
        stats_line = (
            f"  [bold cyan]Results [/bold cyan] │ "
            f"[green]✅ {self.completed}[/green]  "
            f"[red]❌ {self.failed}[/red]  "
            f"[dim]⏭️  {self.skipped}[/dim]"
        )
        parts.append(progress_line)
        parts.append(stats_line)

        # ── Current Task ──
        if self._running and self._current_task_no:
            elapsed = time.time() - self._current_start
            time_str = _format_elapsed(elapsed)
            tick = int(elapsed * 2)
            spinner = SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]
            parts.append("")
            parts.append(
                f"  [bold yellow]{spinner} Running[/bold yellow] │ "
                f"[bold]{self._current_task_no}[/bold] — {self._current_task_name}"
            )
            parts.append(
                f"  [bold yellow]  Elapsed[/bold yellow] │ [cyan]{time_str}[/cyan]"
                f"  [dim](started {self._current_start_str})[/dim]"
            )

        # ── Recent History (last 5) ──
        if self._task_history:
            parts.append("")
            parts.append("  [dim]─── Recent ────────────────────────────────[/dim]")
            for entry in self._task_history[-5:]:
                elapsed_str = _format_elapsed(entry["elapsed"])
                finished_at = entry.get("finished_at", "")
                parts.append(
                    f"  {entry['status']} [dim]{entry['task_no']}[/dim] "
                    f"{entry['task_name'][:40]}  [cyan]{elapsed_str}[/cyan]"
                    f"  [dim][{finished_at}][/dim]"
                )

        border = "yellow" if self._running else "green"
        return Panel(
            "\n".join(parts),
            title=f"[bold] ⚡ {self.project} / {self.task_set} [/bold]",
            border_style=border,
            box=box.ROUNDED,
            padding=(0, 1),
        )
