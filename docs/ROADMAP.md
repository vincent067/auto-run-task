# AI Task Planner Agent — 扩展路线图

> 基于当前 `feature/task-planner-agent` 分支的实现，规划后续智能化扩展方向。

---

## Phase 7: 自主运行 Agent（Autonomous Execution Agent）

### 目标
任务集生成后，Agent 能够**自主监控执行进度**，在任务失败时自动分析日志、诊断问题、决策重试或跳过。

### 核心能力
1. **执行监控**
   - 调用现有 `TaskExecutor` 执行任务集
   - 实时捕获每个任务的 stdout/stderr、返回码、执行时长
   - 检测异常信号：非零返回码、超时、空输出（<10s）

2. **失败诊断**
   - 读取失败任务的日志文件（`.clean.log`）
   - 使用 LLM 分析错误类型：编译错误、测试失败、网络问题、AI CLI 异常
   - 分类错误严重程度：可重试 / 需人工介入 / 需调整任务

3. **自动恢复策略**
   | 错误类型 | 自动策略 |
   |----------|----------|
   | 网络超时 / AI CLI 503 | 指数退避重试（最多 3 次） |
   | 编译错误（依赖缺失） | 自动调整任务顺序，前置依赖任务 |
   | 测试失败（代码未实现） | 标记为 failed，生成修复子任务 |
   | AI CLI 返回空结果 | 增加 prompt 详细度，重新生成 |
   | 未知错误 | 暂停执行，通知用户决策 |

4. **执行报告**
   - 生成结构化执行报告（JSON/Markdown）
   - 统计：成功率、平均耗时、失败原因分布
   - 与 `ValidatorAgent` 联动，验证修复后的任务

### 技术实现要点
```python
class AutonomousExecutionAgent:
    async def monitor_and_execute(self, project_name: str, task_set_name: str):
        executor = TaskExecutor(...)  # 复用现有执行器
        for task in scheduled_tasks:
            result = await executor.execute_single(task)
            if not result.success:
                diagnosis = await self.diagnose_failure(result.log_path)
                action = await self.decide_recovery_action(diagnosis)
                await self.execute_recovery(action, task)
```

### 验收标准
- [ ] 单个任务失败后，Agent 能在 60s 内完成诊断并决策
- [ ] 可重试错误的自动恢复成功率 ≥ 70%
- [ ] 生成完整的执行报告，包含时间轴和决策日志

---

## Phase 8: 自主监控 Agent（Autonomous Monitor Agent）

### 目标
以**后台守护进程**模式运行，定时检查 workspace 的 git 变化、代码质量指标，主动建议开发任务。

### 核心能力
1. **Git 变化监控**
   - 监听 `git diff`、`git log`、`git status`
   - 识别新增/修改的文件和模块
   - 检测潜在问题：未测试的代码、缺少文档、API 变更未更新

2. **代码质量扫描**
   - 集成 `ruff`、`mypy`、`pytest` 等工具
   - 扫描 lint 错误、类型错误、测试覆盖率下降
   - 使用 Doubao 多模态 Embedding 做代码相似度分析

3. **主动建议**
   - 当检测到新 commit 时，自动生成 "建议任务集"
   - 示例：
     ```
     🔔 Monitor Agent 检测到变化：
     
     apps/product/models.py 新增了 Product 模型
     └─ 建议任务：
        1. 创建 Product 序列化器
        2. 创建 Product 视图集
        3. 编写 Product 单元测试
        4. 创建数据库迁移
     
     输入 /accept 生成任务集，或 /ignore 忽略
     ```

4. **定时巡检**
   - 可配置检查间隔（默认 30 分钟）
   - 支持 supervisor / systemd / cron 部署
   - 变化时通过企业微信通知（复用现有 `notify.py`）

### 技术实现要点
```python
class AutonomousMonitorAgent:
    async def run_daemon(self, project_name: str, interval_minutes: int = 30):
        while True:
            changes = await self.detect_git_changes(project_name)
            if changes.has_significant_changes:
                suggestions = await self.generate_task_suggestions(changes)
                await self.notify_user(suggestions)
            await asyncio.sleep(interval_minutes * 60)
```

### 验收标准
- [ ] 后台守护进程稳定运行 24h 无崩溃
- [ ] 检测到实质性代码变化后，5 分钟内生成建议
- [ ] 建议的任务集与人工判断的一致性 ≥ 80%

---

## Phase 9: 记忆与学习（Memory & Learning）

### 目标
记录用户反馈（接受/修改/拒绝任务），持续优化生成策略，使 Agent 越来越懂项目风格和用户偏好。

