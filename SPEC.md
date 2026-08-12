# ScholarAgent — 论文综述智能体

> **AI4SE 期末项目 · Track A · Coding Agent Harness**
>
> 本文件是完整的项目规约（SPEC），由 Superpowers `brainstorming` 技能引导生成。

---

## 1. 问题陈述

### 1.1 要解决什么问题

研究人员和研究生在进入一个新领域或撰写论文文献综述时，面临以下痛点：

- **文献检索耗时**：需要在 arXiv、Semantic Scholar、Google Scholar 等多个平台间切换，手动搜索和筛选论文
- **综述写作门槛高**：高质量的学术综述需要系统性地分类、比较和综合大量文献，对新手极不友好
- **缺乏工具支持**：现有工具（如 Elicit、Connected Papers）只能做检索或可视化，无法端到端生成完整综述
- **格式标准化难**：会议级别的综述（如 IEEEtran 格式）有严格的排版和引用规范

### 1.2 目标用户

- **计算机科学方向的研究人员**：需要快速了解新领域的研究现状
- **研究生**：撰写学位论文中的文献综述章节
- **AI/计算机视觉领域从业者**：跟踪前沿进展

### 1.3 为什么值得做

本项目的核心价值在于：**将「检索 → 分析 → 综合 → 写作」这一完整的学术综述流程自动化**，让用户从数周的手工工作缩短到数小时。同时，作为 Coding Agent Harness 项目，它示范了如何构建一个带治理、反馈、记忆的可靠 agent 系统。

---

## 2. 用户故事

以下用户故事遵循 INVEST 原则（Independent, Negotiable, Valuable, Estimable, Small, Testable）：

| ID | 角色 | 故事 | 验收标准 |
|----|------|------|---------|
| US-1 | 研究人员 | 我可以输入一个研究主题，启动 agent 自动生成一篇 IEEEtran 会议格式的综述论文 | 系统在 30 分钟内输出包含摘要、引言、分类、方法对比、挑战与未来工作的完整综述 |
| US-2 | 研究生 | 我可以在综述生成过程中随时查看进度，并看到 agent 当前在做什么 | Agent Execution 页面实时显示当前步骤（检索/分析/写作/验证），每步有状态标识 |
| US-3 | 研究人员 | 我可以在生成过程中向 agent 提供反馈，要求补充某个子领域的论文或展开某个章节 | 在 Agent Execution 页面输入反馈后，agent 暂停当前任务，执行修正，然后继续 |
| US-4 | 研究生 | 我可以在生成完成后查看质量评分和评估报告，了解综述的覆盖面和引用完整性 | Final Review 页面显示质量评分、引用覆盖率、完整性评分，以及每项检查的通过/警告状态 |
| US-5 | 研究人员 | 系统可以记住我的偏好设置（默认检索源、年份范围、黑名单期刊），下次使用时自动加载 | 新建任务时，偏好设置自动填充；我可以在记忆管理页面查看和修改这些偏好 |
| US-6 | 研究生 | 我可以查看 agent 检索到的论文列表和论文关系图，了解文献脉络 | Knowledge Explorer 页面展示论文关系图和论文列表表格，支持按年份/引用排序 |
| US-7 | 研究人员 | 我可以导出生成的综述为 Markdown 文件，并获取完整的 BibTeX 引用列表 | 在 Final Review 页面提供"导出 Markdown"和"导出 BibTeX"按钮 |

---

## 3. 功能规约

### 3.1 Agent Harness 核心

| 功能 | 描述 | 输入 | 行为 | 输出 | 边界条件 | 错误处理 |
|------|------|------|------|------|---------|---------|
| 主循环 | 基于状态机的 agent 调度器 | 用户任务配置 | 按 PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → COMPLETE 顺序执行 | 完整的 Survey 论文 | 最大重试次数 3 次 | 状态超时回退到 IDLE，记录错误日志 |
| 状态管理 | 管理当前任务状态与转换 | 状态转换事件 | 更新状态机，通过 WebSocket 推送状态变更 | 实时状态更新 | 支持手动中断和恢复 | 非法状态转换拒绝并记录 |
| LLM 抽象层 | 统一 LLM 调用接口，支持 mock 替换 | 系统提示 + 用户消息 + 工具列表 | 调用 LLM，解析响应中的工具调用或文本生成 | 结构化响应或工具调用 | 支持流式/非流式 | 调用失败重试 3 次，指数退避 |

