"""Tests for agent configuration and provider loading."""

import os
from unittest.mock import patch

import pytest

from task_runner.agent.config import AgentAppConfig, LLMConfig


class TestAgentAppConfig:
    def test_from_env_all_set(self):
        env = {
            "MINIMAX_API_KEY": "minimax-key",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/anthropic",
            "MINIMAX_MODEL": "MiniMax-M2.7",
            "KIMI_API_KEY": "kimi-key",
            "KIMI_BASE_URL": "https://api.kimi.com/coding/",
            "KIMI_MODEL": "kimi-for-coding",
            "AGENT_DEFAULT_PROVIDER": "kimi",
            "AGENT_MAX_TOKENS": "8000",
            "AGENT_TEMPERATURE": "0.5",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AgentAppConfig.from_env()
        assert cfg.default_provider == "kimi"
        assert cfg.max_tokens == 8000
        assert cfg.temperature == 0.5
        assert cfg.minimax.api_key == "minimax-key"
        assert cfg.kimi.api_key == "kimi-key"

    def test_from_env_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                AgentAppConfig.from_env()
            assert "MINIMAX_API_KEY" in str(exc_info.value)

    def test_get_config(self):
        env = {
            "MINIMAX_API_KEY": "mk",
            "KIMI_API_KEY": "kk",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AgentAppConfig.from_env()
        assert cfg.get_config("minimax").api_key == "mk"
        assert cfg.get_config("kimi").api_key == "kk"
        with pytest.raises(ValueError):
            cfg.get_config("unknown")


class TestLLMConfig:
    def test_llm_config_creation(self):
        cfg = LLMConfig(api_key="key", base_url="https://example.com", model="m")
        assert cfg.api_key == "key"
        assert cfg.base_url == "https://example.com"
        assert cfg.model == "m"
