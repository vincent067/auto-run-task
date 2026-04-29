#!/usr/bin/env python3
"""
Shortcut entry point: directly launch the interactive Agent REPL.

Usage:
    python agent.py [PROJECT_NAME]

Examples:
    python agent.py MY_PROJECT
    python agent.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure package importable
pkg_dir = str(Path(__file__).resolve().parent)
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)


def check_dependencies() -> None:
    missing = []
    for pkg in ("rich", "prompt_toolkit", "anthropic", "dotenv"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("╔═══════════════════════════════════════════════════════════╗")
        print("║  ❌ Missing dependencies. Please install:               ║")
        for m in missing:
            print(f"║     pip install {m}")
        print("╚═══════════════════════════════════════════════════════════╝")
        sys.exit(1)


async def main() -> int:
    check_dependencies()

    from task_runner.agent.repl import AgentREPL

    project = sys.argv[1] if len(sys.argv) > 1 else None
    repl = AgentREPL(project_name=project)
    await repl.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n\n👋 Aborted by user.")
        sys.exit(130)
