"""Tests for agent tool functions.

Tools are wrapped by `function_tool`, so we test via `on_invoke_tool`.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from task_runner.agent.tools import (
    list_directory,
    read_existing_tasks,
    read_file,
    write_tasks_json,
)


async def _invoke(tool, **kwargs):
    """Helper to invoke a FunctionTool with kwargs."""
    ctx = MagicMock()
    return await tool.on_invoke_tool(ctx, json.dumps(kwargs))


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n", encoding="utf-8")
        result = await _invoke(read_file, path=str(f))
        assert "hello" in result
        assert "world" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        result = await _invoke(read_file, path="/nonexistent/path/file.txt")
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_max_lines(self, tmp_path: Path):
        f = tmp_path / "long.txt"
        f.write_text("\n".join(f"line {i}" for i in range(200)), encoding="utf-8")
        result = await _invoke(read_file, path=str(f), max_lines=10)
        assert "more lines" in result


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_list_simple(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b").mkdir()
        result = await _invoke(list_directory, path=str(tmp_path), recursive=False)
        assert "a.py" in result
        assert "b" in result

    @pytest.mark.asyncio
    async def test_list_recursive(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.py").write_text("x")
        result = await _invoke(list_directory, path=str(tmp_path), recursive=True)
        assert "nested.py" in result

    @pytest.mark.asyncio
    async def test_ignores_pycache(self, tmp_path: Path):
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "real.py").write_text("x")
        result = await _invoke(list_directory, path=str(tmp_path), recursive=False)
        assert "__pycache__" not in result
        assert "real.py" in result

    @pytest.mark.asyncio
    async def test_nonexistent(self):
        result = await _invoke(list_directory, path="/nonexistent/dir")
        assert "not found" in result


class TestReadExistingTasks:
    @pytest.mark.asyncio
    async def test_reads_task_files(self, tmp_path: Path):
        import json as json_mod

        data = {"tasks": [{"task_no": "F-1", "task_name": "Test"}]}
        (tmp_path / "feature.tasks.json").write_text(json_mod.dumps(data))
        result = await _invoke(read_existing_tasks, project_path=str(tmp_path))
        assert "feature.tasks.json" in result
        assert "Test" in result

    @pytest.mark.asyncio
    async def test_no_tasks_found(self, tmp_path: Path):
        result = await _invoke(read_existing_tasks, project_path=str(tmp_path))
        assert "No existing task sets" in result


class TestWriteTasksJson:
    @pytest.mark.asyncio
    async def test_writes_valid_json(self, tmp_path: Path):
        data = '{"template": "t.md", "tasks": []}'
        result = await _invoke(
            write_tasks_json, project_path=str(tmp_path), task_set_name="my-tasks", content=data
        )
        assert "saved" in result
        written = json.loads((tmp_path / "my-tasks.tasks.json").read_text())
        assert written["template"] == "t.md"

    @pytest.mark.asyncio
    async def test_invalid_json(self, tmp_path: Path):
        result = await _invoke(
            write_tasks_json, project_path=str(tmp_path), task_set_name="bad", content="not json"
        )
        assert "Invalid JSON" in result
