"""
Handler for the `plan` subcommand — launches the interactive Agent REPL.
"""

import asyncio
import sys

from task_runner.agent.repl import AgentREPL
from task_runner.display import console, show_error


def handle_plan(args) -> int:
    """Handle the `plan` subcommand.

    Usage:
        python run.py plan [PROJECT_NAME] [--workspace PATH]
    """
    project_name = getattr(args, "project_name", None)
    workspace = getattr(args, "workspace", None)

    try:
        repl = AgentREPL(project_name=project_name)
        if workspace:
            repl.agent_session.workspace = workspace
        asyncio.run(repl.run())
        return 0
    except Exception as e:
        show_error(f"Agent REPL failed: {e}")
        return 1
