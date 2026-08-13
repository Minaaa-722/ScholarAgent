# ScholarAgent — 学术综述自动生成智能体

> **AI4SE 期末项目 · Track A · Coding Agent Harness**
>
> 自编码六维 Agent Harness，输入研究主题，自动完成「检索 → 分析 → 写作 → 验证」全流程，输出 IEEEtran 会议格式的学术文献综述论文。

---

## 功能特性

| 特性 | 描述 |
|------|------|
| **端到端综述生成** | 输入研究主题，自动输出符合 IEEEtran 会议格式的完整综述论文（摘要、引言、分类、方法对比、挑战与未来工作） |
| **多源文献检索** | 集成 arXiv、Semantic Scholar、Google Scholar 三源检索，自动去重合并、按引用排序 |
| **证据支撑层** | 18 文件证据引擎：论断提取 → 引用锚定 → 事实校验 → 基准数据提取，确保每个论断可追溯至具体文献 |
| **Pipeline 编排** | 1385 行 PipelineOrchestrator 驱动 PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → COMPLETE 全流程 |
| **反馈闭环** | 5 个确定性校验器（引用检查、幻觉检测、字数统计、语言润色、连贯性检查）+ 聚合器 + 修复指令生成器，支持多轮自动修正 |
| **守卫系统** | 5 类守卫（来源过滤、事实绑定、操作安全、速率限制、输出标准化），统一管理器调度 |
| **双层级记忆** | 会话级 JSON 持久化 + 跨会话 SQLite 持久化，含记忆集成层自动注入用户偏好 |
| **实时 Web UI** | 7 页面 React 前端，14 个组件，WebSocket 实时进度推送，支持人工反馈注入 |
| **RESTful API** | FastAPI 后端，7 路由模块（综述、进度、反馈、记忆、凭据、历史、健康检查），完整 OpenAPI 文档 |
| **凭据安全存储** | 支持 Windows Credential Manager / keyring / .env 三种凭据管理方式，API Key 绝不硬编码 |
| **CI/CD 就绪** | GitHub Actions 三流水线（单元测试 + lint + 前端构建），Docker 多阶段构建 |

---

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+
- LLM API Key（OpenAI 兼容接口，默认使用学校代理 `https://njusehub.info/v1`）

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
# 可选自定义 LLM_BASE_URL 和 LLM_MODEL
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
# 运行全部 506+ 个测试（~26 秒，无需网络/LLM 依赖）
make test