### 3.2 工具系统

| 模块 | 工具 | 描述 | Guardrail 绑定 |
|------|------|------|---------------|
| **检索** | `arxiv_search` | 搜索 arXiv 最新论文 | 速率限制 + 来源过滤 |
| | `semantic_scholar_search` | 搜索 Semantic Scholar 已发表论文 | 速率限制 + 来源过滤 |
| | `google_scholar_search` | 搜索 Google Scholar 补充检索 | 速率限制 + 来源过滤 |
| | `merge_results` | 去重合并多源结果 | — |
| **后处理** | `pdf_download` | 下载论文全文 PDF | 操作安全（需确认） |
| | `pdf_parse` | 解析 PDF 提取全文文本 | — |
| | `dedup_papers` | 按标题/DOI 去重 | — |
| | `sort_by_citation` | 按引用数/年份排序 | — |
| | `format_bibtex` | 生成 IEEEtran 标准 BibTeX | — |
| **写作** | `write_chapter` | 生成单个章节 | 事实绑定 |
| | `expand_paragraph` | 扩展指定段落 | 事实绑定 |
| | `truncate_paragraph` | 精简指定段落 | — |
| | `insert_references` | 自动插入引用列表 | 事实绑定 |
| | `format_ieeetran` | 格式对齐 IEEEtran 模板 | 输出标准化 |
| **验证** | `check_citations` | 检查引用一致性 | — |
| | `detect_hallucination` | 检测无文献支持的论断 | — |
| | `check_word_count` | 统计字数 | — |
| | `polish_language` | 学术语言润色 | — |
| | `check_coherence` | 逻辑连贯性检查 | — |
| **辅助** | `web_search` | 通用网络搜索 | 操作安全 |
| | `check_arxiv_updates` | 定时检查新论文 | — |
| | `shell_exec` | 安全 shell 执行 | 操作安全（需确认） |

### 3.3 记忆系统

| 功能 | 描述 | 存储方式 | 生命周期 |
|------|------|---------|---------|
| 会话记忆 | 存储当前任务：论文元数据、章节草稿、LLM 推理记录、已过滤文献 | JSON 文件 (`memory/session/`) | 任务创建时初始化，完成/手动清除后释放 |
| 持久记忆 | 存储用户偏好：默认检索源、年份范围、黑名单期刊、历史研究领域、写作偏好 | SQLite (`memory/persistent/scholar_memory.db`) | 跨会话持久化，支持查看/更新/清除 |
| 自动加载 | 新任务创建时，持久记忆自动注入到会话记忆 | — | 每次任务启动时 |

### 3.4 反馈系统

| 功能 | 描述 | 触发条件 | 行为 |
|------|------|---------|------|
| 自动校验 | `check_citations` / `detect_hallucination` / `check_word_count` / `polish_language` / `check_coherence` | VALIDATION 状态 | 逐项检查，生成结构化验证报告 |
| 自动修正 | 根据验证报告生成修复指令，回灌到 agent 循环 | 验证分数 < 70% | 回到 WRITING 状态，最多重试 3 次 |
| 人工反馈 | 用户输入三种类型反馈：文献扩展 / 章节调整 / 风格格式 | 用户主动在 UI 输入 | 暂停当前任务，注入反馈，触发修正 |
| 反馈记录 | 所有反馈记录写入持久记忆 | 每次反馈注入 | 写入 SQLite 供后续任务参考 |

### 3.5 守卫系统

| 守卫 | 描述 | 检查逻辑 | 阻断行为 |
|------|------|---------|---------|
| 来源过滤 | 过滤低质量来源和黑名单期刊 | 检查论文来源 URL / 期刊名 | `BLOCK` — 不导入论文 |
| 事实绑定 | 每个论断必须有文献支持 | 提取文本中的论断，检查是否关联论文 ID | `BLOCK` — 强制检索后再写 |
| 操作安全 | 拦截危险文件操作 | 检查命令/操作是否在危险列表 | `REQUIRE_APPROVAL` — 暂停等待用户确认 |
| 速率限制 | 控制 API 调用频率 | 跟踪时间窗口内的调用次数 | `BLOCK` — 等待冷却 |
| 输出标准化 | 防止抄袭和非正式语言 | 文本相似度检测 + 学术语气检查 | `BLOCK` — 重写 |

### 3.6 配置系统

