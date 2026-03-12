"""Tests for task_runner.config module."""

import pytest

from task_runner.config import (
    TOOL_CONFIGS,
    ToolConfig,
    get_tool_config,
    list_tool_names,
)


class TestToolConfig:
    def test_all_expected_tools_present(self):
        assert set(TOOL_CONFIGS.keys()) == {"kimi", "agent", "copilot", "claude", "opencode"}

    def test_kimi_no_proxy(self):
        cfg = TOOL_CONFIGS["kimi"]
        assert cfg.needs_proxy is False
        assert cfg.supports_model is False
        assert cfg.default_model is None

    def test_agent_needs_proxy_and_model(self):
        cfg = TOOL_CONFIGS["agent"]
        assert cfg.needs_proxy is True
        assert cfg.supports_model is True
        assert cfg.default_model is not None
        assert len(cfg.models) > 0

    def test_copilot_needs_proxy_and_model(self):
        cfg = TOOL_CONFIGS["copilot"]
        assert cfg.needs_proxy is True
        assert cfg.supports_model is True
        assert cfg.default_model is not None

    def test_claude_no_model_support(self):
        cfg = TOOL_CONFIGS["claude"]
        assert cfg.needs_proxy is True
        assert cfg.supports_model is False

    def test_opencode_no_proxy_with_model(self):
        cfg = TOOL_CONFIGS["opencode"]
        assert cfg.needs_proxy is False
        assert cfg.supports_model is True
        assert cfg.default_model is not None
        assert cfg.models == []  # accepts any provider/model

    def test_cmd_template_contains_task_file(self):
        """Every tool's command template must reference the {task_file} placeholder."""
        for name, cfg in TOOL_CONFIGS.items():
            assert "{task_file}" in cfg.cmd_template, (
                f"Tool '{name}' cmd_template missing {{task_file}}"
            )


class TestGetToolConfig:
    def test_returns_correct_config(self):
        cfg = get_tool_config("kimi")
        assert isinstance(cfg, ToolConfig)
        assert cfg.name == "kimi"

    def test_raises_for_unknown_tool(self):
        with pytest.raises(KeyError, match="Unknown tool"):
            get_tool_config("nonexistent")

    @pytest.mark.parametrize("tool", ["kimi", "agent", "copilot", "claude", "opencode"])
    def test_all_tools_retrievable(self, tool):
        cfg = get_tool_config(tool)
        assert cfg.name == tool


class TestListToolNames:
    def test_returns_list(self):
        names = list_tool_names()
        assert isinstance(names, list)

    def test_contains_all_tools(self):
        names = list_tool_names()
        assert "kimi" in names
        assert "agent" in names
        assert "copilot" in names
        assert "claude" in names
        assert "opencode" in names