# 或带覆盖率报告
make coverage
```

---

## 项目结构

```
ScholarAgent/
├── agent/                          # Agent Harness 核心
│   ├── core/                       # 核心模块
│   │   ├── harness.py              # 主循环调度器（1152 行）
│   │   ├── pipeline.py             # PipelineOrchestrator 编排（1385 行）
│   │   ├── state.py                # 状态机（66 行）
│   │   ├── llm.py                  # LLM 抽象层（213 行）
│   │   └── config.py               # 声明式配置
│   ├── tools/                      # 工具系统（5 类别）
│   │   ├── base.py / registry.py   # 工具基类 + 注册表
│   │   ├── retrieval.py            # 检索工具（arxiv / semantic scholar / merge）
│   │   ├── processing.py           # 后处理工具（PDF 下载/解析/去重/BibTeX）
│   │   ├── writing.py              # 写作工具（章节生成/扩展/引用插入）
│   │   ├── relevance.py            # 相关性过滤工具
│   │   ├── models.py / prompts.py  # 数据模型 + 提示词模板
│   │   └── auxiliary.py            # 辅助工具（web search / shell exec）
│   ├── evidence/                   # 证据支撑层（18 文件）
│   │   ├── claim_extractor.py      # 论断提取器
│   │   ├── evidence_store.py       # 证据存储
│   │   ├── verifier.py / checker.py# 证据校验器
│   │   ├── pdf_parser.py           # PDF 解析器
│   │   ├── paper_analyzer.py       # 论文分析器
│   │   ├── paper_knowledge.py      # 论文知识库（架构/训练知识）
│   │   ├── citation_store.py / citation_anchor_store.py / citation_injector.py
│   │   ├── evidence_reference.py   # 证据引用管理
│   │   ├── benchmark_extractor.py / benchmark_store.py
│   │   ├── context_retriever.py    # 上下文检索器
│   │   └── table_generator.py      # Benchmark 表格生成器
│   ├── feedback/                   # 反馈系统（重点维度）
│   │   ├── base.py                 # 校验器基类
│   │   ├── check_citations.py      # 引用检查校验器
│   │   ├── detect_hallucination.py # 幻觉检测校验器
│   │   ├── check_word_count.py     # 字数统计校验器
│   │   ├── polish_language.py      # 语言润色校验器
│   │   ├── check_coherence.py      # 连贯性检查校验器
│   │   ├── latex_repair.py         # LaTeX 格式修复
│   │   ├── aggregator.py           # 反馈聚合器
│   │   └── repair_generator.py     # 修复指令生成器
│   ├── guardrails/                 # 守卫系统（5 守卫 + 统一管理器）
│   │   ├── base.py / manager.py    # 守卫基类 + 统一管理器
│   │   ├── source_filter.py        # 来源过滤
│   │   ├── fact_binding.py         # 事实绑定
│   │   ├── op_safety.py            # 操作安全
│   │   ├── rate_limit.py           # 速率限制
│   │   └── output_std.py           # 输出标准化
│   └── memory/                     # 记忆系统（2 层级）
│       ├── base.py                 # 记忆基类
│       ├── session.py              # 会话记忆（JSON 持久化）
│       ├── persistent.py           # 持久记忆（SQLite）
│       └── integration.py          # 记忆集成层
├── api/                            # API 层（FastAPI）
│   ├── main.py                     # 应用入口 + 健康检查
│   ├── models.py                   # Pydantic 数据模型
│   └── routes/                     # 7 路由模块
│       ├── survey.py               # 综述任务 CRUD
│       ├── progress.py             # 进度 WebSocket 推送
│       ├── feedback.py             # 反馈注入 API
│       ├── memory.py               # 记忆管理 API
│       ├── credentials.py          # 凭据管理 API
│       └── history.py              # 历史任务 API
├── web/                            # Web 前端（React + TypeScript + Vite）
│   ├── src/
│   │   ├── App.tsx                 # 7 路由入口
│   │   ├── api/client.ts           # API 客户端
│   │   ├── hooks/useWebSocket.ts   # WebSocket 实时连接 Hook
│   │   ├── pages/                  # 7 个页面
│   │   │   ├── Dashboard.tsx       # 仪表盘首页
│   │   │   ├── ResearchCreation.tsx# 创建研究任务
│   │   │   ├── AgentExecution.tsx  # 执行过程实时监控
│   │   │   ├── KnowledgeExplorer.tsx# 论文关系图谱
│   │   │   ├── FinalReview.tsx     # 最终审查与导出
│   │   │   ├── Credentials.tsx     # 凭据管理
│   │   │   └── HistoryDetail.tsx   # 历史任务详情
│   │   └── components/             # 14 个 UI 组件
│   │       ├── Layout.tsx          # 全局布局
│   │       ├── StageTimeline.tsx   # 阶段时间线
│   │       ├── PaperTable.tsx / PaperDetail.tsx / PaperGraph.tsx
│   │       ├── Button.tsx / Card.tsx / Badge.tsx
│   │       ├── Toast.tsx / ConfirmDialog.tsx
│   │       ├── LoadingSkeleton.tsx / EmptyState.tsx / ErrorBoundary.tsx
│   │       └── ...
│   └── package.json
├── tests/                          # 测试套件（27 文件，506+ 测试）
│   ├── conftest.py                 # 全局 fixture（mock_llm, mock_llm_with_tool）
│   ├── test_llm.py                 # LLM 抽象层测试
│   ├── test_state.py               # 状态机测试
│   ├── test_harness.py             # Harness 主循环测试
│   ├── test_pipeline.py            # Pipeline 编排测试
│   ├── test_pipeline_initialization.py / test_pipeline_expand.py
│   ├── test_tools.py               # 工具系统测试
│   ├── test_processing.py / test_retrieval.py / test_auxiliary.py
│   ├── test_guardrails.py          # 守卫系统测试
│   ├── test_memory.py              # 记忆系统测试
│   ├── test_feedback.py            # 反馈系统测试（含多轮迭代）
│   ├── test_latex_repair.py        # LaTeX 修复测试（645 行）
│   ├── test_evidence.py            # 证据层测试（2248 行）
│   ├── test_evidence_citations.py  # 引用测试
│   ├── test_api.py / test_models.py# API 层测试
│   ├── test_config.py / test_prompts.py / test_relevance.py
│   ├── test_credentials.py         # 凭据管理测试
│   ├── test_error_recovery.py      # 错误恢复测试
│   ├── test_demo.py                # 机制演示测试（7 测试）
│   └── test_integration_pipeline.py# 集成测试
├── memory/                         # 运行时数据
│   ├── session/                    # 会话记忆 JSON
│   └── persistent/                 # 持久记忆 SQLite
├── docs/                           # 文档
│   ├── SPEC.md                     # 完整设计规约
│   ├── PLAN.md                     # 实现计划
│   ├── SPEC_PROCESS.md             # 设计过程文档
│   ├── TDD_RECOVERY.md             # TDD 流程补证文档
│   ├── REFLECTION.md               # 项目反思报告
│   └── AGENT_LOG.md                # 关键决策与流程偏离记录
├── .github/workflows/ci.yml        # GitHub Actions CI 配置
├── Dockerfile                      # 多阶段构建（前端 + 后端）
├── Makefile                        # 构建命令
├── .env.example                    # 环境变量模板
├── requirements.txt                # Python 依赖
└── CLAUDE.md                       # 项目全局约束
```

---

## 系统架构

```
Web UI (React 7 页面 + 14 组件)
    │  REST + WebSocket
    ▼
API Layer (FastAPI 7 路由模块)
    │
    ▼