| 功能 | 描述 |
|------|------|
| 声明式配置 | 用户可通过配置文件声明检索源、年份范围、最大论文数、质量阈值等 |
| 默认配置 | 提供合理的开箱即用默认值 |
| 配置覆盖 | 运行时配置可覆盖持久记忆中的默认值 |

---

## 4. 非功能性需求

### 4.1 性能

- 一次完整的综述生成应在 30 分钟内完成
- Web UI 页面加载时间 < 2 秒
- WebSocket 状态推送延迟 < 500ms
- 同时支持至少 1 个并发任务（单用户场景）

### 4.2 安全（凭据威胁模型）

- **LLM API Key**（如 OpenAI / Anthropic）：需要安全存储
- **威胁模型**：
  - Key 硬编码进源码 → 泄露到 Git 历史
  - Key 明文存储在配置文件 → 被其他进程读取
  - Key 出现在终端 history → 被肩窥或日志泄露
- **对策**：
  - Key 绝不硬编码进源码，绝不提交进 Git
  - 使用操作系统凭据管理（Windows Credential Manager / macOS Keychain）
  - 支持 `.env` 文件加载（明确说明明文风险）
  - 首次运行引导用户通过隐藏输入录入 key
  - 提供查看（不回显明文）/ 更新 / 清除 API

### 4.3 可用性

- Web UI 提供直观的 5 页面导航
- 关键操作（启动任务、提供反馈、导出结果）不超过 2 次点击
- 实时进度显示，用户始终知道 agent 正在做什么
- 错误信息清晰可理解，不暴露技术栈

### 4.4 可观测性

- Agent Execution 页面实时显示每个步骤的状态
- AGENT_LOG.md 记录关键决策与人工干预
- 工具执行日志记录入参、出参、耗时

---

## 5. 系统架构

### 5.1 组件图

```
┌─────────────────────────────────────────────────────────────────┐
│                       Web UI (React)                            │
│  Dashboard  │  Research Creation  │  Agent Execution            │
│  Knowledge Explorer  │  Final Review                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │  REST + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                    API Layer (FastAPI)                          │
│  /api/survey  │  /api/progress  │  /api/feedback  │  /api/memory│
│  WebSocket /ws/stream/{task_id}                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Agent Harness (Python)                       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Main Loop                              │  │
│  │  State Machine  →  Dispatch  →  Execute  →  Feedback     │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                                                       │
│  ┌──────▼──────────────────────────────────────────────────┐   │
│  │                    Tools                                 │   │
│  │  Retrieval  │  Post-Process  │  Writing  │  Validation  │   │
│  │  Auxiliary                                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                       │
│  ┌──────▼──────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Memory (2-tier) │  │ Feedback (2L) │  │   Guardrails    │  │
│  │  Session  JSON   │  │ Auto-Valid.  │  │ Source Filter   │  │
│  │  Persistent SQL  │  │ Human Input  │  │ Fact Binding    │  │
│  └──────────────────┘  └──────────────┘  │ Op Safety       │  │
│                                          │ Rate Limit      │  │
│                                          │ Output Std.     │  │
│                                          └─────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 数据流

```
用户输入主题
    │
    ▼
[PLANNING] → Planning Agent 拆解任务 → 生成检索策略
    │
    ▼
[RETRIEVAL] → arxiv_search / semantic_scholar_search / google_scholar_search
    │         → merge_results → dedup → sort_by_citation
    │         Guardrail: 来源过滤 + 速率限制
    ▼
[ANALYSIS] → Stage 1: 摘要筛选（标记核心论文）
    │       → Stage 2: pdf_download + pdf_parse（仅核心论文）
    │       Guardrail: 操作安全（下载确认）
    ▼
[WRITING] → write_chapter（逐章生成）
    │      Guardrail: 事实绑定（每个论断绑定论文 ID）
    ▼
[VALIDATION] → Auto-Feedback 校验器链
    │         check_citations → detect_hallucination → check_word_count
    │         → polish_language → check_coherence
    │         分数 < 70% → 回到 WRITING（最多 3 次）
    │         70-85% → 标记警告
    │         ≥ 85% → 进入 COMPLETE
    ▼
[COMPLETE] → 最终 Survey 存入存储，更新持久记忆
           → Web UI 跳转到 Final Review 页面
