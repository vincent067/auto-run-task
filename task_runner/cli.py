"""
Command-line argument parsing for Auto Task Runner v3.0.

Provides a subcommand-based CLI architecture with legacy compatibility.
Subcommands: project, run, list, dry-run, status.
"""

import argparse
import sys
from pathlib import Path

from .config import TOOL_CONFIGS, list_tool_names


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Detects legacy mode (--plan in argv) and routes to the old parser.
    Otherwise uses the new subcommand architecture.
    """
    raw_argv = argv if argv is not None else sys.argv[1:]

    # Legacy detection: if --plan is present, use old parser
    if "--plan" in raw_argv:
        return _parse_legacy_args(raw_argv)

    return _parse_v3_args(raw_argv)


# ─── V3 Subcommand Parser ───────────────────────────────────────


def _parse_v3_args(argv: list[str]) -> argparse.Namespace:
    """Parse v3 subcommand-based arguments."""
    parser = argparse.ArgumentParser(
        prog="auto-run-task",
        description="Auto Task Runner v3.0 — Project-based AI agent task execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_v3_epilog(),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── project ──
    _add_project_subparser(subparsers)

    # ── run ──
    _add_run_subparser(subparsers)

    # ── dry-run ──
    _add_dryrun_subparser(subparsers)

    # ── list ──
    _add_list_subparser(subparsers)

    # ── reset ──
    _add_reset_subparser(subparsers)

    # ── status ──
    _add_status_subparser(subparsers)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args._legacy = False
    return args


def _add_project_subparser(subparsers):
    """Add the 'project' subcommand."""
    project_parser = subparsers.add_parser(
        "project",
        help="Project management (create, list, info, validate, archive)",
    )
    project_sub = project_parser.add_subparsers(dest="project_action")

    # project create
    create_p = project_sub.add_parser("create", help="Create a new project")
    create_p.add_argument("name", help="Project name (uppercase recommended)")
    create_p.add_argument("--workspace", required=True, help="Absolute path to workspace directory")
    create_p.add_argument("--description", default="", help="Project description")

    # project list
    project_sub.add_parser("list", help="List all projects")

    # project info
    info_p = project_sub.add_parser("info", help="Show project details")
    info_p.add_argument("name", help="Project name")

    # project validate
    validate_p = project_sub.add_parser("validate", help="Validate project structure")
    validate_p.add_argument("name", help="Project name")

    # project archive
    archive_p = project_sub.add_parser("archive", help="Archive a project")
    archive_p.add_argument("name", help="Project name")


def _add_run_subparser(subparsers):
    """Add the 'run' subcommand."""
    run_parser = subparsers.add_parser(
        "run",
        help="Execute tasks from a project's task set",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.add_argument("project_name", help="Project name")
    run_parser.add_argument("task_set_name", help="Task set name (without .tasks.json)")

    _add_execution_options(run_parser)


def _add_dryrun_subparser(subparsers):
    """Add the 'dry-run' subcommand."""
    dryrun_parser = subparsers.add_parser(
        "dry-run",
        help="Generate prompts without executing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dryrun_parser.add_argument("project_name", help="Project name")
    dryrun_parser.add_argument("task_set_name", help="Task set name (without .tasks.json)")

    _add_execution_options(dryrun_parser)


def _add_execution_options(parser):
    """Add common execution options shared by run and dry-run."""
    # Tool & Model
    tool_group = parser.add_argument_group("tool & model")
    tool_group.add_argument(
        "--tool",
        choices=list_tool_names(),
        default=None,
        help="CLI tool to use (default: from project config)",
    )
    tool_group.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Model name (default: from project config)",
    )
    tool_group.add_argument(
        "--template",
        default=None,
        metavar="PATH",
        help="Override template path (relative to project dir or absolute)",
    )

    # Proxy
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument(
        "--proxy",
        dest="proxy_mode",
        action="store_const",
        const="on",
        help="Force enable proxy",
    )
    proxy_group.add_argument(
        "--no-proxy",
        dest="proxy_mode",
        action="store_const",
        const="off",
        help="Force disable proxy",
    )

    # Filtering
    filter_group = parser.add_argument_group("filtering")
    filter_group.add_argument(
        "--batch",
        type=int,
        default=None,
        metavar="N",
        help="Only run tasks in batch N",
    )
    filter_group.add_argument(
        "--min-priority",
        type=int,
        default=None,
        metavar="N",
        help="Only run tasks with priority <= N",
    )
    filter_group.add_argument(
        "--start",
        default=None,
        metavar="TASK_NO",
        help="Start from a specific task number (e.g., 'F-3')",
    )
    filter_group.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only re-run tasks with status 'failed'",
    )

    # Control
    ctrl_group = parser.add_argument_group("execution control")
    ctrl_group.add_argument(
        "--work-dir",
        default=None,
        metavar="DIR",
        help="Override working directory",
    )
    ctrl_group.add_argument(
        "--heartbeat",
        type=int,
        default=60,
        metavar="SEC",
        help="Heartbeat interval in seconds (default: 60)",
    )
    ctrl_group.add_argument(
        "--delay",
        default=None,
        metavar="MIN-MAX",
        help="Random delay between tasks in seconds, e.g. '60-120' (default). "
        "Use '0' to disable, or a single number for fixed delay.",
    )
    ctrl_group.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SEC",
        help="Max execution time per task in seconds (default: 2400 = 40min). "
        "The task is killed and marked failed if it exceeds this limit.",
    )
    ctrl_group.add_argument(
        "--git-safety",
        action="store_true",
        help="Check workspace git status and create safety tag before execution",
    )

    # Notification
    notify_group = parser.add_argument_group("notification")
    notify_toggle = notify_group.add_mutually_exclusive_group()
    notify_toggle.add_argument(
        "--notify",
        dest="notify_enabled",
        action="store_true",
        default=None,
        help="Enable webhook notifications (default: auto-detect from env/config)",
    )
    notify_toggle.add_argument(
        "--no-notify",
        dest="notify_enabled",
        action="store_false",
        help="Disable all webhook notifications",
    )
    notify_group.add_argument(
        "--notify-each",
        action="store_true",
        default=False,
        help="Send a notification for every completed task (not just failures/summary)",
    )
    notify_group.add_argument(
        "--wecom-webhook",
        default=None,
        metavar="URL",
        help="WeCom bot webhook URL (overrides TASK_RUNNER_WECOM_WEBHOOK env var)",
    )

    # Output control
    output_group = parser.add_argument_group("output control")
    verbosity = output_group.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show extra detail (heartbeat each 15s, full paths)",
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (suppress banner, heartbeat, live panel)",
    )
    output_group.add_argument(
        "--no-color",
        action="store_true",
        help="Disable color output (useful for CI/piped output)",
    )
    output_group.add_argument(
        "--daemon",
        action="store_true",
        help="Daemon/supervisor mode: disable interactive features (Live panel, "
        "terminal title, \\r progress bars), force PIPE subprocess mode, "
        "use line-buffered output. Auto-enabled when stdout is not a TTY.",
    )


def _add_reset_subparser(subparsers):
    """Add the 'reset' subcommand."""
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset task statuses to re-run tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  # Reset all failed tasks to not-started
  %(prog)s FIX_CODE code-quality-fix --status failed

  # Reset all tasks from F-3 onward
  %(prog)s FIX_CODE code-quality-fix --from F-3

  # Reset ALL tasks (full re-run)
  %(prog)s FIX_CODE code-quality-fix --all

  # Reset a specific batch
  %(prog)s FIX_CODE code-quality-fix --all --batch 2
""",
    )
    reset_parser.add_argument("project_name", help="Project name")
    reset_parser.add_argument("task_set_name", help="Task set name (without .tasks.json)")

    target_group = reset_parser.add_argument_group("target selection (at least one required)")
    target_group.add_argument(
        "--status",
        choices=["failed", "completed", "interrupted", "in-progress"],
        default=None,
        help="Reset tasks matching this status",
    )
    target_group.add_argument(
        "--from",
        dest="start_from",
        default=None,
        metavar="TASK_NO",
        help="Reset tasks from this task number onward (e.g. 'F-3')",
    )
    target_group.add_argument(
        "--all",
        action="store_true",
        dest="reset_all",
        help="Reset ALL tasks back to not-started",
    )
    target_group.add_argument(
        "--batch",
        type=int,
        default=None,
        metavar="N",
        help="Only reset tasks in batch N (combine with --all or --status)",
    )


