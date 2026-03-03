"""
Core display components: console singleton, constants, and utility helpers.
"""

import os
import sys

from rich.console import Console

# ─── Daemon Mode Detection ───────────────────────────────────────

# Daemon mode is activated by:
#   1. Explicit ``--daemon`` CLI flag  (sets _daemon_mode = True via enable_daemon_mode())
#   2. Auto-detection: stdout is NOT a TTY (e.g. supervisor, systemd, nohup)
#
# In daemon mode:
#   - Rich Live panel is disabled (no cursor manipulation)
#   - Terminal title escape sequences are suppressed
#   - \r carriage-return progress is replaced by plain line output
#   - PIPE mode is forced for subprocess execution (no PTY)
#   - Output is line-buffered to prevent silent buffering

_daemon_mode: bool = False


def is_daemon_mode() -> bool:
    """Return True if running in daemon/supervisor mode."""
    return _daemon_mode


def enable_daemon_mode() -> None:
    """Activate daemon mode and reconfigure console for non-interactive output."""
    global _daemon_mode
    _daemon_mode = True

    # Reconfigure the shared console instance in-place so all modules that
    # already imported ``console`` see the change.  We disable colour and
    # override ``is_terminal`` so Rich degrades gracefully (no cursor moves).
    console.no_color = True
    console._force_terminal = False  # type: ignore[attr-defined]

    # Ensure stdout/stderr are line-buffered so supervisor log capture is
    # immediate.  In a non-TTY environment Python may full-buffer stdout.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        # Fallback: set PYTHONUNBUFFERED for child processes at least
        os.environ.setdefault("PYTHONUNBUFFERED", "1")


def auto_detect_daemon_mode() -> None:
    """Auto-enable daemon mode when stdout is not a TTY."""
    if not sys.stdout.isatty():
        enable_daemon_mode()


# ─── Singleton Console ───────────────────────────────────────────

console = Console(highlight=False)

# ─── Constants ───────────────────────────────────────────────────

STATUS_ICONS = {
    "not-started": "⬜",
    "in-progress": "🔄",
    "completed": "✅",
    "failed": "❌",
    "interrupted": "⚡",
    "skipped": "⏭️",
    "planned": "📋",
    "active": "🟢",
    "archived": "📦",
    "running": "🔄",
    "partial": "⚠️",
}

STATUS_STYLES = {
    "not-started": "dim",
    "in-progress": "yellow",
    "completed": "green",
    "failed": "red",
    "interrupted": "yellow",
    "planned": "dim",
    "active": "green",
    "archived": "dim",
}

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

LOGO = r"""
   _____          __          ______           __      ____
  /  _  \  __ ___/  |_  ____ \__   _|____   _/  |_  _/_   |
 /  /_\  \|  |  \   __\/  _ \  |   |__  \  \   __\ \   ___|
/    |    \  |  /|  | (  <_> ) |   |/ __ \_/\  |    |  |
\____|__  /____/ |__|  \____/  |___(____  /  \__|    |__|
        \/                              \/  v3.0
"""


# ─── Terminal Title ──────────────────────────────────────────────


def set_terminal_title(text: str):
    """Set terminal window title via OSC escape sequence.

    Suppressed in daemon mode — escape sequences corrupt supervisor logs.
    """
    if _daemon_mode:
        return
    try:
        sys.stderr.write(f"\033]0;{text}\007")
        sys.stderr.flush()
    except OSError:
        pass


def reset_terminal_title():
    """Reset terminal title to default.

    Suppressed in daemon mode.
    """
    if _daemon_mode:
        return
    try:
        sys.stderr.write("\033]0;\007")
        sys.stderr.flush()
    except OSError:
        pass


# ─── Internal Helpers ────────────────────────────────────────────


def format_elapsed(elapsed: float) -> str:
    """Format elapsed seconds into a human-readable string."""
    total_secs = int(elapsed)
    hours, remainder = divmod(total_secs, 3600)
    mins, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    elif mins > 0:
        return f"{mins}m {secs:02d}s"
    else:
        return f"{secs}s"


# Keep _format_elapsed as alias for backward compat within display submodules
_format_elapsed = format_elapsed
