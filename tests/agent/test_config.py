"""Tests for agent configuration loading."""

import os
from unittest.mock import patch

import pytest

from task_runner.agent.config import AgentAppConfig, get_agent_config


class TestAgentAppConfig:
    def test_from_env_success(self):
        env = {
            "MINIMAX_API_KEY": "test-minimax-key",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/anthropic",
            "MINIMAX_MODEL": "MiniMax-M2.7",
            "KIMI_API_KEY": "test-kimi-key",
            "KIMI_BASE_URL": "https://api.kimi.com/coding/",
            "KIMI_MODEL": "kimi-for-coding",
            "AGENT_DEFAULT_PROVIDER": "kimi",
            "AGENT_MAX_TOKENS": "8192",
            "AGENT_TEMPERATURE": "0.5",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AgentAppConfig.from_env()

        assert cfg.minimax.api_key == "test-minimax-key"
        assert cfg.kimi.api_key == "test-kimi-key"
        assert cfg.default_provider == "kimi"
        assert cfg.max_tokens == 8192
        assert cfg.temperature == 0.5

    def test_from_env_missing_key(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(RuntimeError, match="Missing required environment variable"),
        ):
            AgentAppConfig.from_env()

    def test_get_config(self):
        env = {
            "MINIMAX_API_KEY": "k1",
            "KIMI_API_KEY": "k2",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AgentAppConfig.from_env()

        assert cfg.get_config("minimax").api_key == "k1"
        assert cfg.get_config("kimi").api_key == "k2"
        with pytest.raises(ValueError, match="Unknown provider"):
            cfg.get_config("unknown")

    def test_get_agent_config_singleton(self):
        env = {
            "MINIMAX_API_KEY": "k1",
            "KIMI_API_KEY": "k2",
        }
        with patch.dict(os.environ, env, clear=True):
            # Force re-init by clearing singleton
            import task_runner.agent.config as mod

            mod._agent_config = None
            cfg1 = get_agent_config()
            cfg2 = get_agent_config()
            assert cfg1 is cfg2
