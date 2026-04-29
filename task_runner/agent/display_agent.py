"""
Rich display utilities for agent output in the REPL.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status

console = Console()


def show_welcome(project_name: str | None = None):
    """Display the welcome banner."""
    title = "🤖 Auto Task Runner — AI Task Planner"
    subtitle = f"Project: {project_name}" if project_name else "No project loaded"
    console.print(
        Panel(
            f"[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]\n\n"
            "Type your requirement in natural language, or use a command:\n"
            "  [green]/plan[/green] <description>  — Generate a task set\n"
            "  [green]/analyze[/green]           — Analyze project structure\n"
            "  [green]/tasks[/green]             — View generated tasks\n"
            "  [green]/save[/green]              — Save task set to project\n"
            "  [green]/run[/green]               — Execute tasks\n"
            "  [green]/help[/green]              — Show all commands\n"
            "  [green]/quit[/green]              — Exit",
            title="Welcome",
            border_style="cyan",
        )
    )


def show_goodbye():
    """Display the goodbye message."""
    console.print("\n[dim]👋 Goodbye![/dim]\n")


def show_agent_thinking(agent_name: str) -> Status:
    """Return a Status context manager for agent thinking."""
    return console.status(
        f"[bold cyan]🧠 {agent_name} is thinking...[/bold cyan]",
        spinner="dots",
    )


def show_agent_response(agent_name: str, text: str):
    """Display an agent's response as a panel."""
    console.print(
        Panel(
            Markdown(text),
            title=f"[bold green]{agent_name}[/bold green]",
            border_style="green",
        )
    )


def show_streaming_chunk(chunk: str):
    """Print a streaming text chunk (used with Live)."""
    console.print(chunk, end="")


def show_tool_call(tool_name: str, tool_input: dict):
    """Display a tool call."""
    console.print(
        f"[dim]🔧 Tool call: [bold]{tool_name}[/bold]"
        f"({', '.join(f'{k}={v!r}' for k, v in list(tool_input.items())[:3])})"
        f"[/dim]"
    )


def show_error(message: str):
    """Display an error message."""
    console.print(f"[bold red]❌ Error:[/bold red] {message}")


def show_info(message: str):
    """Display an info message."""
    console.print(f"[cyan]ℹ️ {message}[/cyan]")


def show_success(message: str):
    """Display a success message."""
    console.print(f"[bold green]✅ {message}[/bold green]")


def show_warning(message: str):
    """Display a warning message."""
    console.print(f"[bold yellow]⚠️ {message}[/bold yellow]")


def show_task_set_preview(task_set: dict):
    """Display a preview of the generated task set."""
    tasks = task_set.get("tasks", [])
    if not tasks:
        console.print("[dim]No tasks generated.[/dim]")
        return

    lines = [f"[bold]📋 Task Set: {task_set.get('template', 'default')}[/bold]\n"]
    for t in tasks:
        status_emoji = "⬜"
        lines.append(
            f"  {status_emoji} [bold]{t.get('task_no', '?')}[/bold]"
            f" {t.get('task_name', 'Unnamed')}"
            f" [dim](batch {t.get('batch', 1)},"
            f" {t.get('estimated_minutes', '?')}min)[/dim]"
        )
        if t.get("depends_on"):
            lines.append(f"     [dim]depends_on: {t['depends_on']}[/dim]")

    console.print(Panel("\n".join(lines), border_style="blue"))


def show_help():
    """Display the help panel."""
    commands = """
[bold cyan]Commands:[/bold cyan]
  [green]/project <NAME>[/green]      Load or switch project
  [green]/workspace <PATH>[/green]    Set workspace directory
  [green]/analyze[/green]             Analyze project structure
  [green]/plan <desc>[/green]         Generate task set from description
  [green]/plan-step[/green]           Step-by-step planning (analyze → demand → generate)
  [green]/run[/green]                 Execute current project tasks
  [green]/dry-run[/green]             Preview generated prompts
  [green]/tasks[/green]               View current generated tasks
  [green]/save[/green]                Save generated task set
  [green]/status[/green]              Show session status
  [green]/clear[/green]               Clear conversation history
  [green]/help[/green]                Show this help
  [green]/quit[/green] or [green]exit[/green]  Exit REPL

[bold cyan]Natural Language:[/bold cyan]
  Type any requirement directly (without /) to chat with the Orchestrator.
"""
    console.print(Panel(commands, title="Help", border_style="cyan"))
