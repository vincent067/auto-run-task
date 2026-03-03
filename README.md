# Auto Task Runner v3.0

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Powered by QeasyCloud](https://img.shields.io/badge/Powered%20by-轻易云-orange.svg)](https://www.qeasy.cloud)

> 项目化 AI Agent CLI 批量任务执行引擎 — 支持多工具、多模型、项目管理、任务集、运行历史

**Auto Task Runner** 是由 [广东轻亿云软件科技有限公司（QeasyCloud）](https://www.qeasy.cloud) 研发团队开源的 AI Agent 批量任务执行引擎。
将结构化的任务集（`.tasks.json`）+ Prompt 模板，批量交给 AI Agent CLI 自动执行。
适用于大规模代码迁移、批量修复、自动化重构等场景。

> 💡 **[轻易云数据集成平台](https://www.qeasy.cloud)** 是我们的核心产品 —— 一站式数据集成解决方案，
> 连接 200+ 应用系统，实现企业数据自动化流转。Auto Task Runner 正是我们在
> AI 辅助研发实践中沉淀出的工程工具。

---

## 特性

- 📁 **项目化架构** — 以项目为中心，支持多任务集、运行历史、模板管理
- 🔧 **多工具支持** — kimi / agent (Claude Code) / copilot / claude，一键切换
- 🤖 **多模型选择** — 项目级、任务集级、任务级可独立配置 tool/model
- 📋 **结构化任务集** — `.tasks.json` 定义任务，`{{key}}` + `#item` 模板渲染
- 🗂️ **运行时管理** — 每次运行自动创建运行目录、备份任务集、记录历史
- 🎯 **智能调度** — batch + priority 排序，依赖验证，支持过滤和重试
- ✅ **验证框架** — 项目结构、工作空间、任务集全面校验
- 🎨 **丰富终端** — Rich 面板、进度条、心跳动画、项目仪表板
- 🌐 **代理自动控制** — kimi 免代理，其他工具自动启用代理
- 🔄 **断点续跑** — 状态实时持久化，中断后从上次位置继续
- 🛡️ **健壮可靠** — PTY 色彩保留、原子写入、优雅信号处理、git 安全标签
- ⏱️ **防误标** — AI CLI 执行低于 10s 自动标记失败（防止空跑）
- 🕐 **防封号** — 任务间随机延时（默认 60-120s），降低被检测为机器人的风险
- � **进程守护** — 支持 supervisor / systemd / nohup，自动检测非 TTY 环境或 `--daemon` 显式启用
- �📢 **企业微信通知** — 批次完成、任务失败、中断时自动推送（可选）

---

## 快速上手

```bash
# 1. 安装
pip install rich

# 2. 创建项目
python run.py project create MY_PROJECT --workspace /path/to/repo

# 3. 编写 templates/__init__.md 和 *.tasks.json（见下方结构说明）

# 4. 执行
python run.py dry-run MY_PROJECT my-tasks   # 预览
python run.py run MY_PROJECT my-tasks       # 执行
```

**完整操作指引、命令示例与典型工作流** → [用户操作指南](docs/USER_GUIDE.md)

---

## 命令速查

| 命令 | 说明 |
| --- | --- |
| `project create` | 创建新项目 |
| `project list` | 列出所有项目 |
| `project info` | 查看项目详情 |
| `project validate` | 校验项目结构 |
| `project archive` | 归档项目 |
| `run` | 执行任务 |
| `dry-run` | 预览模式（只生成 prompt 不执行） |
| `reset` | 重置任务状态（用于重跑） |
| `list` | 列出任务集/任务 |
| `status` | 项目状态仪表板 |

---

## 支持的工具

| 工具      | 默认模型          | 需要代理 | 说明                    |
| --------- | ----------------- | -------- | ----------------------- |
| `kimi`    | —                 | ✗        | Kimi AI CLI（默认工具） |
| `agent`   | `opus-4.6`        | ✓        | Claude Code Agent CLI   |
| `copilot` | `claude-opus-4.6` | ✓        | GitHub Copilot CLI      |
| `claude`  | 固定              | ✓        | Claude CLI（单模型）    |

---

## 项目结构

```
auto-run-task/
├── run.py                    # 入口
├── task_runner/              # 核心模块
├── projects/                 # 项目目录（gitignored）
│   └── MY_PROJECT/
│       ├── __init__.json     # 项目配置
│       ├── *.tasks.json      # 任务集
│       ├── templates/        # Prompt 模板
│       └── runtime/          # 运行输出
└── docs/
    └── USER_GUIDE.md         # 用户操作指南
```

---

## 核心概念

- **`{{key}}`** — 模板占位符，替换为 `task[key]` 的值
- **`#item`** — 替换为整个任务对象的 JSON
- **任务字段** — `task_no`, `task_name`, `batch`, `priority`, `status`, `depends_on`, `cli.tool`, `cli.model` 等

详见 [用户操作指南 - 数据结构](docs/USER_GUIDE.md#数据结构详解)。

---

## 环境要求

- Python 3.11+
- `rich` Python 包
- 对应的 AI CLI 工具已安装并在 PATH 中
- 需要代理的工具，确保系统已配置 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量

---

## 开源信息

### 许可证

本项目基于 [MIT License](LICENSE) 开源。

### 作者

**广东轻亿云软件科技有限公司（QeasyCloud）** 研发团队

- 🌐 官网：[https://www.qeasy.cloud](https://www.qeasy.cloud)
- 📦 GitHub：[https://github.com/qeasy-cloud](https://github.com/qeasy-cloud)

### 贡献

欢迎提交 Issue 和 Pull Request！

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://www.qeasy.cloud">轻易云 QeasyCloud</a> R&D Team</sub>
</p>
