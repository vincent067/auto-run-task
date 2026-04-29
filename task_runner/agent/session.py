"""
Agent session state management.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentSession:
    """Holds the state for an interactive agent session."""

    project_name: str | None = None
    workspace: str | None = None
    project_summary: str = ""  # ProjectAnalyzer output
    user_requirement: str = ""  # Original user requirement
    analyzed_tasks: list[dict] = field(default_factory=list)  # DemandAnalyst output
    generated_task_set: dict | None = None  # TaskSetGenerator output
    conversation_history: list[dict] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        """Append a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def get_history(self) -> list[dict]:
        """Return conversation history as Anthropic-compatible message list."""
        return list(self.conversation_history)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()

    @property
    def workspace_path(self) -> Path | None:
        if self.workspace:
            return Path(self.workspace)
        return None
