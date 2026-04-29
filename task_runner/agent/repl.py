"""
Interactive REPL for the AI Task Planner Agent.

Built with prompt-toolkit (input) + rich (output).
Supports multi-turn conversations, command history, tab completion,
and streaming agent responses.
"""

from __future__ import annotations

import json
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from .agents import (
    orchestrator_agent,
    project_analyzer_agent,
    task_generator_agent,
)
from .display_agent import (
    console,
    show_agent_response,
    show_agent_thinking,
    show_error,
    show_goodbye,
    show_help,
    show_info,
    show_success,
    show_task_set_preview,
    show_warning,
    show_welcome,
)
from .planner import TaskPlanner
from .runner import AnthropicRunner
from .session import AgentSession


class AgentCommandCompleter(WordCompleter):
    """Tab completer for REPL commands."""

    def __init__(self):
        super().__init__([
            "/project",
            "/workspace",
            "/analyze",
            "/plan",
            "/plan-step",
            "/run",
            "/dry-run",
            "/tasks",
            "/save",
            "/status",
            "/clear",
            "/help",
            "/quit",
            "exit",
        ])


class AgentREPL:
    """Interactive REPL for the Task Planner Agent."""

    HISTORY_FILE = Path.home() / ".auto_run_task_history"

    def __init__(self, project_name: str | None = None):
        self.session = PromptSession(
            history=FileHistory(str(self.HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=AgentCommandCompleter(),
            multiline=False,
        )
        self.console = Console()
        self.agent_session = AgentSession(project_name=project_name)
        self.runner = AnthropicRunner()
        self.planner = TaskPlanner(runner=self.runner)

        # If project name is given, try to resolve workspace
        if project_name:
            self._auto_load_project(project_name)

    def _auto_load_project(self, project_name: str) -> None:
        """Try to auto-load project workspace from existing projects."""
        from task_runner.project import load_project

        try:
            cfg = load_project(project_name)
            self.agent_session.project_name = cfg.project
            self.agent_session.workspace = cfg.workspace
            show_info(f"Loaded project '{project_name}' → workspace: {cfg.workspace}")
        except FileNotFoundError:
            show_warning(f"Project '{project_name}' not found. Use /workspace to set path.")

    async def run(self) -> None:
        """Main REPL loop."""
        show_welcome(self.agent_session.project_name)

        while True:
            try:
                user_input = await self.session.prompt_async(
                    HTML("<ansicyan><b>🤖 You</b></ansicyan> > ")
                )
                if not user_input.strip():
                    continue
                await self._handle_input(user_input.strip())
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                show_error(f"{type(e).__name__}: {e}")

        show_goodbye()

    async def _handle_input(self, user_input: str) -> None:
        """Dispatch input to command handler or agent."""
        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            await self._handle_command(cmd, args)
        else:
            # Natural language → Orchestrator
            await self._chat_with_orchestrator(user_input)

    async def _handle_command(self, cmd: str, args: str) -> None:
        """Handle slash commands."""
        handlers = {
            "project": self._cmd_project,
            "workspace": self._cmd_workspace,
            "analyze": self._cmd_analyze,
            "plan": self._cmd_plan,
            "plan-step": self._cmd_plan_step,
            "run": self._cmd_run,
            "dry-run": self._cmd_dry_run,
            "tasks": self._cmd_tasks,
            "save": self._cmd_save,
            "status": self._cmd_status,
            "clear": self._cmd_clear,
            "help": self._cmd_help,
            "quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(args)
        elif cmd in ("exit", "q"):
            await self._cmd_quit("")
        else:
            show_warning(f"Unknown command: /{cmd}. Type /help for available commands.")

    # ─── Command Handlers ──────────────────────────────────────────

    async def _cmd_project(self, args: str) -> None:
        if not args:
            show_info(f"Current project: {self.agent_session.project_name or '(none)'}")
            return
        self._auto_load_project(args.strip())

    async def _cmd_workspace(self, args: str) -> None:
        if not args:
            show_info(f"Workspace: {self.agent_session.workspace or '(not set)'}")
            return
        path = Path(args.strip()).resolve()
        if not path.exists():
            show_error(f"Path does not exist: {path}")
            return
        self.agent_session.workspace = str(path)
        show_success(f"Workspace set to: {path}")

    async def _cmd_analyze(self, _args: str) -> None:
        ws = self.agent_session.workspace
        if not ws:
            show_error("No workspace set. Use /workspace <PATH> first.")
            return

        with show_agent_thinking("ProjectAnalyzer"):
            prompt = (
                f"请深入分析以下项目的结构和技术栈。\n"
                f"项目路径: {ws}\n\n"
                f"要求:\n"
                f"1. 扫描目录结构（忽略 __pycache__, .git, node_modules 等）\n"
                f"2. 识别主要技术栈（框架、语言、数据库等）\n"
                f"3. 提取关键代码模式（如基类、命名规范、架构模式）\n"
                f"4. 列出已有的主要模块和模型\n"
                f"5. 输出为结构化的 JSON 格式"
            )
            result = await self.runner.run(
                agent=project_analyzer_agent,
                input_text=prompt,
                provider="minimax",
            )

        self.agent_session.project_summary = result.output
        show_agent_response("ProjectAnalyzer", result.output)

    async def _cmd_plan(self, args: str) -> None:
        if not args:
            show_error("Usage: /plan <requirement description>")
            return
        await self._run_full_pipeline(args)

    async def _cmd_plan_step(self, args: str) -> None:
        if not args:
            show_error("Usage: /plan-step <requirement description>")
            return
        await self._run_step_by_step_pipeline(args)

    async def _cmd_run(self, _args: str) -> None:
        pn = self.agent_session.project_name
        if not pn:
            show_error("No project loaded. Use /project <NAME> first.")
            return
        show_info("Executing tasks using existing executor...")
        # Bridge to existing executor
        from task_runner.cli import parse_args
        from task_runner.commands.run_cmd import handle_run

        try:
            # Run all task sets in project
            exit_code = handle_run(parse_args(["run", pn, "--all"]))
            show_info(f"Execution finished with exit code: {exit_code}")
        except Exception as e:
            show_error(f"Execution failed: {e}")

    async def _cmd_dry_run(self, _args: str) -> None:
        if not self.agent_session.generated_task_set:
            show_warning("No task set generated yet. Use /plan first.")
            return
        show_task_set_preview(self.agent_session.generated_task_set)

    async def _cmd_tasks(self, _args: str) -> None:
        if not self.agent_session.generated_task_set:
            show_warning("No task set generated yet.")
            return
        show_task_set_preview(self.agent_session.generated_task_set)

    async def _cmd_save(self, _args: str) -> None:
        if not self.agent_session.generated_task_set:
            show_error("No task set to save. Generate one with /plan first.")
            return
        if not self.agent_session.project_name:
            show_error("No project loaded. Use /project <NAME> first.")
            return

        from task_runner.project import get_project_dir

        project_dir = get_project_dir(self.agent_session.project_name)
        task_set_name = self._suggest_task_set_name()
        content = json.dumps(self.agent_session.generated_task_set, ensure_ascii=False, indent=2)

        await self.runner.run(
            agent=task_generator_agent,
            input_text=f"Save task set '{task_set_name}' to {project_dir}",
            messages=[
                {
                    "role": "user",
                    "content": f"Please save this task set as '{task_set_name}.tasks.json':\n\n{content}",
                }
            ],
        )
        show_success(f"Task set saved to {project_dir / f'{task_set_name}.tasks.json'}")

    async def _cmd_status(self, _args: str) -> None:
        lines = [
            "[bold]Session Status[/bold]",
            f"  Project: {self.agent_session.project_name or '(none)'}" ,
            f"  Workspace: {self.agent_session.workspace or '(not set)'}" ,
            f"  Project analyzed: {'✅' if self.agent_session.project_summary else '❌'}" ,
            f"  Tasks generated: {'✅' if self.agent_session.generated_task_set else '❌'}" ,
            f"  Conversation turns: {len(self.agent_session.conversation_history)}" ,
        ]
        self.console.print("\n".join(lines))

    async def _cmd_clear(self, _args: str) -> None:
        self.agent_session.clear_history()
        show_info("Conversation history cleared.")

    async def _cmd_help(self, _args: str) -> None:
        show_help()

    async def _cmd_quit(self, _args: str) -> None:
        raise EOFError

    # ─── Agent Chat & Pipeline ─────────────────────────────────────

    async def _chat_with_orchestrator(self, user_input: str) -> None:
        """Send natural language input to the Orchestrator agent."""
        self.agent_session.add_message("user", user_input)

        # Streaming response for better UX
        full_text = ""
        with Live(Markdown(""), refresh_per_second=10, console=console) as live:
            async for event in self.runner.run_stream(
                agent=orchestrator_agent,
                input_text=user_input,
                provider="kimi",
                messages=self.agent_session.get_history()[:-1],
            ):
                if event.type == "text":
                    full_text += event.data
                    live.update(Markdown(full_text))
                elif event.type == "thinking":
                    # Optionally show thinking dots; for now, silently accumulate
                    pass
                elif event.type == "done":
                    break

        self.agent_session.add_message("assistant", full_text)

    async def _run_full_pipeline(self, requirement: str) -> None:
        """Run the complete planning pipeline via TaskPlanner."""
        ws = self.agent_session.workspace
        if not ws:
            show_error("No workspace set. Use /workspace <PATH> first.")
            return

        self.agent_session.user_requirement = requirement

        show_info("🚀 Starting full planning pipeline (analyze → demand → generate → validate)...")
        result = await self.planner.run_full_pipeline(
            requirement=requirement,
            session=self.agent_session,
        )

        if not result.success:
            show_error(f"Pipeline failed: {result.error}")
            return

        show_success("Task set generated and validated!")
        show_task_set_preview(result.task_set)

        if result.validation.get("issues"):
            issues = result.validation["issues"]
            errors = [i for i in issues if i.get("severity") == "error"]
            warnings = [i for i in issues if i.get("severity") == "warning"]
            if errors:
                show_warning(f"Validation found {len(errors)} error(s):")
                for e in errors:
                    console.print(f"  ❌ {e.get('message', '')}")
            if warnings:
                show_info(f"Validation found {len(warnings)} warning(s):")
                for w in warnings:
                    console.print(f"  ⚠️ {w.get('message', '')}")

    async def _run_step_by_step_pipeline(self, requirement: str) -> None:
        """Run pipeline step by step, pausing between each phase for user confirmation."""
        ws = self.agent_session.workspace
        if not ws:
            show_error("No workspace set. Use /workspace <PATH> first.")
            return

        self.agent_session.user_requirement = requirement
        steps = ["analyze", "demand", "generate", "validate"]

        for step in steps:
            show_info(f"🔹 Step: {step}")
            try:
                result = await self.planner.run_step(
                    step=step,
                    session=self.agent_session,
                    requirement=requirement,
                )
                if step == "analyze":
                    self.agent_session.project_summary = result.output
                    show_success("Project analysis complete.")
                elif step == "demand":
                    from .planner import _extract_json
                    try:
                        data = json.loads(_extract_json(result.output))
                        self.agent_session.analyzed_tasks = data.get("tasks", [])
                    except json.JSONDecodeError:
                        show_warning("Could not parse demand output as JSON.")
                elif step == "generate":
                    from .planner import _extract_json
                    try:
                        self.agent_session.generated_task_set = json.loads(_extract_json(result.output))
                        show_success("Task set generated.")
                        show_task_set_preview(self.agent_session.generated_task_set)
                    except json.JSONDecodeError:
                        show_error("Failed to parse generated task set.")
                elif step == "validate":
                    show_info("Validation complete.")
            except Exception as e:
                show_error(f"Step '{step}' failed: {e}")
                return

            if step != steps[-1] and not await self._confirm(f"Continue to next step ({steps[steps.index(step)+1]})?"):
                return

    # ─── Helpers ───────────────────────────────────────────────────

    async def _confirm(self, message: str) -> bool:
        """Ask user for confirmation."""
        answer = await self.session.prompt_async(HTML(f"<yellow>{message}</yellow> [y/N]: "))
        return answer.strip().lower() in ("y", "yes")

    def _suggest_task_set_name(self) -> str:
        """Suggest a task set name based on requirement."""
        req = self.agent_session.user_requirement or ""
        # Take first 3 ASCII words, lowercase, hyphenated
        import re

        words = re.findall(r"[a-zA-Z0-9]+", req)[:3]
        name = "-".join(w.lower() for w in words)
        return name or "generated-tasks"
