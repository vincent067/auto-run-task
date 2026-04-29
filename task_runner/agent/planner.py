"""
Task Planner — orchestrates multi-agent collaboration to generate executable task sets.

Pipeline:
    1. Project Analysis   → scan workspace, identify tech stack & patterns
    2. Demand Analysis    → decompose user requirement into structured tasks
    3. Task Generation    → produce standard .tasks.json + prompt templates
    4. Validation         → validate completeness, dependencies, executability
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .agents import (
    demand_analyst_agent,
    project_analyzer_agent,
    task_generator_agent,
    validator_agent,
)
from .runner import AnthropicRunner, RunResult
from .session import AgentSession


@dataclass
class PipelineResult:
    """Result of a full planning pipeline."""

    success: bool
    project_summary: str = ""
    tasks: list[dict] = field(default_factory=list)
    task_set: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    raw_outputs: list[RunResult] = field(default_factory=list)


class TaskPlanner:
    """Orchestrates the multi-agent task planning pipeline."""

    def __init__(self, runner: AnthropicRunner | None = None):
        self.runner = runner or AnthropicRunner()

    # ─── Public API ────────────────────────────────────────────────

    async def run_full_pipeline(
        self,
        requirement: str,
        session: AgentSession,
        max_turns: int = 10,
    ) -> PipelineResult:
        """Run the complete pipeline: analyze → demand → generate → validate."""
        raw_outputs: list[RunResult] = []

        # Step 1: Project Analysis
        if not session.project_summary:
            analyze_result = await self._analyze_project(
                workspace=session.workspace or ".",
                max_turns=max_turns,
            )
            raw_outputs.append(analyze_result)
            if not analyze_result.output:
                return PipelineResult(
                    success=False,
                    error="Project analysis failed: no output from analyzer.",
                    raw_outputs=raw_outputs,
                )
            session.project_summary = analyze_result.output

        # Step 2: Demand Analysis
        demand_result = await self._analyze_demand(
            requirement=requirement,
            project_summary=session.project_summary,
            max_turns=max_turns,
        )
        raw_outputs.append(demand_result)

        tasks = self._extract_tasks(demand_result.output)
        session.analyzed_tasks = tasks

        # Step 3: Task Set Generation
        gen_result = await self._generate_task_set(
            tasks=tasks,
            project_summary=session.project_summary,
            workspace=session.workspace or ".",
            max_turns=max_turns,
        )
        raw_outputs.append(gen_result)

        task_set = self._extract_task_set(gen_result.output)
        if not task_set:
            return PipelineResult(
                success=False,
                error="Failed to parse generated task set as JSON.",
                project_summary=session.project_summary,
                tasks=tasks,
                raw_outputs=raw_outputs,
            )
        session.generated_task_set = task_set

        # Step 4: Validation (optional but recommended)
        validation_result = await self._validate_task_set(
            task_set=task_set,
            project_summary=session.project_summary,
            max_turns=max_turns,
        )
        raw_outputs.append(validation_result)
        validation = self._extract_validation(validation_result.output)

        return PipelineResult(
            success=True,
            project_summary=session.project_summary,
            tasks=tasks,
            task_set=task_set,
            validation=validation,
            raw_outputs=raw_outputs,
        )

    async def run_step(
        self,
        step: str,
        session: AgentSession,
        requirement: str = "",
        max_turns: int = 10,
    ) -> RunResult:
        """Run a single pipeline step by name.

        Steps: "analyze", "demand", "generate", "validate"
        """
        if step == "analyze":
            return await self._analyze_project(
                workspace=session.workspace or ".",
                max_turns=max_turns,
            )
        elif step == "demand":
            if not session.project_summary:
                raise RuntimeError("Project analysis required before demand analysis.")
            return await self._analyze_demand(
                requirement=requirement,
                project_summary=session.project_summary,
                max_turns=max_turns,
            )
        elif step == "generate":
            if not session.analyzed_tasks:
                raise RuntimeError("Demand analysis required before task generation.")
            return await self._generate_task_set(
                tasks=session.analyzed_tasks,
                project_summary=session.project_summary,
                workspace=session.workspace or ".",
                max_turns=max_turns,
            )
        elif step == "validate":
            if not session.generated_task_set:
                raise RuntimeError("Task generation required before validation.")
            return await self._validate_task_set(
                task_set=session.generated_task_set,
                project_summary=session.project_summary,
                max_turns=max_turns,
            )
        else:
            raise ValueError(f"Unknown step: {step}. Available: analyze, demand, generate, validate")

    # ─── Internal Steps ────────────────────────────────────────────

    async def _analyze_project(self, workspace: str, max_turns: int = 10) -> RunResult:
        prompt = (
            f"请深入分析以下项目的结构和技术栈。\n\n"
            f"项目路径: {workspace}\n\n"
            f"要求:\n"
            f"1. 扫描目录结构（忽略 __pycache__, .git, node_modules 等）\n"
            f"2. 识别主要技术栈（框架、语言、数据库等）\n"
            f"3. 提取关键代码模式（如基类、命名规范、架构模式）\n"
            f"4. 列出已有的主要模块和模型\n"
            f"5. 输出为结构化的 JSON 格式，包含 tech_stack, key_modules, code_patterns, "
            f"existing_models, test_framework, notes 字段"
        )
        return await self.runner.run(
            agent=project_analyzer_agent,
            input_text=prompt,
            provider="minimax",
            max_turns=max_turns,
        )

    async def _analyze_demand(
        self,
        requirement: str,
        project_summary: str,
        max_turns: int = 10,
    ) -> RunResult:
        prompt = (
            f"用户需求: {requirement}\n\n"
            f"项目摘要:\n{project_summary}\n\n"
            f"请将此需求拆解为具体的技术任务列表。\n"
            f"如果需求存在歧义，先列出 clarifying_questions。\n"
            f"输出要求：JSON 格式，包含 tasks 数组（每个任务包含 task_no, task_name, module, type, "
            f"batch, priority, depends_on, description, estimated_minutes, acceptance_criteria）"
        )
        return await self.runner.run(
            agent=demand_analyst_agent,
            input_text=prompt,
            provider="minimax",
            max_turns=max_turns,
        )

    async def _generate_task_set(
        self,
        tasks: list[dict],
        project_summary: str,
        workspace: str,
        max_turns: int = 10,
    ) -> RunResult:
        prompt = (
            f"请基于以下分析结果生成标准的 .tasks.json 任务集。\n\n"
            f"项目摘要:\n{project_summary}\n\n"
            f"任务列表:\n{json.dumps(tasks, ensure_ascii=False, indent=2)}\n\n"
            f"输出要求：\n"
            f"1. 顶层包含 'template' 字段（如 'prompt-feature-dev.md'）\n"
            f"2. 'tasks' 数组，每个任务包含：task_no, task_name, batch, priority, status='not-started', "
            f"depends_on, description, estimated_minutes, cli.tool, cli.model, module, type\n"
            f"3. 依赖关系正确，batch 分组合理\n"
            f"4. 只输出 JSON，不要 markdown 代码块"
        )
        return await self.runner.run(
            agent=task_generator_agent,
            input_text=prompt,
            provider="kimi",
            max_turns=max_turns,
        )

    async def _validate_task_set(
        self,
        task_set: dict,
        project_summary: str,
        max_turns: int = 10,
    ) -> RunResult:
        prompt = (
            f"请验证以下任务集的完整性和正确性。\n\n"
            f"项目摘要:\n{project_summary}\n\n"
            f"任务集:\n{json.dumps(task_set, ensure_ascii=False, indent=2)}\n\n"
            f"检查清单：完整性、依赖合理性、batch 分组、命名规范、可执行性\n"
            f"输出要求：JSON 格式，包含 ok (bool), issues (array), suggestions (array)"
        )
        return await self.runner.run(
            agent=validator_agent,
            input_text=prompt,
            provider="kimi",
            max_turns=max_turns,
        )

    # ─── Extraction Helpers ────────────────────────────────────────

    @staticmethod
    def _extract_tasks(text: str) -> list[dict]:
        """Extract task list from demand analysis output."""
        try:
            data = json.loads(_extract_json(text))
            return data.get("tasks", [])
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _extract_task_set(text: str) -> dict[str, Any] | None:
        """Extract task set JSON from generator output."""
        try:
            return json.loads(_extract_json(text))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_validation(text: str) -> dict[str, Any]:
        """Extract validation result from validator output."""
        try:
            return json.loads(_extract_json(text))
        except json.JSONDecodeError:
            return {"ok": False, "issues": [{"severity": "error", "message": "Failed to parse validation output"}]}


# ─── Helpers ─────────────────────────────────────────────────────


def _extract_json(text: str) -> str:
    """Extract JSON from markdown code blocks or raw text."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
