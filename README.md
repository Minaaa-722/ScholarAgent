# ScholarAgent — 论文综述智能体

ScholarAgent 是一个**自编码的 Coding Agent Harness**，用于自动生成 CVPR 格式的学术文献综述论文。用户只需输入研究主题，Agent 即可完成「检索 → 分析 → 写作 → 验证」全流程，最终输出一篇完整的综述论文。

> **AI4SE 期末项目 · Track A · Coding Agent Harness**

---

## 功能特性

- **端到端综述生成**：输入主题，自动输出 CVPR 格式综述论文
- **多源文献检索**：集成 arXiv、Semantic Scholar、Google Scholar
- **反馈闭环**：5 个确定性校验器（引用检查、幻觉检测、字数统计、语言润色、连贯性检查），支持多轮修正
- **守卫系统**：5 类守卫（来源过滤、事实绑定、操作安全、速率限制、输出标准化）
- **双层级记忆**：会话级 JSON 持久化 + 跨会话 SQLite 持久化
- **实时 Web UI**：React 前端，5 页面导航，WebSocket 实时进度推送
- **RESTful API**：FastAPI 后端，完整 REST + WebSocket 端点

---

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+
- LLM API Key（OpenAI 或 Anthropic）

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/scholaragent.git
cd scholaragent

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Web 前端依赖
cd web && npm install && cd ..

# 4. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 运行

```bash
# 终端 1：启动 API 服务
make run-api

# 终端 2：启动 Web 前端
cd web && npm run dev
```

打开浏览器访问 `http://localhost:5173`

### 运行测试

```bash
make test
```

---

## 项目结构

```
ScholarAgent/
├── agent/                          # Agent Harness 核心
│   ├── core/                       # 核心模块
│   │   ├── harness.py              # 主循环调度器
│   │   ├── state.py                # 状态机
│   │   └── llm.py                  # LLM 抽象层
│   ├── tools/                      # 工具系统
│   │   ├── base.py                 # 工具基类
│   │   ├── registry.py             # 工具注册表
│   │   ├── retrieval.py            # 检索工具
│   │   ├── processing.py           # 后处理工具
│   │   ├── writing.py              # 写作工具
│   │   └── auxiliary.py            # 辅助工具
│   ├── feedback/                   # 反馈系统 (重点维度)
│   │   ├── base.py                 # 校验器基类
│   │   ├── check_citations.py      # 引用检查
│   │   ├── detect_hallucination.py # 幻觉检测
│   │   ├── check_word_count.py     # 字数统计
│   │   ├── polish_language.py      # 语言润色
│   │   ├── check_coherence.py      # 连贯性检查
│   │   ├── aggregator.py           # 反馈聚合器
│   │   └── repair_generator.py     # 修复指令生成器
│   ├── guardrails/                 # 守卫系统
│   │   ├── base.py                 # 守卫基类
│   │   ├── source_filter.py        # 来源过滤
│   │   ├── fact_binding.py         # 事实绑定
│   │   ├── op_safety.py            # 操作安全
│   │   ├── rate_limit.py           # 速率限制
│   │   └── output_std.py           # 输出标准化
│   └── memory/                     # 记忆系统
│       ├── base.py                 # 记忆基类
│       ├── session.py              # 会话记忆 (JSON)
│       └── persistent.py           # 持久记忆 (SQLite)
├── api/                            # API 层
│   ├── main.py                     # FastAPI 应用
│   ├── models.py                   # Pydantic 模型
│   └── routes/                     # 路由
│       ├── survey.py               # 综述任务 API
│       ├── feedback.py             # 反馈 API
│       ├── progress.py             # 进度 WebSocket
│       └── memory.py               # 记忆管理 API
├── web/                            # Web 前端 (React + TypeScript)
│   ├── src/
│   │   ├── pages/                  # 5 个页面
│   │   │   ├── Dashboard.tsx
│   │   │   ├── ResearchCreation.tsx
│   │   │   ├── AgentExecution.tsx
│   │   │   ├── KnowledgeExplorer.tsx
│   │   │   └── FinalReview.tsx
│   │   ├── components/
│   │   │   └── Layout.tsx
│   │   └── api/
│   │       └── client.ts
│   └── ...
├── tests/                          # 测试套件 (70 个测试)
│   ├── test_llm.py                 # LLM 抽象层测试
│   ├── test_state.py               # 状态机测试
│   ├── test_harness.py             # Harness 主循环测试
│   ├── test_tools.py               # 工具系统测试
│   ├── test_guardrails.py          # 守卫系统测试
│   ├── test_memory.py              # 记忆系统测试
│   ├── test_feedback.py            # 反馈系统测试 (含多轮迭代)
│   └── test_api.py                 # API 层测试
├── SPEC.md                         # 设计规约
├── PLAN.md                         # 实现计划
└── Makefile                        # 构建命令
```

---

## 系统架构

```
Web UI (React) ←→ API (FastAPI) ←→ Agent Harness (Python)
                                       ├── State Machine
                                       ├── Tools (检索/处理/写作/验证/辅助)
                                       ├── Feedback (5 校验器 + 多轮修正)
                                       ├── Guardrails (5 守卫)
                                       └── Memory (会话 JSON + 持久 SQLite)
```

**数据流：** `用户输入 → PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → COMPLETE`

---

## 安全边界

- API Key 绝不硬编码，通过 `.env` 文件加载（已加入 `.gitignore`）
- 操作安全守卫拦截 `rm -rf`、`DROP TABLE` 等危险命令
- 速率限制防止 API 滥用（默认 30 次/分钟）

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端语言 | Python 3.11+ |
| API 框架 | FastAPI |
| 前端 | React + TypeScript + Vite |
| 持久化 | SQLite + JSON |
| 测试 | pytest + pytest-asyncio + httpx |
| 分发 | Docker |

---

## 许可证

MIT