### 核心能力
1. **反馈收集**
   - `/accept` — 用户接受生成的任务集
   - `/modify <desc>` — 用户修改后接受
   - `/reject <reason>` — 用户拒绝并说明原因
   - 记录时间戳、用户、原始输出、最终输出、反馈类型

2. **项目记忆库**
   - 使用 SQLite / JSON 存储每个项目的生成历史
   - 结构：
     ```json
     {
       "project": "MY_PROJECT",
       "memories": [
         {
           "timestamp": "2026-04-29T10:00:00Z",
           "requirement": "创建订单模块",
           "generated_tasks": [...],
           "user_feedback": "accepted",
           "final_tasks": [...]
         }
       ]
     }
     ```

3. **RAG 增强生成**
   - 使用 Doubao 多模态 Embedding（2048 维）对历史任务集做向量索引
   - 新需求生成前，检索相似的历史需求作为 few-shot 示例
   - Prompt 中注入："类似需求 '创建产品模块' 的最终任务集是..."

4. **风格学习**
   - 学习用户的命名偏好（task_no 格式、batch 大小）
   - 学习项目的代码模式（从执行结果中总结）
   - 自动调整生成参数（temperature、max_tokens）

### 技术实现要点
```python
class MemorySystem:
    def store_feedback(self, session: AgentSession, feedback: UserFeedback):
        ...
    
    async def retrieve_similar(self, requirement: str, k: int = 3) -> list[Memory]:
        embedding = await doubao_embed(requirement)
        return vector_db.similarity_search(embedding, k=k)
    
    def build_few_shot_prompt(self, requirement: str) -> str:
        memories = asyncio.run(self.retrieve_similar(requirement))
        return format_few_shot_examples(memories)
```

### 验收标准
- [ ] 反馈数据持久化，支持 1000+ 条记录查询
- [ ] RAG 检索相似需求的准确率 ≥ 85%
- [ ] 经过 10 次反馈后，生成质量主观评分提升 ≥ 20%

---

## Phase 10: 多模态支持（Multimodal Input）

### 目标
支持截图、UI 设计图、架构图作为需求输入，Agent 能解析图像内容并生成对应开发任务。

### 核心能力
1. **图像理解**
   - 使用 Doubao 多模态 Embedding + Vision 模型
   - 解析 UI 截图：识别组件、布局、交互逻辑
   - 解析架构图：识别模块关系、数据流

2. **图像 → 需求转换**
   - 将图像描述转换为结构化需求文本
   - 示例：
     ```
     输入：产品列表页 UI 截图
     输出：
       - 需求：实现产品列表页
       - 包含：搜索框、分页、筛选条件、批量操作按钮
       - 技术：Table 组件、API 分页查询
     ```

3. **图像 → 任务集生成**
   - 基于图像解析结果，走标准 pipeline 生成任务集
   - 支持批量处理多张设计图（如完整原型图集）

### 技术实现要点
```python
class MultimodalDemandAnalyst:
    async def analyze_image(self, image_path: str) -> str:
        # 使用 Doubao-embedding-vision 或 Moonshot 多模态
        client = Ark(api_key=DOUBAO_API_KEY)
        resp = client.embeddings.create(
            model="ep-20260316203438-4gjb6",
            input=[{"type": "image", "image_url": image_path}],
        )
        # 结合 vision 模型生成文本描述
        description = await vision_model.describe(image_path)
        return description
```

### 验收标准
- [ ] 支持 PNG/JPG/WebP 格式输入
- [ ] UI 截图的组件识别准确率 ≥ 80%
- [ ] 从截图到生成任务集的总耗时 ≤ 2 分钟

---

## 优先级与依赖关系

```
Phase 7 (自主运行)
    ↓ 依赖 Phase 4 的 TaskPlanner 和现有 Executor
Phase 8 (自主监控)
    ↓ 依赖 Phase 7 的执行监控能力
Phase 9 (记忆学习)
    ↓ 依赖 Phase 7+8 的数据积累
Phase 10 (多模态)
    ↓ 独立模块，可随时插入
```

## 基础设施预研

| 技术 | 用途 | 当前状态 |
|------|------|----------|
| `Doubao-embedding-vision` | 多模态 Embedding | 密钥已配置，待接入 |
| `SQLiteSession` (openai-agents) | 持久化会话 | 框架已支持 |
| `supervisor` / `systemd` | 守护进程部署 | 现有项目已支持 |
| 向量数据库 (`faiss` / `chromadb`) | RAG 检索 | 待引入 |
