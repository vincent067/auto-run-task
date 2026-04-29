"""
Tool functions available to agents.

These tools allow agents to interact with the filesystem, run shell commands,
invoke external AI CLIs, and manage task sets.
"""

import asyncio
import json
import subprocess
from pathlib import Path

from agents import function_tool


@function_tool
async def read_file(path: str, max_lines: int = 100) -> str:
    """Read the contents of a file.

    Args:
        path: Absolute or relative path to the file.
        max_lines: Maximum number of lines to read (default 100).
    """
    try:
        p = Path(path)
        if not p.exists():
            return f"[Error] File not found: {path}"
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines])
            content += f"\n\n... ({len(lines) - max_lines} more lines)"
        else:
            content = "\n".join(lines)
        return content
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
async def list_directory(path: str, recursive: bool = False) -> str:
    """List files and directories.

    Args:
        path: Directory path to list.
        recursive: Whether to list recursively (default False).
    """
    try:
        p = Path(path)
        if not p.exists():
            return f"[Error] Directory not found: {path}"
        if not p.is_dir():
            return f"[Error] Not a directory: {path}"

        ignore_patterns = {"__pycache__", ".git", ".venv", ".task_env", "node_modules", ".pytest_cache", ".mypy_cache"}

        def _should_ignore(part: str) -> bool:
            return part in ignore_patterns or part.endswith(".pyc")

        if recursive:
            lines = []
            for item in sorted(p.rglob("*")):
                if any(_should_ignore(part) for part in item.parts):
                    continue
                rel = item.relative_to(p)
                prefix = "  " * (len(rel.parts) - 1)
                marker = "📁 " if item.is_dir() else "📄 "
                lines.append(f"{prefix}{marker}{rel.name}")
            return "\n".join(lines) if lines else "(empty directory)"
        else:
            items = sorted(p.iterdir())
            lines = []
            for item in items:
                if _should_ignore(item.name):
                    continue
                marker = "📁 " if item.is_dir() else "📄 "
                lines.append(f"{marker}{item.name}")
            return "\n".join(lines)
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
async def run_shell(command: str, cwd: str | None = None, timeout: int = 30) -> str:
    """Run a shell command safely.

    Args:
        command: The shell command to run.
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait (default 30).
    """
    # Safety: block dangerous commands
    dangerous = {"rm -rf /", "rm -rf ~", "> /dev/null", "mkfs", "dd if=/dev/zero"}
    for d in dangerous:
        if d in command:
            return f"[Error] Dangerous command blocked: {command}"

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        result = f"[Exit code: {proc.returncode}]\n"
        if out:
            result += f"[stdout]\n{out}\n"
        if err:
            result += f"[stderr]\n{err}\n"
        return result
    except TimeoutError:
        return f"[Error] Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
async def read_existing_tasks(project_path: str) -> str:
    """Read existing task sets from a project directory.

    Args:
        project_path: Path to the project directory.
    """
    try:
        p = Path(project_path)
        task_files = sorted(p.glob("*.tasks.json"))
        if not task_files:
            return "No existing task sets found."

        results = []
        for tf in task_files:
            data = json.loads(tf.read_text(encoding="utf-8"))
            tasks = data.get("tasks", [])
            results.append(
                f"📋 {tf.name} ({len(tasks)} tasks)\n"
                + "\n".join(
                    f"  - {t.get('task_no', '?')}: {t.get('task_name', 'unnamed')}"
                    for t in tasks[:5]
                )
                + ("\n  ..." if len(tasks) > 5 else "")
            )
        return "\n\n".join(results)
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
async def write_tasks_json(project_path: str, task_set_name: str, content: str) -> str:
    """Write a task set JSON file to the project directory.

    Args:
        project_path: Path to the project directory.
        task_set_name: Name of the task set (without .tasks.json suffix).
        content: JSON string of the task set.
    """
    try:
        p = Path(project_path)
        p.mkdir(parents=True, exist_ok=True)
        file_path = p / f"{task_set_name}.tasks.json"

        # Validate JSON
        data = json.loads(content)

        # Write with pretty formatting
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return f"✅ Task set saved to {file_path}"
    except json.JSONDecodeError as e:
        return f"[Error] Invalid JSON: {e}"
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
def invoke_kimi_cli(prompt: str, workspace: str = ".", timeout: int = 600) -> str:
    """Invoke the kimi CLI with a single prompt.

    Args:
        prompt: The prompt text to send.
        workspace: Working directory.
        timeout: Max execution time in seconds.
    """
    try:
        cmd = f'kimi --quiet --yolo -p "{prompt}"'
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        response = f"[Exit code: {result.returncode}]\n"
        if out:
            response += f"[Output]\n{out}\n"
        if err:
            response += f"[Stderr]\n{err}\n"
        return response
    except subprocess.TimeoutExpired:
        return f"[Error] kimi CLI timed out after {timeout}s"
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"


@function_tool
def invoke_opencode_cli(prompt: str, model: str = "minimax-cn-coding-plan/MiniMax-M2.7-highspeed", workspace: str = ".", timeout: int = 600) -> str:
    """Invoke the opencode CLI with a single prompt.

    Args:
        prompt: The prompt text to send.
        model: Model identifier for opencode.
        workspace: Working directory.
        timeout: Max execution time in seconds.
    """
    try:
        cmd = f'opencode run --model {model} "{prompt}"'
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        response = f"[Exit code: {result.returncode}]\n"
        if out:
            response += f"[Output]\n{out}\n"
        if err:
            response += f"[Stderr]\n{err}\n"
        return response
    except subprocess.TimeoutExpired:
        return f"[Error] opencode CLI timed out after {timeout}s"
    except Exception as e:
        return f"[Error] {type(e).__name__}: {e}"
