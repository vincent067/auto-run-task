# AI Task Planner Agent 使用指南

> 🤖 基于 `openai-agents-python` + `anthropic` SDK + `prompt-toolkit` 构建的交互式智能任务规划 Agent。

---

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY 和 KIMI_API_KEY
```

> ⚠️ **`.env` 已加入 `.gitignore`，切勿提交到 git！**

### 2. 启动交互式 REPL

```bash
# 方式1：直接启动
python agent.py

# 方式2：指定项目启动
python agent.py MY_PROJECT

# 方式3：通过 run.py 子命令
python run.py plan MY_PROJECT
```

### 3. 使用示例

```
🤖 You > /workspace /path/to/your/project
✅ Workspace set to: /path/to/your/project

🤖 You > /plan 创建 Product 模块，包含模型、序列化器、视图集和测试
🚀 Starting full planning pipeline (analyze → demand → generate → validate)...
✅ Task set generated and validated!

📋 Task Set: prompt-feature-dev.md
  ⬜ F-1 创建 Product 模型 (batch 1, 10min)
  ⬜ F-2 创建 Product 序列化器 (batch 1, 8min)
     depends_on: F-1
  ⬜ F-3 创建 Product 视图集 (batch 1, 8min)
     depends_on: F-2
  ⬜ F-4 配置路由和迁移 (batch 1, 5min)
     depends_on: F-3
  ⬜ F-5 编写 Product 单元测试 (batch 2, 15min)
     depends_on: F-4

🤖 You > /save
✅ Task set saved to projects/MY_PROJECT/create-product-module.tasks.json

🤖 You > /run
# 开始批量执行任务...
```

---

## REPL 命令速查

| 命令 | 功能 |
|------|------|
| `/project <NAME>` | 加载/切换项目 |
| `/workspace <PATH>` | 设置工作目录 |
| `/analyze` | 分析项目结构 |
| `/plan <描述>` | 生成任务集（完整流程） |
| `/plan-step` | 分步执行（每步确认） |
| `/run` | 执行当前项目任务集 |
| `/dry-run` | 预览生成的 prompts |
| `/tasks` | 查看当前生成的任务 |
| `/save` | 保存任务集到项目目录 |
| `/status` | 查看会话状态 |
| `/clear` | 清空对话历史 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |

> 不以 `/` 开头的输入会交给 Orchestrator Agent 处理。

---

## 架构概览

### 多 Agent 协作流程

```
User (自然语言需求)
    ↓
OrchestratorAgent (Kimi Coding) — 主控、路由
    ↓
├─→ ProjectAnalyzerAgent (MiniMax M2.7) — 扫描项目结构
├─→ DemandAnalystAgent (MiniMax M2.7) — 拆解需求
├─→ TaskSetGeneratorAgent (Kimi Coding) — 生成任务集
└─→ ValidatorAgent (Kimi Coding) — 验证完整性
    ↓
.tasks.json + prompt 模板（兼容 v3 执行器）
```

### Karpathy Skills 注入

每个 Agent 都注入了对应的原则：
- **Think Before Coding** → Orchestrator / DemandAnalyst
- **Simplicity First** → TaskSetGenerator
- **Surgical Changes** → ProjectAnalyzer
- **Goal-Driven Execution** → TaskSetGenerator / Validator

---

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | `openai-agents-python` | Agent / Tool / Handoff 抽象 |
| LLM 调用 | `anthropic` SDK | MiniMax & Kimi 均兼容 Anthropic Messages API |
| 交互式 CLI | `prompt-toolkit` + `rich` | 输入/历史/补全 + Markdown 渲染 |
| 配置管理 | `python-dotenv` | `.env` 管理密钥 |

---

## 自定义配置

### 修改模型参数

编辑 `.env`：

```bash
AGENT_DEFAULT_PROVIDER=minimax    # 或 kimi
AGENT_MAX_TOKENS=8000
AGENT_TEMPERATURE=0.3
```

### 添加自定义 Agent

在 `task_runner/agent/agents.py` 中定义：

```python
my_custom_agent = Agent(
    name="MyAgent",
    instructions="你的系统提示词...",
    tools=[read_file, list_directory],
    model="minimax",  # 或 kimi
)
```

### 添加自定义 Tool

在 `task_runner/agent/tools.py` 中定义：

```python
@function_tool
async def my_tool(param: str) -> str:
    """Tool description shown to the LLM."""
    return f"Result: {param}"
```

---

## 扩展路线

| 阶段 | 功能 |
|------|------|
| Phase 7 | **自主运行 Agent** — 监控执行进度，失败自动重试 |
| Phase 8 | **自主监控 Agent** — 后台守护，定时检查 git 变化 |
| Phase 9 | **记忆与学习** — 记录用户反馈，持续优化生成策略 |
| Phase 10 | **多模态支持** — 截图/UI 设计图作为需求输入 |