def _add_list_subparser(subparsers):
    """Add the 'list' subcommand."""
    list_parser = subparsers.add_parser(
        "list",
        help="List task sets or tasks within a project",
    )
    list_parser.add_argument("project_name", help="Project name")
    list_parser.add_argument(
        "task_set_name", nargs="?", default=None, help="Task set name (optional)"
    )
    list_parser.add_argument("--status", default=None, help="Filter by task status")


def _add_status_subparser(subparsers):
    """Add the 'status' subcommand."""
    status_parser = subparsers.add_parser(
        "status",
        help="Show project status dashboard",
    )
    status_parser.add_argument(
        "project_name", nargs="?", default=None, help="Project name (omit for all)"
    )


# ─── Legacy Parser ───────────────────────────────────────────────


def _parse_legacy_args(argv: list[str]) -> argparse.Namespace:
    """Parse legacy --plan based arguments with deprecation warning."""
    from .display import show_warning

    show_warning(
        "Legacy CLI mode detected (--plan). "
        "This will be removed in v4.0. Use subcommands instead:\n"
        "  python run.py run PROJECT_NAME TASK_SET_NAME [options]\n"
    )

    parser = argparse.ArgumentParser(
        prog="auto-run-task",
        description="Auto Task Runner (Legacy Mode)",
    )

    # Required
    required = parser.add_argument_group("required arguments")
    required.add_argument("--plan", required=True, help="Path to task plan JSON file")
    required.add_argument("--project", required=True, help="Project name")

    # Tool & Model
    tool_group = parser.add_argument_group("tool & model")
    tool_group.add_argument("--tool", choices=list_tool_names(), default="kimi")
    tool_group.add_argument("--model", default=None, metavar="MODEL")
    tool_group.add_argument("--template", default=None, metavar="FILE")

    # Proxy
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument("--proxy", dest="proxy_mode", action="store_const", const="on")
    proxy_group.add_argument("--no-proxy", dest="proxy_mode", action="store_const", const="off")

    # Modes
    mode_group = parser.add_argument_group("execution modes")
    mode_group.add_argument("--dry-run", action="store_true")
    mode_group.add_argument("--list", action="store_true", dest="list_tasks")
    mode_group.add_argument("--list-models", action="store_true")

    # Control
    ctrl_group = parser.add_argument_group("execution control")
    ctrl_group.add_argument("--start", default=None, metavar="TASK_NO")
    ctrl_group.add_argument("--work-dir", default=None, metavar="DIR")
    ctrl_group.add_argument("--heartbeat", type=int, default=60, metavar="SEC")
    ctrl_group.add_argument(
        "--delay",
        default=None,
        metavar="MIN-MAX",
        help="Random delay between tasks in seconds, e.g. '60-120' (default). "
        "Use '0' to disable, or a single number for fixed delay.",
    )

    args = parser.parse_args(argv)
    _validate_legacy_args(args, parser)

    # Parse delay into a tuple so the legacy executor can read it directly
    from .executor import parse_delay_range

    args.delay_range = parse_delay_range(args.delay)

    args._legacy = True
    return args


