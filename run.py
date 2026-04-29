#!/usr/bin/env python3
"""
Auto Task Runner v3.0 — Project-based AI agent task execution.

Entry point script. Validates dependencies, parses args, and dispatches commands.

Usage:
    python run.py project create NAME --workspace PATH
    python run.py run PROJECT TASK_SET [options]
    python run.py dry-run PROJECT TASK_SET [options]
    python run.py list PROJECT [TASK_SET] [--status STATUS]
    python run.py status [PROJECT]
    python run.py --help

Legacy (deprecated):
    python run.py --plan PLAN.json --project PROJECT [--template TPL.md] [options]
"""

import sys
from pathlib import Path


def check_dependencies():
    """Ensure required packages are installed before importing anything else."""
    try:
        import rich  # noqa: F401
    except ImportError:
        print("╔═══════════════════════════════════════════════════════════╗")
        print("║  ❌ Missing dependency: 'rich' is not installed.        ║")
        print("║                                                          ║")
        print("║  Quick fix:                                              ║")
        print("║    pip install rich                                      ║")
        print("║                                                          ║")
        print("║  Or run the full setup:                                  ║")
        print("║    bash setup.sh                                         ║")
        print("╚═══════════════════════════════════════════════════════════╝")
        sys.exit(1)


def main():
    check_dependencies()

    # Ensure our package is importable
    pkg_dir = str(Path(__file__).resolve().parent)
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    from task_runner.cli import parse_args

    try:
        args = parse_args()

        # Legacy mode: --plan detected
        if getattr(args, "_legacy", False):
            return _run_legacy(args)

        # V3 subcommand dispatch
        command = args.command

        if command == "project":
            from task_runner.commands.project_cmd import handle_project

            sys.exit(handle_project(args))

        elif command == "run":
            from task_runner.commands.run_cmd import handle_run

            sys.exit(handle_run(args))

        elif command == "dry-run":
            from task_runner.commands.dryrun_cmd import handle_dryrun

            sys.exit(handle_dryrun(args))

        elif command == "reset":
            from task_runner.commands.reset_cmd import handle_reset

            sys.exit(handle_reset(args))

        elif command == "list":
            from task_runner.commands.list_cmd import handle_list

            sys.exit(handle_list(args))

        elif command == "status":
            from task_runner.commands.status_cmd import handle_status

            sys.exit(handle_status(args))

        elif command == "plan":
            from task_runner.commands.plan_cmd import handle_plan

            sys.exit(handle_plan(args))

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Aborted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", file=sys.stderr)

        import os

        if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
            import traceback

            traceback.print_exc()

        sys.exit(1)


def _run_legacy(args):
    """Run in legacy mode using the old TaskExecutor interface."""
    from task_runner.executor import TaskExecutor

    executor = TaskExecutor(args=args)
    sys.exit(executor.run())


if __name__ == "__main__":
    main()
