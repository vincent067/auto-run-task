"""
Tool and model configurations for Auto Task Runner.

Defines command templates, proxy requirements, and available models
for each supported CLI tool (kimi, agent, copilot, claude).
"""

from dataclasses import dataclass, field


@dataclass
class ToolConfig:
    """Configuration for a single CLI tool."""

    name: str
    cmd_template: str
    needs_proxy: bool
    supports_model: bool
    default_model: str | None = None
    models: list[str] = field(default_factory=list)
    description: str = ""


# ─── Tool Definitions ────────────────────────────────────────────

TOOL_CONFIGS: dict[str, ToolConfig] = {
    "kimi": ToolConfig(
        name="kimi",
        cmd_template='kimi --quiet --yolo -p "$(cat {task_file})"',
        needs_proxy=False,
        supports_model=False,
        description="Kimi AI CLI (Moonshot) — 默认工具，无需代理",
    ),
    "agent": ToolConfig(
        name="agent",
        cmd_template='agent --print -f --trust --model {model} "$(cat {task_file})"',
        needs_proxy=True,
        supports_model=True,
        default_model="opus-4.6",
        models=[
            "auto",
            "composer-2",
            "composer-1.5",
            "composer-1",
            "gpt-5.3-codex",
            "gpt-5.3-codex-fast",
            "gpt-5.3-codex-high",
            "gpt-5.3-codex-high-fast",
            "gpt-5.3-codex-xhigh",
            "opus-4.6-thinking",
            "opus-4.6",
            "opus-4.5",
            "opus-4.5-thinking",
            "sonnet-4.6",
            "sonnet-4.6-thinking",
            "sonnet-4.5",
            "sonnet-4.5-thinking",
        ],
        description="Claude Code Agent CLI — 需要代理",
    ),
    "copilot": ToolConfig(
        name="copilot",
        cmd_template='copilot --silent --yolo --model {model} -p "$(cat {task_file})"',
        needs_proxy=True,
        supports_model=True,
        default_model="claude-opus-4.6",
        models=[
            "claude-sonnet-4.6",
            "claude-sonnet-4.5",
            "claude-haiku-4.5",
            "claude-opus-4.6",
            "claude-opus-4.6-fast",
            "claude-opus-4.5",
            "claude-sonnet-4",
            "gemini-3-pro",
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.2",
            "gpt-5.1-codex-max",
            "gpt-5.1-codex",
            "gpt-5.1",
            "gpt-5.1-codex-mini",
            "gpt-5-mini",
            "gpt-4.1",
        ],
        description="GitHub Copilot CLI — 需要代理",
    ),
    "claude": ToolConfig(
        name="claude",
        cmd_template='claude --print --permission-mode bypassPermissions -p "$(cat {task_file})"',
        needs_proxy=True,
        supports_model=False,
        description="Claude CLI (claude-opus-4-6 only) — 需要代理",
    ),
    "opencode": ToolConfig(
        name="opencode",
        cmd_template='opencode run --model {model} "$(cat {task_file})"',
        needs_proxy=False,
        supports_model=True,
        default_model="minimax-cn-coding-plan/MiniMax-M2.7-highspeed",
        models=[],  # opencode supports many providers — run `opencode models` to list
        description="OpenCode CLI — 无需代理，支持多 provider/model（格式: provider/model）",
    ),
}


# ─── Execution Limits ────────────────────────────────────────────

# Maximum time (in seconds) a single task is allowed to run before being
# killed and marked as failed.  40 minutes by default; override via
# ``--timeout`` CLI flag or project-level configuration.
MAX_EXECUTION_SECONDS: int = 2400


# ─── Proxy Environment Variables ─────────────────────────────────

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "SOCKS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "socks_proxy",
    "no_proxy",
]


def get_tool_config(tool_name: str) -> ToolConfig:
    """Get tool configuration, raising KeyError if not found."""
    if tool_name not in TOOL_CONFIGS:
        available = ", ".join(TOOL_CONFIGS.keys())
        raise KeyError(f"Unknown tool '{tool_name}'. Available: {available}")
    return TOOL_CONFIGS[tool_name]


def list_tool_names() -> list[str]:
    """Get all available tool names."""
    return list(TOOL_CONFIGS.keys())
