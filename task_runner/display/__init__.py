"""
Rich terminal display helpers for Auto Task Runner v3.0.

This package provides all visual output: banners, tables, task panels,
heartbeat, progress indicators, execution summaries, project dashboards,
and validation.

All public symbols are re-exported here so that existing imports like
``from task_runner.display import show_error, console`` continue to work.
"""

# ─── Core primitives ─────────────────────────────────────────────
# ─── Banners ─────────────────────────────────────────────────────
from .banners import show_banner, show_banner_v3
from .core import (
    LOGO,
    SPINNER_FRAMES,
    STATUS_ICONS,
    STATUS_STYLES,
    _format_elapsed,
    auto_detect_daemon_mode,
    console,
    enable_daemon_mode,
    format_elapsed,
    is_daemon_mode,
    reset_terminal_title,
    set_terminal_title,
)

# ─── Utility messages ────────────────────────────────────────────
from .messages import (
    show_available_models,
    show_delay,
    show_error,
    show_force_exit,
    show_info,
    show_interrupt,
    show_tool_not_found,
    show_warning,
)

# ─── Project / dashboard ─────────────────────────────────────────
from .projects import (
    show_project_dashboard,
    show_project_info,
    show_project_list,
    show_run_history,
    show_schedule_plan,
    show_task_set_list,
    show_validation_result,
)

# ─── Summary / progress ──────────────────────────────────────────
from .summary import show_all_done, show_progress_bar, show_summary

# ─── Task display ────────────────────────────────────────────────
from .tasks import (
    show_dry_run_skip,
    show_task_cmd,
    show_task_list,
    show_task_list_v3,
    show_task_output,
    show_task_prompt_info,
    show_task_result,
    show_task_running,
    show_task_skip,
    show_task_start,
)

# ─── Execution tracker ───────────────────────────────────────────
from .tracker import ExecutionTracker, show_heartbeat

__all__ = [
    "LOGO",
    "SPINNER_FRAMES",
    "STATUS_ICONS",
    "STATUS_STYLES",
    # Tracker
    "ExecutionTracker",
    "_format_elapsed",
    "auto_detect_daemon_mode",
    # Core
    "console",
    "enable_daemon_mode",
    "format_elapsed",
    "is_daemon_mode",
    "reset_terminal_title",
    "set_terminal_title",
    "show_all_done",
    "show_available_models",
    # Banners
    "show_banner",
    "show_banner_v3",
    "show_dry_run_skip",
    "show_delay",
    # Messages
    "show_error",
    "show_force_exit",
    "show_heartbeat",
    "show_info",
    "show_interrupt",
    "show_progress_bar",
    "show_project_dashboard",
    "show_project_info",
    # Projects
    "show_project_list",
    "show_run_history",
    "show_schedule_plan",
    # Summary
    "show_summary",
    "show_task_cmd",
    # Tasks
    "show_task_list",
    "show_task_list_v3",
    "show_task_output",
    "show_task_prompt_info",
    "show_task_result",
    "show_task_running",
    "show_task_set_list",
    "show_task_skip",
    "show_task_start",
    "show_tool_not_found",
    "show_validation_result",
    "show_warning",
]