def _validate_legacy_args(args: argparse.Namespace, parser: argparse.ArgumentParser):
    """Validate legacy args — same as v2 behavior."""
    args.plan_path = Path(args.plan).resolve()
    if not args.plan_path.exists():
        parser.error(f"Plan file not found: {args.plan}")

    tool_config = TOOL_CONFIGS[args.tool]
    args.tool_config = tool_config

    if args.model and not tool_config.supports_model:
        parser.error(f"Tool '{args.tool}' does not support model selection.")

    if args.model and tool_config.models and args.model not in tool_config.models:
        available = ", ".join(tool_config.models)
        parser.error(f"Unknown model '{args.model}' for tool '{args.tool}'. Available: {available}")

    if not args.model and tool_config.supports_model:
        args.model = tool_config.default_model

    if args.proxy_mode == "on":
        args.use_proxy = True
    elif args.proxy_mode == "off":
        args.use_proxy = False
    else:
        args.use_proxy = tool_config.needs_proxy

    if args.template:
        args.template_path = Path(args.template).resolve()
        if not args.template_path.exists():
            parser.error(f"Template file not found: {args.template}")
    else:
        args.template_path = None

    if args.work_dir:
        args.work_dir_path = Path(args.work_dir).resolve()
        if not args.work_dir_path.is_dir():
            parser.error(f"Work directory not found: {args.work_dir}")
    else:
        args.work_dir_path = None

    if args.heartbeat < 5:
        parser.error("--heartbeat must be at least 5 seconds")


# ─── Epilog ──────────────────────────────────────────────────────


def _build_v3_epilog() -> str:
    return """
examples:
  # Create a project
  %(prog)s project create FIX_CODE --workspace /path/to/repo

  # Run tasks
  %(prog)s run FIX_CODE code-quality-fix
  %(prog)s run FIX_CODE code-quality-fix --tool agent --model opus-4.6
  %(prog)s run FIX_CODE code-quality-fix --batch 1

  # Dry-run (generate prompts only)
  %(prog)s dry-run FIX_CODE code-quality-fix

  # List task sets / tasks
  %(prog)s list FIX_CODE
  %(prog)s list FIX_CODE code-quality-fix --status failed

  # Status dashboard
  %(prog)s status
  %(prog)s status FIX_CODE

  # Legacy mode (deprecated)
  %(prog)s --plan plan.json --project my-fix --template prompt.md
"""
