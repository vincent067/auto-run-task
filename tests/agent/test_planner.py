"""Tests for TaskPlanner."""

import json

import pytest

from task_runner.agent.planner import TaskPlanner, _extract_json
from task_runner.agent.runner import RunResult
from task_runner.agent.session import AgentSession


class TestExtractJson:
    def test_raw_json(self):
        assert _extract_json('{"a": 1}') == '{"a": 1}'

    def test_markdown_json_block(self):
        text = "```json\n{\"a\": 1}\n```"
        assert _extract_json(text) == '{"a": 1}'

    def test_plain_markdown_block(self):
        text = "```\n{\"a\": 1}\n```"
        assert _extract_json(text) == '{"a": 1}'


class TestTaskPlanner:
    def test_extract_tasks(self):
        planner = TaskPlanner()
        text = json.dumps({"tasks": [{"task_no": "F-1", "task_name": "A"}]})
        tasks = planner._extract_tasks(text)
        assert len(tasks) == 1
        assert tasks[0]["task_no"] == "F-1"

    def test_extract_task_set(self):
        planner = TaskPlanner()
        data = {"template": "t.md", "tasks": []}
        result = planner._extract_task_set(json.dumps(data))
        assert result is not None
        assert result["template"] == "t.md"

    def test_extract_task_set_invalid(self):
        planner = TaskPlanner()
        assert planner._extract_task_set("not json") is None

    def test_extract_validation(self):
        planner = TaskPlanner()
        text = json.dumps({"ok": True, "issues": []})
        val = planner._extract_validation(text)
        assert val["ok"] is True

    @pytest.mark.asyncio
    async def test_run_step_analyze(self, monkeypatch):
        """Test that run_step delegates to the correct internal method."""
        planner = TaskPlanner()
        called = {}

        async def fake_analyze(*, workspace, max_turns):
            called["analyze"] = True
            return RunResult(output="summary")

        monkeypatch.setattr(planner, "_analyze_project", fake_analyze)

        session = AgentSession()
        result = await planner.run_step("analyze", session)
        assert called["analyze"]
        assert result.output == "summary"

    @pytest.mark.asyncio
    async def test_run_step_requires_previous(self):
        planner = TaskPlanner()
        session = AgentSession()
        with pytest.raises(RuntimeError) as exc_info:
            await planner.run_step("demand", session)
        assert "Project analysis required" in str(exc_info.value)
