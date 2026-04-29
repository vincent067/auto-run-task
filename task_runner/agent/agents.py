"""
Agent definitions for the Task Planner system.

Each agent is configured with instructions (system prompt), tools, and model settings.
Agents use the openai-agents-python Agent dataclass for compatibility.
"""

from agents import Agent

from .skills import (
    SKILL_AGENT_DEMAND_ANALYST,
    SKILL_AGENT_ORCHESTRATOR,
    SKILL_AGENT_PROJECT_ANALYZER,
    SKILL_AGENT_TASK_GENERATOR,
    SKILL_AGENT_VALIDATOR,
)
from .tools import (
    invoke_kimi_cli,
    invoke_opencode_cli,
    list_directory,
    read_existing_tasks,
    read_file,
    run_shell,
    write_tasks_json,
)

# ─── Orchestrator Agent ──────────────────────────────────────────

orchestrator_agent = Agent(
    name="Orchestrator",
    instructions=SKILL_AGENT_ORCHESTRATOR,
    tools=[
        list_directory,
        read_file,
    ],
    model="kimi",  # Provider hint for our runner
)

# ─── Project Analyzer Agent ──────────────────────────────────────

project_analyzer_agent = Agent(
    name="ProjectAnalyzer",
    instructions=SKILL_AGENT_PROJECT_ANALYZER,
    tools=[
        list_directory,
        read_file,
        run_shell,
    ],
    model="minimax",
)

# ─── Demand Analyst Agent ────────────────────────────────────────

demand_analyst_agent = Agent(
    name="DemandAnalyst",
    instructions=SKILL_AGENT_DEMAND_ANALYST,
    tools=[
        read_file,
        read_existing_tasks,
    ],
    model="minimax",
)

# ─── Task Set Generator Agent ────────────────────────────────────

task_generator_agent = Agent(
    name="TaskSetGenerator",
    instructions=SKILL_AGENT_TASK_GENERATOR,
    tools=[
        write_tasks_json,
        read_existing_tasks,
    ],
    model="kimi",
)

# ─── Validator Agent ─────────────────────────────────────────────

validator_agent = Agent(
    name="Validator",
    instructions=SKILL_AGENT_VALIDATOR,
    tools=[
        read_file,
        read_existing_tasks,
    ],
    model="kimi",
)

# ─── CLI Invoker Agent ───────────────────────────────────────────

cli_invoker_agent = Agent(
    name="CLIInvoker",
    instructions=(
        "你是 CLI 调用 Agent。你的职责是调用外部 AI CLI 工具（kimi / opencode）"
        "执行单个任务，并分析返回结果的质量。"
    ),
    tools=[
        invoke_kimi_cli,
        invoke_opencode_cli,
    ],
    model="minimax",
)