Agent Harness (Python)
    │
    ├── PipelineOrchestrator
    │   PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → COMPLETE
    │
    ├── Tools (5 类别 17+ 工具)
    │   检索 / 后处理 / 写作 / 验证 / 辅助
    │
    ├── Evidence Layer (18 文件)
    │   论断提取 → 引用锚定 → 证据校验 → 知识库 → 表格生成
    │
    ├── Feedback (5 确定性校验器 + 聚合器 + 修复生成器)
    │   Citations / Hallucination / Word Count / Language / Coherence
    │
    ├── Guardrails (5 守卫 + 统一管理器)
    │   Source Filter / Fact Binding / Op Safety / Rate Limit / Output Std
    │
    └── Memory (2 层级)
        Session JSON + Persistent SQLite + Integration Layer
```

### 数据流

```
用户输入主题
    │
    ▼
[PLANNING]     → 拆解任务 → 生成检索策略
    │
    ▼
[RETRIEVAL]    → arxiv_search / semantic_scholar_search / google_scholar_search
    │           → merge_results → dedup → sort_by_citation
    │           Guardrail: 来源过滤 + 速率限制
    ▼
[ANALYSIS]     → 摘要筛选（标记核心论文）
    │           → pdf_download + pdf_parse（仅核心论文）
    │           → 论断提取 → 证据存储 → 引用锚定
    │           Guardrail: 操作安全（下载确认）
    ▼
[WRITING]      → 逐章生成（含证据引用注入）
    │           Guardrail: 事实绑定（每个论断绑定论文 ID）
    ▼
[VALIDATION]   → 5 校验器链
    │           citations → hallucination → word_count → language → coherence
    │           分数 < 70% → 回到 WRITING（最多 3 次）
    │           70-85% → 标记警告
    │           ≥ 85% → 进入 COMPLETE
    ▼
[COMPLETE]     → 最终论文输出 → 更新记忆 → Web UI 跳转 Final Review
```

---

## 测试策略

ScholarAgent 采用 **Mock-LLM 驱动测试**，所有测试不依赖真实 LLM 调用和网络连接：

- **506+ 个测试**，27 个测试文件，全部通过
- **测试运行时间**：~26 秒
- **零外部依赖**：无需网络、无需 API Key、无需 LLM 服务
- **MockLLM**：统一 mock 替换 LLM 抽象层，返回固定结构化响应

### 测试覆盖

| 模块 | 测试文件 | 覆盖内容 |
|------|---------|---------|
| LLM 抽象层 | `test_llm.py` | 流式/非流式调用、错误重试、指数退避 |
| 状态机 | `test_state.py` | 合法/非法状态转换、中断恢复 |
| Harness 主循环 | `test_harness.py` | 全流程调度、状态转换、错误处理 |
| Pipeline 编排 | `test_pipeline*.py` | 多阶段编排、初始化、扩展场景 |
| 工具系统 | `test_tools.py`, `test_*.py` | 5 类别工具的入参/出参/错误分支 |
| 守卫系统 | `test_guardrails.py` | 5 守卫的拦截逻辑、BLOCK/REQUIRE_APPROVAL |
| 记忆系统 | `test_memory.py` | 会话/持久记忆的 CRUD、集成、自动加载 |
| 反馈系统 | `test_feedback.py` | 5 校验器的确定性验证、多轮修正 |
| 证据层 | `test_evidence.py` | 论断提取、引用锚定、证据校验（2248 行） |
| API 层 | `test_api.py`, `test_models.py` | REST 端点 CRUD、WebSocket 推送、数据模型 |
| 凭据管理 | `test_credentials.py` | 安全存储、读取、更新、清除 |
| 错误恢复 | `test_error_recovery.py` | 状态超时、非法操作、异常恢复 |
| 机制演示 | `test_demo.py` | 守卫拦截 + 反馈修正行为的端到端演示 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端语言 | Python 3.11+ |
| API 框架 | FastAPI（自动 OpenAPI 文档） |
| 前端 | React + TypeScript + Vite |
| 持久化 | SQLite + JSON |
| 测试 | pytest + pytest-asyncio + httpx |
| CI | GitHub Actions（3 流水线） |
| 容器化 | Docker 多阶段构建 |
| 凭据管理 | keyring / Windows Credential Manager |
| LLM 供应商 | OpenAI 兼容接口（默认 deepseek-v4-flash） |

---

## 开发约束

- **TDD 强制**：所有代码开发必须遵循 RED → GREEN → REFACTOR 循环
- **机制即代码**：所有守卫、校验器、反馈逻辑必须是代码实现，非 prompt 实现
- **零第三方 Agent 框架**：不使用 LangChain、AutoGen、CrewAI 等
- **API Key 安全**：绝不硬编码，绝不提交 Git

---

## 安全边界

- API Key 通过 `.env` 文件加载（已加入 `.gitignore`）或操作系统凭据管理器存储
- 操作安全守卫拦截 `rm -rf`、`DROP TABLE` 等危险命令
- 速率限制防止 API 滥用（默认 30 次/分钟）
- 来源过滤拒绝低质量来源和黑名单期刊
- 事实绑定确保每个学术论断可追溯至具体文献

---

## 许可证

MIT