```

### 5.3 外部依赖

| 依赖 | 用途 | 鉴权方式 |
|------|------|---------|
| LLM API（OpenAI / Anthropic） | 主循环中的 LLM 调用 | API Key（安全存储） |
| arXiv API | 论文检索 | 无需鉴权（需遵守速率限制） |
| Semantic Scholar API | 论文检索 + 引用数据 | 可选 API Key |
| Google Scholar | 补充检索 | 无需鉴权（需处理反爬） |
| SQLite | 持久记忆存储 | 文件系统权限 |

---

## 6. 数据模型

### 6.1 实体关系

```
Task
├── id: UUID (PK)
├── topic: str
├── keywords: list[str]
├── goal: str
├── max_papers: int
├── status: enum (planning|retrieval|analysis|writing|validation|complete|error)
├── created_at: datetime
├── completed_at: datetime?
└── quality_score: float?

Paper
├── id: UUID (PK)
├── task_id: UUID (FK → Task)
├── title: str
├── authors: list[str]
├── abstract: str
├── year: int
├── source: enum (arxiv|semantic_scholar|google_scholar)
├── url: str
├── pdf_path: str?
├── citation_count: int
├── is_core: bool (是否被标记为核心论文)
├── full_text: str? (仅核心论文有)
└── keywords: list[str]

Chapter
├── id: UUID (PK)
├── task_id: UUID (FK → Task)
├── title: str
├── content: str
├── order: int
├── status: enum (draft|revised|final)
└── word_count: int

ValidationResult
├── id: UUID (PK)
├── task_id: UUID (FK → Task)
├── validator_name: str
├── passed: bool
├── score: float
├── issues: list[str]
├── repair_instructions: str?
├── iteration: int (第几次验证)
└── created_at: datetime

Feedback
├── id: UUID (PK)
├── task_id: UUID (FK → Task)
├── type: enum (auto|human)
├── category: enum (literature|chapter|style)
├── content: str
├── resolved: bool
└── created_at: datetime

