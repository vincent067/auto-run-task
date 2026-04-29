"""
Agent configuration loaded from environment variables (.env file).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (silently ignore if not found)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for a single LLM provider."""

    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class AgentAppConfig:
    """Global agent application configuration."""

    minimax: LLMConfig
    kimi: LLMConfig
    default_provider: str
    max_tokens: int
    temperature: float

    @classmethod
    def from_env(cls) -> "AgentAppConfig":
        """Load configuration from environment variables."""
        minimax = LLMConfig(
            api_key=_require_env("MINIMAX_API_KEY"),
            base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
            model=os.getenv("MINIMAX_MODEL", "MiniMax-M2.7"),
        )
        kimi = LLMConfig(
            api_key=_require_env("KIMI_API_KEY"),
            base_url=os.getenv("KIMI_BASE_URL", "https://api.kimi.com/coding/"),
            model=os.getenv("KIMI_MODEL", "kimi-for-coding"),
        )
        return cls(
            minimax=minimax,
            kimi=kimi,
            default_provider=os.getenv("AGENT_DEFAULT_PROVIDER", "minimax").lower(),
            max_tokens=int(os.getenv("AGENT_MAX_TOKENS", "4000")),
            temperature=float(os.getenv("AGENT_TEMPERATURE", "0.2")),
        )

    def get_config(self, provider: str) -> LLMConfig:
        """Get config for a specific provider."""
        if provider == "minimax":
            return self.minimax
        elif provider == "kimi":
            return self.kimi
        raise ValueError(f"Unknown provider: {provider}. Available: minimax, kimi")


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}\n"
            f"Please create a .env file based on .env.example and fill in your API keys."
        )
    return value


# Singleton instance — loaded on first import
_agent_config: AgentAppConfig | None = None


def get_agent_config() -> AgentAppConfig:
    """Get the global agent configuration (lazy-loaded singleton)."""
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentAppConfig.from_env()
    return _agent_config