UserPreference (持久记忆)
├── key: str (PK)
├── value: str
└── updated_at: datetime
```

### 6.2 约束

- Task 的 `status` 转换遵循状态机定义的合法路径
- Paper 的 `source` 限制为三个枚举值
- ValidationResult 的 `iteration` 最大为 3
- 同一 Task 下 Paper 的 `title` 唯一（去重后）

---

## 7. 凭据与分发设计

### 7.1 凭据安全存储

**支持的存储后端：**

1. **Windows Credential Manager**（Windows 首选）
   - 使用 `win32cred` 或 `keyring` 库访问
   - 凭据存储在用户专属的凭据管理器中，其他用户不可读

2. **环境变量 + `.env` 文件**（备选）
   - 从 `.env` 文件加载（已加入 `.gitignore`）
   - 启动时检查必需 key，缺失时引导用户录入

**支持的凭据：**
- `LLM_API_KEY` — LLM 供应商 API Key
- `SEMANTIC_SCHOLAR_API_KEY` — Semantic Scholar API Key（可选）
- `GOOGLE_SCHOLAR_COOKIE` — Google Scholar 访问 Cookie（可选）

**安全操作流程：**
- 首次运行：检测到 key 缺失 → 提示用户输入（隐藏字符不回显）→ 存储到 Credential Manager
- 运行中：从 Credential Manager 读取 → 注入到环境变量
- 管理：Web UI 提供凭据状态查看（不显示明文）/ 更新 / 清除

### 7.2 分发

**分发形态：Docker 容器**

- `Dockerfile` 构建前后端一体镜像
- 单条 `docker build` + 单条 `docker run` 可启动
- 容器内通过 `.env` 文件或环境变量传入 key
- 推送到公开 registry（Docker Hub / GitHub Container Registry）

**README 说明：**
- 获取方式：`docker pull ...`
- 运行命令：`docker run -p 8000:8000 --env-file .env scholaragent`
- Key 配置方式：在 `.env` 文件中设置，或通过 `-e` 参数传入
- 已知限制：Windows 容器兼容性、依赖外部 API 可用性

---

## 8. 技术选型与理由

| 层 | 技术 | 理由 |
|----|------|------|
| **后端语言** | Python 3.11+ | 丰富的学术库支持（arxiv、PyMuPDF）；LLM SDK 原生支持；课程项目常用语言 |
| **API 框架** | FastAPI | 原生异步支持（适合 I/O 密集型检索任务）；自动 OpenAPI 文档；WebSocket 内置支持 |
| **前端** | React + TypeScript | 丰富的 UI 组件生态；WebSocket 原生支持；适合构建实时进度展示页面 |
| **前端设计系统** | Open Design | 课程推荐；提供开箱即用的组件库 |
| **LLM 供应商** | OpenAI / Anthropic | 任选其一或两者都支持；通过 LLM 抽象层可切换 |
| **持久化** | SQLite | 零配置；单用户场景足够；Python 标准库内置 |
| **PDF 解析** | PyMuPDF (fitz) | 高精度文本提取；支持批量处理 |
| **容器化** | Docker | 跨平台分发；课程推荐格式 |
| **CI** | GitHub Actions | 自动运行测试；可构建 Docker 镜像 |
| **凭据管理** | keyring | 跨平台凭据管理器接口；支持 Windows Credential Manager |

---

## 9. 领域与机制设计

> 本节是 Track A（Coding Agent Harness）的额外要求，参见 §A.5。

### 9.1 领域分析：学术综述生成

ScholarAgent 的领域是**学术文献综述自动化**，属于"知识密集型写作"场景。该领域的关键特征：

- **信息可信度至关重要**：综述中的每个论断必须可追溯至具体文献，幻觉直接影响学术可信度
- **反馈信号客观明确**：引用匹配、字数统计、格式合规等都有确定的判定标准
- **危险操作边界清晰**：批量文件删除、数据库清空、大量 API 调用等风险可提前识别
- **记忆需求分层**：单次任务的上下文（会话级）与用户偏好（持久级）天然分离

### 9.2 四类机制设计

#### 动作/工具

领域所需的工具分为五类（详见 §3.2），通过统一的 `Tool` 接口注册到 harness：

```python
class Tool(ABC):
    name: str
    description: str
    guardrails: list[Guardrail]

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult: ...
```

每个工具是**独立的纯函数模块**，可脱离 LLM 进行单元测试。

#### 客观反馈信号

本领域的反馈信号具有**客观、确定、可编码**的特点：

| 反馈信号 | 校验器 | 判定方式 | 可回灌 |
|---------|--------|---------|-------|
| 引用一致性 | `check_citations` | 解析文本中的 `[@id]` 标记，检查是否在论文列表中存在 | ✅ 生成修复指令 |
| 事实幻觉 | `detect_hallucination` | 提取每个论断，检查是否至少关联一个论文 ID | ✅ 强制检索后再写 |
| 字数合规 | `check_word_count` | 统计每个章节字数 | ✅ 提示扩展/精简 |
| 学术语言质量 | `polish_language` | 检测非正式表达、语法问题 | ✅ 提供修改建议 |
| 逻辑连贯性 | `check_coherence` | 检查章节间过渡和段落间逻辑连接 | ✅ 提示结构调整 |

#### 危险动作

| 危险动作 | 拦截条件 | 处理方式 |
|---------|---------|---------|
| 批量文件删除 | 命令匹配 `rm -rf`、`del /F` 等模式 | `REQUIRE_APPROVAL` — 暂停并等待用户确认 |
| 数据库清空 | 检测到 `DROP TABLE`、`DELETE FROM` 无 WHERE 条件 | `REQUIRE_APPROVAL` |
| 大量 API 调用 | 1 分钟内调用超过 30 次 | `BLOCK` — 等待冷却 |
| 大规模下载 | 单次下载超过 50 篇 PDF | `REQUIRE_APPROVAL` |

#### 记忆需求

| 层级 | 内容 | 存储 | 加载时机 |
|------|------|------|---------|
| 会话级 | 当前任务的论文元数据、章节草稿、LLM 推理记录 | JSON 文件 | 任务初始化时 |
| 持久级 | 用户偏好、黑名单、历史任务 | SQLite | 应用启动时 |

### 9.3 重点维度：反馈闭环

**选择理由：** 学术综述生成对**事实准确性**和**引用完整性**要求极高，一个健壮的反馈闭环是确保输出质量的关键。反馈闭环的五个校验器（citation / hallucination / word count / language / coherence）天然适合用**确定性代码**实现，完美契合 §A.4 的"机制必须是代码"要求。

**深入实现计划：**

1. **校验器基类**：定义 `Validator` 抽象基类，所有校验器继承自它
2. **五个确定性校验器**：每个校验器接收写作产物 → 解析 → 输出结构化 `ValidationResult`（含分数、问题列表、修复指令）
3. **反馈聚合器**：收集所有校验器结果 → 计算综合分数 → 判定 PASS / WARN / FAIL
4. **修复指令生成器**：根据 FAIL 的校验器，生成结构化修复指令，回灌到 agent 主循环
5. **多轮迭代控制**：跟踪重试次数，超过 3 次则强制终止，避免无限循环
6. **Mock-LLM 测试套件**：每个校验器可独立测试（输入撰写产物 → 断言输出评分和问题列表）

---

## 10. 验收标准

| 功能 | 验收标准 |
|------|---------|
| Harness 主循环 | 给定一个 mock LLM（返回固定响应），主循环能按 PLANNING → RETRIEVAL → ANALYSIS → WRITING → VALIDATION → COMPLETE 顺序执行，每次状态转换可验证 |
| 工具分发 | 5 个工具类别的每个工具注册到 harness 后，可通过名称调用并返回正确结果 |
| 记忆系统 | 会话记忆在任务内持久化；持久记忆在重启后仍可读取 |
| 反馈闭环（重点） | 5 个校验器均可用确定性输入验证；注入失败时可自动触发修正；重试 3 次后停止 |
| 守卫系统 | 4 类守卫均可用 mock 动作验证其拦截逻辑；操作安全守卫可正确暂停并等待确认 |
| Web UI | 5 个页面均可正常渲染；Agent Execution 页面实时显示进度；Final Review 页面展示完整综述 |
| 凭据管理 | 首次运行引导录入 key；key 不硬编码、不提交 Git；提供查看/更新/清除功能 |
| 分发 | `docker build` 成功构建；`docker run` 可启动；README 写清运行步骤 |

---

## 11. 风险与未决问题

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Google Scholar 反爬机制 | 检索失败或 IP 被封 | 将其作为最后备选，控制请求频率，支持用户配置 Cookie |
| LLM 输出质量不稳定 | 综述质量波动 | 反馈闭环的校验器可捕获大部分质量问题并触发修正 |
| PDF 解析质量差 | 部分论文解析不完整 | 对解析失败的论文降级为摘要级分析 |
| 长上下文下 LLM 性能下降 | 综述后半部分质量下降 | 分章节写作 + 各章节独立验证 |
| 课程要求中的"冷启动"验证 | 发现 spec 缺陷需要修改 | 在 PLAN 阶段预留修订时间 |

---

## 附录 A：与课程要求的对应关系

| 课程要求 | 对应章节 | 说明 |
|---------|---------|------|
| §A.1 什么是 Harness | §3.1, §5 | 决策封装、工具、记忆、治理、反馈、配置六维度 |
| §A.2 Coding Agent Harness | §9 | 学术综述领域的工具、反馈、守卫设计 |
| §A.3 四类机制 | §9.2 | 动作/工具、反馈信号、危险动作、记忆 |
| §A.4 实现边界 | §9.3 | 机制为代码，可 mock 测试 |
| §A.4-D 重点维度 | §9.3 | 反馈闭环（Feedback）为深入维度 |
| §A.5 SPEC 额外要求 | §9 | 领域与机制设计 |
| §A.6 测试要求 | §10, 附录 B #12 | mock-LLM 单元测试 + 机制演示 |
| §3.1 凭据安全 | §7.1 | 凭据威胁模型与对策 |
| §3.2 分发 | §7.2 | Docker 容器分发 |
| §4.2 交付物清单 | 本文件 + PLAN.md + SPEC_PROCESS.md 等 | 见附录 B |

## 附录 B：交付物清单

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | `SPEC.md` | 本文件 — 设计规约 |
| 2 | `PLAN.md` | 实现计划（由 writing-plans 技能生成） |
| 3 | `SPEC_PROCESS.md` | 过程文档（brainstorming 关键节点、3 轮迭代、冷启动结果） |
| 4 | 完整源代码 | 自编码 harness 内核 + ScholarAgent 应用 + mock-LLM 测试 |
| 5 | 分发产物 | Dockerfile + 构建脚本 |
| 6 | `README.md` | 项目简介、安装、运行、分发、目录结构、安全边界 |
| 7 | `AGENT_LOG.md` | 时间顺序的关键节点记录 |
| 8 | CI 配置（`.github/workflows/`） | 包含 unit-test job |
| 9 | CI/CD 执行记录 | 最后一次为 pass 状态 |
| 10 | `REFLECTION.md` | 1500-2500 字反思报告 |
| 11 | 线上部署 URL | 可访问的 Web UI 地址 |
| 12 | 机制演示 | mock-LLM 下复现守卫拦截 + 反馈修正 + 重点维度行为 |