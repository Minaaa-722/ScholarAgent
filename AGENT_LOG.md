# AGENT_LOG — 关键决策与人工干预记录

> 按时间顺序记录 ScholarAgent 项目开发过程中的关键决策、架构变更、bug 修复和人工干预节点。

---

## ⚠️ 标准流程偏离说明

### 偏离原因

项目初始化时（2026-07-20），我未仔细阅读课程作业的 AI4SE 通用要求文档，未注意到 §3.6 强制要求全开发流程执行 TDD（红-绿-重构：先写失败测试、再写最小实现、最后重构）。项目初始设置中，`settings.json` 未配置全局 `test-driven-development` 强制开关，导致所有历史开发任务均未走标准 TDD 循环。

### 实际违规流程

所有历史任务（Task 1—Task 13）均采用以下不合规流程：
```
SPEC 定义 → PLAN 规划 → subagent 实现业务代码 → 事后补充测试
```
而非标准 TDD 流程：
```
编写失败测试(RED) → 最小实现代码(GREEN) → 重构优化(REFACTOR)
```

### 本次全部补救动作清单

| # | 补救动作 | 状态 | 涉及文件 |
|---|---------|------|---------|
| 1 | 全覆盖单元测试补全 — 新增 119 个测试，覆盖证据层引用/表格/辅助工具/凭据API模块 | ✅ 完成 | `tests/test_evidence_citations.py`, `test_auxiliary.py`, `test_credentials.py` |
| 2 | 新增 TDD_RECOVERY.md 流程补证文档，按模块还原 RED→GREEN→REFACTOR 流程 | ✅ 完成 | `TDD_RECOVERY.md` |
| 3 | 优化 Makefile，增加 test-all/test-unit/test-ci/coverage 多目标 | ✅ 完成 | `Makefile` |
| 4 | 检查 CI 配置，确认 unit-test job 完整可用 | ✅ 完成 | `.github/workflows/ci.yml` |
| 5 | 更新 AGENT_LOG.md 补充偏离记录 | ✅ 完成 | 本文件 |
| 6 | 修正 PLAN.md 添加 TDD 验证步骤 | ✅ 完成 | `PLAN.md` |
| 7 | 更新 REFLECTION.md 写作素材 | ✅ 完成 | `REFLECTION.md` |
| 8 | 配置 CLAUDE.md 开启 TDD 强制规则 | ✅ 完成 | `CLAUDE.md` |

### 后续规范

**从本记录起，剩余未开发任务（或未来迭代任务）必须手动调用 `/test-driven-development` 指令执行**，严格遵守 TDD 循环：
1. 先编写该任务对应失败测试用例（RED）
2. 编写最小实现代码使测试通过（GREEN）
3. 在不破坏测试前提下重构代码（REFACTOR）

仅纯静态配置、简单 UI 页面可豁免，豁免必须在 AGENT_LOG 标注理由。

---

## 2026-07-20

### 项目初始化：Brainstorming 与 SPEC 编写

- **决策**：确定采用 6 维度 Harness 架构（决策封装、工具、记忆、治理、反馈、配置）
- **决策**：选择反馈闭环（Feedback Loop）作为深入维度（§A.4-D）
- **决策**：确定技术栈为 Python + FastAPI + React + TypeScript + SQLite
- **产出**：`SPEC.md` — 包含 7 个用户故事、完整功能规约、数据模型、架构图

## 2026-07-21

### Task 1: 项目脚手架 + LLM 抽象层

- **决策**：LLM 抽象层采用 `LLMBase` 抽象基类 + `MockLLM` 测试替身 + `OpenAILLM` 真实实现的三层结构
- **决策**：`MockLLM` 支持固定文本响应和固定工具调用两种模式，便于测试
- **决策**：`conftest.py` 提供全局 `mock_llm` 和 `mock_llm_with_tool` 两个 fixture
- **测试**：4 个测试全部通过

### Task 2: 状态机 + Agent Harness 主循环

- **决策**：状态机采用显式转换表，定义所有合法状态转换路径
- **决策**：支持中断/恢复机制，`INTERRUPTED` 状态可返回任意之前的活跃状态
- **决策**：`HarnessConfig` 包含 `max_papers`, `max_retries`, `quality_threshold`, `year_start`, `year_end` 等配置项
- **测试**：6 个状态机测试 + 4 个 Harness 测试全部通过

## 2026-07-22

### Task 3: 工具系统

- **决策**：5 类工具（检索、处理、写作、验证、辅助）共 17 个工具
- **决策**：论文去重逻辑提取为 `_dedup_by_title` 共享函数，同时被 `MergeResults` 和 `Dedup` 复用（DRY 原则）
- **测试**：8 个工具测试全部通过

### Task 4: 守卫系统

- **决策**：三个守卫裁定级别：`PASS` / `BLOCK` / `REQUIRE_APPROVAL`
- **决策**：`OpSafety` 使用正则模式匹配检测危险命令，如 `rm -rf`、`DROP TABLE` 等
- **决策**：`RateLimit` 基于时间窗口滑动计数，按 action 名称独立统计
- **问题**：`OpSafety` 的 `action` 变量在 1e7777c 中修复（未使用变量）
- **测试**：10 个守卫测试全部通过

## 2026-07-23

### Task 5: 记忆系统

- **决策**：双层级记忆架构 — 会话级 (JSON) 存储当前任务上下文，持久级 (SQLite) 存储跨会话用户偏好
- **决策**：`PersistentMemory` 使用 `:memory:` 数据库进行测试，隔离测试数据
- **测试**：12 个记忆测试全部通过

### Task 6: 反馈系统 — 校验器（重点维度）

- **决策**：5 个确定性校验器，全部用纯代码实现，不依赖 LLM
- **决策**：`LanguagePolisher` 使用正则匹配检测非正式表达，两个 bug 修复：
  - 1e7777c: 修复 `LanguagePolisher` 中 `r'\b basicially \b'` → `r'\bbasically\b'`（两端空格导致匹配失败）
  - 1e7777c: 修复 `r'\b things? \b'` → `r'\bthings?\b'`（两端空格导致匹配失败）
  - 4968b7e: 修复 `OutputStandard` 中 `r'\b basically \b'` → `r'\bbasically\b'`（同上）
- **测试**：16 个校验器测试全部通过

### Task 7: 反馈聚合器 + 修复生成器 + 多轮迭代

- **决策**：`FeedbackAggregator` 计算平均分，低于阈值则触发修正
- **决策**：`RepairGenerator` 聚合所有失败校验器的修复指令
- **决策**：Harness 的 `inject_feedback` 方法集成多轮迭代控制，最多重试 3 次
- **决策**：超过最大重试次数后标记 `has_warnings=True` 并进入 COMPLETE
- **测试**：7 个新增测试全部通过，总测试数 67

## 2026-07-24

### Task 8: API 层

- **决策**：FastAPI 框架，CORS 全开（开发环境）
- **决策**：4 个路由模块（survey, feedback, progress, memory）
- **决策**：WebSocket 端点 `/ws/stream/{task_id}` 用于实时进度推送
- **决策**：API 测试使用 `dependency_overrides` 注入 mock harness
- **测试**：5 个 API 测试全部通过，总测试数 72

### Task 9: Web UI 脚手架

- **决策**：React + TypeScript + Vite 技术栈
- **决策**：5 页面路由（Dashboard、ResearchCreation、AgentExecution、KnowledgeExplorer、FinalReview）
- **决策**：Vite 代理配置将 `/api` 请求转发到 FastAPI 后端
- **决策**：Dashboard 和 ResearchCreation 页面有完整功能实现，其余 3 页为功能骨架

## 2026-07-26

### 全仓库验收

- **验证**：70 个测试全部通过（测试数从 72 调整为 70，因 `test_demo.py` 未创建）
- **发现**：6 个交付物缺失（Dockerfile、README.md、AGENT_LOG.md、REFLECTION.md、SPEC_PROCESS.md、CI 配置）
- **行动**：补充所有缺失交付物
- **状态**：项目验收完成

## 2026-07-27

### Task 10: 错误恢复管线

- **决策**：添加 `ERROR → PLANNING|RETRIEVAL|ANALYSIS|WRITING|VALIDATION` 状态转换（commit: b3adbc1）
- **决策**：`_retry_on_error` 实现阶段级重试，重置当前阶段而非整个管线（commit: 594670f）
- **决策**：`restart()` 方法实现一键重启，清空所有中间产物（commit: 594670f）
- **决策**：`POST /api/survey/restart` 端点 + `restartSurvey()` 前端客户端函数（commits: a6c7ffd, f3bb9a6）
- **决策**：WebSocket 在 `ERROR` 状态下保持流式推送（commit: 682ca34）
- **决策**：前端错误面板 — AgentExecution 页显示重试信息和一键重启按钮（commit: 9307f97）
- **决策**：Dashboard 和 FinalReview 页添加错误状态显示和重启按钮（commits: 3adf6bc, 6433d16）
- **测试**：新增 `tests/test_error_recovery.py` + `tests/test_latex_repair.py`（commits: 420f197, dacc2a8）
- **修复**：API 测试稳定性 — 接受 `PLANNING|RETRIEVAL` 竞态，设置 `_pipeline_running`（commit: 05d9687）
- **测试**：总测试数 72 → 82

### Phase 1: 前端重构

- **决策**：设计系统基础 — 可复用组件库（Button, Card, Input, Modal, Badge, Spinner 等）（commit: b4d7db4）
- **决策**：`useWebSocket` hook 实现指数退避重连（commit: cb5bef8）
- **决策**：AgentExecution 增强 — 实时反馈面板、反馈历史、结构化执行详情（commit: 91f4d86）
- **决策**：FinalReview 增强 — 质量分数、BibTeX 导出、分节评审（commit: 4dbba16）
- **决策**：ResearchCreation 增强 — 偏好自动加载和表单验证（commit: 8c622c5）
- **决策**：Dashboard 增强 — 新手引导、功能卡片、设计系统风格（commit: fe5f315）
- **决策**：新增 Memory Manager 页面 — CRUD 操作用户偏好（commit: 75080f2）
- **决策**：新增 Credential Management 页面 — API 密钥管理（commit: c78087b）
- **决策**：Harness 紧致化 — 减少冗余状态参数、简化转换逻辑（commit: d78defb）

### 知识探索器（Knowledge Explorer）完整实现

- **决策**：三栏布局 — PaperTable（可排序/搜索）+ PaperGraph（D3.js 力导向引用图）+ PaperDetail（元数据显示）（commits: b13bd2b, b900319, 41519fd, 64b22a2）
- **决策**：新增论文列表/图谱/详情 API 端点（commit: 965b175）
- **决策**：CSV 导出功能（commit: a18086c）

### 执行阶段时间线（StageTimeline）

- **决策**：`StageTimeline` 组件 — 每阶段产物卡片 + 脉冲动画（commits: 546bb57, 0881c0f）
- **决策**：集成到 AgentExecution 页面（commit: ee0f7cd）
- **决策**：骨架屏替换为默认着陆页（commit: 3de7f37）
- **决策**：阶段产物立即可见，无需等待阶段完成（commit: e48d012）
- **决策**：实时同步所有 orchestrator 状态（commit: 0bc938e）
- **决策**：产物显示改进 — 去除 markdown 包装、显示完整内容、添加论文链接（commits: d701987, 30ad58a, 51126dd）

### 历史记录 API 与详情页

- **决策**：`HistoryItem` / `HistoryDetail` Pydantic 模型，含 UUID、论文列表和最终论文存储（commits: d7d0276, b67bf98, 36502f2）
- **决策**：`POST /api/history/list` 和 `GET /api/history/{id}` 路由（commit: a00f6ec）
- **决策**：前端 history API 类型和客户端函数（commit: 1fc5a0d）
- **决策**：Dashboard 历史列表区域（commit: 9ec8d50）
- **决策**：HistoryDetail 页面 — 论文列表和分节查看器（commits: 935bfce, dbcf98a）

## 2026-07-28

### 论文搜索质量改进 v2

- **决策**：`_search_seeds()` 从 `_retrieve_papers()` 提取为独立方法（commit: c4ff95f）
- **决策**：`CompositeRanker` — 多因子论文排序（引用数、年份、会议等级）（commit: 865d4f3）
- **决策**：`RelevanceFilter` — LLM 相关性评分（commit: 34110bc）
- **决策**：`CitationExpander` — 引用网络扩展（commit: 7a9b3bf）
- **决策**：`VenueLookup` — DBLP 会议等级检测（commit: feb83ca）
- **决策**：注册 4 个新工具到 Harness（commit: a2b1a47）
- **测试**：新增 `tests/test_relevance.py`、`tests/test_citation.py`、`tests/test_venue.py`、`tests/test_processing.py`、`tests/test_pipeline.py`（commit: 13859ee）
- **修复**：max_papers 数据流从前端到搜索管线全线贯通（commit: be0999a）
- **合并**：commit 888cec0

### 前端 UI 修复

- **规划卡片样式**：规划卡片与分析卡片对齐 — DOM 结构、CSS、滚动逻辑统一（commits: ad38900, bab4b06, f76a59f）
- **Dashboard 网格布局**：历史卡片从列表改为 CSS Grid 3 列布局（commits: 65a2efa, 9f4f0d9）
- **4 个滚动/布局 bug**：卡片 flex 容器、论文列表滚动、时间线溢出修复（commit: f4b58ee）
- **论文 URL 缺失**：`CitationExpander` 字段列表 + 回退机制（commit: 7f2cf3d）
- **重试阶段 bug**：成功重试后重置 `current_stage`（commit: efe0335）
- **管线重试状态**：时间线显示正确的失败阶段而非全部完成（commit: 6e72eac）

### 取消任务功能

- **决策**：`CANCELLED` 状态加入状态机（commit: 78faa33）
- **决策**：`cancel()` 方法 — 带数据清理（commit: 3e068e8）
- **决策**：`POST /api/survey/cancel` 端点（commit: 97a3bbf）
- **决策**：`cancelSurvey()` 前端客户端函数（commit: 2f3f80c）
- **决策**：移除 Pause/Resume 按钮（commit: ffc8f52）
- **决策**：Dashboard 和 HistoryDetail 显示 cancelled 徽章和清空时间线（commits: 499a690, 8bcd874）
- **决策**：取消后重置为空白初始状态（commit: ab8ef82）
- **决策**：LLM 超时从 60s 增加到 180s，添加 `LLM_TIMEOUT` 环境变量（commit: c5eb9c6）
- **修复**：3 个交互 bug — 页面状态、取消按钮行为、时间线重置（commit: d06083b）

### max_papers 数据流修复

- **问题**：`cancel()` 后中断事件未重置，阻塞新管线启动（commit: 4780353）
- **问题**：Pause/Resume 按钮损坏，interrupt 事件在 `start()` 中未正确清理（commit: 07bd55e）
- **问题**：max_papers 未从 API 请求传递到论文搜索（commit: b3fed92）
- **修复**：全线修复 max_papers 数据流，确保前端设置传递到后端管线

## 2026-07-29

### 证据层（Evidence Grounding Layer）建设

#### 架构设计
- **决策**：证据层整体架构规范文档（commit: e12e127）
- **决策**：3 层架构 — 存储层（Stores）、提取层（Extractors）、检索层（Retrievers）

#### PDF 层（16:33）
- **决策**：`EvidenceReference` — 证据引用数据模型
- **决策**：`PDFParser` — PDF 解析器，提取论文段落和引用
- **决策**：`EvidenceExtractor` — 证据提取器，从 PDF 段落中提取结构化证据
- **测试**：`tests/test_evidence.py`
- **产出**：`agent/evidence/evidence_reference.py`, `agent/evidence/evidence_extractor.py`（commit: 0d4dc1a / 5034558）

#### 存储层（16:45）
- **决策**：`BenchmarkStore` — 基准测试结果存储，管理数据集/指标/结果
- **决策**：`PaperKnowledgeBase` — 论文知识库，存储论文关键发现和方法
- **产出**：`agent/evidence/benchmark_store.py`, `agent/evidence/paper_knowledge.py`（commit: 8e3b2f0 / 60718f3）

#### 提取层（16:52）
- **决策**：`BenchmarkExtractor` — 从论文中提取基准测试结果
- **决策**：`BenchmarkVerifier` — 验证基准测试结果的一致性
- **决策**：`PaperAnalyzer` — 论文分析方法，提取关键发现和贡献
- **产出**：`agent/evidence/benchmark_extractor.py`, `agent/evidence/paper_analyzer.py`（commit: cd105ea / 4b4b00a）

#### 检索层（17:04）
- **决策**：`ContextRetriever` — 上下文检索器，按查询维度检索相关证据
- **决策**：`EvidenceRanker` — 证据排序器，按相关性/重要性排序
- **决策**：`EvidenceContextBuilder` — 上下文构建器，组装证据上下文
- **产出**：`agent/evidence/context_retriever.py`（commit: a760fef / a226456 / 6236f0d）

#### 校验层（17:23）
- **决策**：`EvidenceChecker` 增强 — 3 存储校验（BenchmarkStore, PaperKnowledgeBase, CitationStore）
- **产出**：合并到 `agent/evidence/evidence_checker.py`（commit: dd8b7df / e6e8e18）

#### 管线集成（17:59）
- **决策**：证据层集成到 PipelineOrchestrator（commit: 122bea0）
- **修复**：证据层集成后的冲突解决（commits: f077923, 27bfe2e, 8bbf216）

### 引文完整性层（Citation Integrity Layer）

- **决策**：Phase 2 设计规范文档（commit: 2f23aa7）
- **决策**：`CitationStore` — 引文存储，管理论文引用关系
- **决策**：`CitationAnchorStore` — 引文锚点存储，管理引用位置
- **决策**：`CitationInjector` — 引文注入器，在论文中插入引用标记
- **决策**：`TableGenerator` — 表格生成器，从结构化数据生成对比表格
- **产出**：`agent/evidence/citation_anchor_store.py`, `agent/evidence/citation_injector.py`, `agent/evidence/citation_store.py`, `agent/evidence/table_generator.py`（commit: a37d72f）
- **实现**：引文完整性层实现（commits: 088fcb3, 5a0d889）

### 论文验证与证据获取层

- **决策**：`PaperStatus` / `EvidenceLevel` / `PaperAvailability` / `ClaimType` / `EvidenceSource` 类型系统（commit: 30fd6b2）
- **决策**：`evidence_level` 支持添加到 Claim 数据存储（commit: d0e8faf）
- **决策**：`PaperAvailabilityValidator` — 论文可用性验证器（commit: a4b576f）
- **决策**：`processing.py` 增强 — URL 标准化、arXiv 状态检查、超时机制（commit: 49e2649）
- **决策**：`EvidenceAcquisitionRouter` — 证据获取路由（commit: fbff211）
- **决策**：`PAPER_VALIDATING` 和 `EVIDENCE_ACQUIRING` 状态加入状态机（commit: 06e36cb）
- **决策**：`EvidenceChecker` 增强 — evidence-level 检查和空存储警告（commit: e0c5178）
- **测试**：`tests/test_paper_types.py`, `tests/test_paper_validator.py`, `tests/test_evidence_acquisition.py`, `tests/test_paper_validation_integration.py`（commits: 30fd6b2, a4b576f, fbff211, f1de373）

### Pipeline 初始化修复

- **问题**：PipelineOrchestrator 中 `CitationAnchorStore` 依赖未初始化
- **修复**：证据层依赖在 PipelineOrchestrator 中显式初始化（commit: 3c70ea5）
- **测试**：`tests/test_pipeline_initialization.py`
- **测试**：总测试数 82 → 100+

## 2026-08-08

### 清理与修复

- **决策**：Dashboard 历史列表改为 CSS Grid 响应式布局（commit: 310aa67）
- **修复**：Execution 页面取消按钮正确停止管线并重置页面（commit: fd898be）
- **修复**：`cancel()` 后中断事件未重置，阻塞新管线启动（commit: 4780353）
- **修复**：移除损坏的 Pause/Resume 按钮，修复 `start()` 中的 interrupt 事件（commit: 07bd55e）
- **修复**：max_papers 从 API 请求传递到论文搜索（commit: b3fed92）
- **删除**：MemoryManager 页面移除（commit: fc1cdc0）

## 2026-08-09

### 执行进度增强

- **决策**：`stage_messages` 和 `stage_metrics` 字段添加，用于逐阶段进度追踪（commit: 05d1902）
- **决策**：5 个管线阶段添加粒度化进度消息：
  - 计划生成（commit: 5442384）
  - 论文检索和 PDF 提取（commit: 7b9f1d2）
  - 论文分析（commit: 30a5431）
  - 写作、格式修复和验证（commit: cdec56c）
- **决策**：Harness 向 API 响应传播 `stage_messages` 和 `stage_metrics`（commit: a598fea）
- **决策**：Web 前端传递并在 StageTimeline 中渲染进度消息和指标（commits: be11e58, 0a4d8cd）
- **设计文档**：执行页面进度增强设计规范和实现计划（commits: 9224afd, 8a9395e）

### max_papers 限制调整

- **决策**：默认 `max_papers` 从 20 增加到 50，搜索限制解耦（commit: ab66972）
- **修复**：CLI 传递 `--max-papers` 参数到 `harness.run()`（commit: 2c3e10c）
- **修复**：用户 `max_papers` 传播到 `HarnessConfig`，使 PipelineOrchestrator 使用（commit: d41c5c1）

## 2026-08-11

### 管线性能优化

- **决策**：并行化搜索、PDF 处理和声明验证（commit: da8ec13）
- **决策**：移除 `max_pdf_papers` — `max_papers` 作为 PDF 下载数量的唯一真实来源（commit: 43f761a）
- **修复**：尊重用户从 `TaskInfo` 而非 `HarnessConfig` 中设置的 `max_papers`（commit: 1a67332）

### 修复：机制演示文件

- **问题**：`tests/test_demo.py` 从未创建，导致课程要求 A.6 的机制演示缺失
- **行动**：创建 `tests/test_demo.py`，包含 7 个测试用例，覆盖三个必备演示：
  1. **守卫拦截**：`OpSafety` 拦截 `rm -rf /` 返回 `REQUIRE_APPROVAL`；`RateLimit` 在超限后 `BLOCK`
  2. **反馈闭环**：`Harness.inject_feedback` 使状态从 `VALIDATION` 回退到 `WRITING`；超限重试后进入 `COMPLETE` 并标记警告
  3. **重点维度确定性行为**：5 个校验器 + `FeedbackAggregator` + `RepairGenerator` 在已知输入上产生确定性结果
- **验证**：全部 7 个测试通过（0.66s），不依赖网络与真实 LLM
- **总测试数**：265 → 272
- **产出**：`tests/test_demo.py`（commit: 70bd705）

### 修复：CI job 名称

- **问题**：CI 中 job 名为 `test`，但课程要求必须命名为 `unit-test`
- **行动**：将 `.github/workflows/ci.yml` 第 10 行的 `test:` 改为 `unit-test:`
- **产出**：commit: c9d2cf1

## 2026-08-12

### 前端全面设计改造

- **决策**：完整前端设计改造 — 统一设计语言、视觉风格、组件一致性（commit: 458d070）
- **工作树**：`worktree-frontend-design-overhaul`

### 人工反馈机制修复

- **问题**：3 个 bug 导致人工反馈机制无法正常工作
  - Bug 1: `self._papers` 被 `_retrieve_papers` 覆盖，反馈补充的论文丢失
  - Bug 2: 反馈合并逻辑错误，新旧论文数据冲突
  - Bug 3: PDF 提取证据未在分析中体现
- **修复**：
  - 回退 `self._papers` 护栏覆写，改用合并策略（commit: c4e6b74）
  - 在 `_retrieve_papers` 覆盖前保留反馈补充的论文（commit: 1d087ef）
  - 使用 PDF 提取证据丰富分析，增加写作提示限制（commit: 9370806）
- **产出**：commit 22450c4, 1d087ef, c4e6b74, 9370806

### 论文搜索质量改进 v3

- **决策**：多策略搜索 — 主题直接 + 引用排序 + 领域编码修复（commit: 0f8baa4）
- **决策**：arXiv 标题搜索 + LLM 相关性过滤 + 最小引用数过滤（commit: 5f0320d）
- **决策**：`year_start`/`year_end` 从 API 传递到搜索管线（commit: d9d48e5）
- **决策**：多策略查询、API 过滤器、综述引用扩展（commit: 5bd338b）
- **工作树**：`worktree-improve-search-quality`, `worktree-search-quality-fix`

### IEEEtran 迁移

- **决策**：从 CVPR/计算机视觉领域迁移到 IEEEtran/CS-AI 通用领域（commit: 8fb7dc3）
- **决策**：UI 中显示完整计划文本而非截断预览（commit: 8146312）
- **修复**：`markdownToHtml` 中未定义文本导致前端崩溃（commit: a124db8）

## 2026-08-13

### 论文搜索质量稳定化

- **决策**：LLM 查询生成、相关性过滤器和回退机制稳定论文搜索质量（commit: 3a6af0b）
- **工作树**：`worktree-search-quality-fix`

### 统一论文数据模型与检索重构

- **设计**：统一论文数据模型规范 + 模块接口文档（commits: cbfe8af, 381c738）
- **决策**：`Paper` dataclass 添加 `to_dict`/`from_dict`（commit: 8abe6a1）
- **决策**：`SearchConfig` dataclass 添加 `domain_cat_map`（commit: 81fd0df）
- **决策**：LLM 提示词 — 搜索查询生成和相关性判断（commit: 76aa723）
- **决策**：`auto_quote_terms`（Fix 1）、`infer_arxiv_category`（Fix 2）、双通道 arXiv 搜索（commit: e381f28）
- **决策**：`FallbackManager` 添加 phase6/phase7 回退策略（commit: ff235a8）
- **决策**：`rank_papers` — RRF 融合和复合评分（commit: 6f5d8bf）
- **决策**：`RelevanceFilter` 重构 — 3 级 + 置信度评分（commit: b89a4fe）
- **决策**：管线 `_retrieve_papers` 重构为新模块（commit: b41abdc）
- **决策**：`MergeResults` 合并命中通道 + 修复去重排序（commit: 7b319df）
- **决策**：`__init__.py` 导出 + 检索管线集成测试（commit: 1870757）
- **决策**：Phase A 方法论 + Phase B 查询、分段语义搜索、分层抽样（commit: fd763df）
- **决策**：按贡献类型加权、指数衰减、分层抽样（commit: 7768d74）
- **决策**：`RelevanceFilter` 重构 — 4 级贡献类型（commit: a90f55d）
- **决策**：分段搜索和回退综述查询（commit: 7b0acfd）
- **决策**：`METHODOLOGY_QUERY_PROMPT`、`RELEVANCE_JUDGE_PROMPT` 更新为 4 级贡献类型（commit: 3200b49）
- **决策**：`Paper` 添加 `contribution_type` 字段（commit: 67d5a77）
- **决策**：配置添加 year-segment、贡献权重、衰减和分层字段（commit: b0106fe）
- **测试**：新增 `tests/test_models.py`、`tests/test_config.py`、`tests/test_prompts.py`、`tests/test_retrieval.py`、`tests/test_processing.py`、`tests/test_relevance.py`、`tests/test_pipeline_expand.py`、`tests/test_integration_pipeline.py`
- **工作树**：`worktree-paper-search-unified-model`, `worktree-paper-search-plan`

### LLM 相关性过滤优化

- **决策**：批量推理、预过滤、超时控制、结果缓存、灰度开关（commit: e82ae56）
- **工作树**：`worktree-llm-relevance-optimization`

### 移除硬编码年份约束

- **决策**：从 `PLANNING` 和 `WRITING` agent 提示词中移除硬编码年份限制（commit: 1289d43）
- **工作树**：`worktree-remove-hardcoded-year-constraints`

### 进度报告修复

- **修复**：`_retrieve_papers` 中恢复进度报告（commit: 505842b）
- **修复**：防止自动滚动覆盖 `StageProgressView` 中的手动上滚（commit: 4f8aa53）

### REFLECTION.md 完善

- **决策**：扩展 REFLECTION.md 到 2048+ 中文字符，添加冷启动验证到 SPEC_PROCESS.md（commit: 2b99dbd）
- **修复**：重写 REFLECTION.md §3 从 TDD 到 SDD，诚实反映实际工作流（commit: b6bd6fd）

### TDD 恢复

- **决策**：7 个任务覆盖测试、文档和配置的 TDD 恢复（commit: cf1fe2a）
- **测试**：新增 `tests/test_auxiliary.py`、`tests/test_credentials.py`、`tests/test_evidence_citations.py`（119 个新测试）
- **产出**：`TDD_RECOVERY.md` 流程补证文档
- **工作树**：`worktree-tdd-recovery`

## 2026-08-14

### 提交准备

- **决策**：提交准备 — 最终清理和准备（commit: 35391dc）
- **工作树**：`worktree-submission-prep`

### CI Lint 修复

- **决策**：解决所有 flake8 lint 问题（F821, F401, F811, F841, E741, E501, W292, E124, E302, E401, E241）（commit: 5fdcdb8）
- **工作树**：`worktree-fix-ci-lint` → PR #1 合并到 master

### README 重写

- **决策**：重写 README.md 反映实际项目结构和功能（commit: 4226235）
- **工作树**：`worktree-rewrite-readme`

### 反馈显示修复

- **问题**：Execution 页面反馈显示延迟 — WebSocket 覆盖导致数据竞争
- **修复**：用专用轮询替换 WebSocket 覆盖，解决反馈显示延迟（commit: f09ac3e）
- **工作树**：`worktree-fix-feedback-display` → PR #2 合并到 master

### 移除反馈模块

- **决策**：从前端移除人工反馈模块（FeedbackPanel、FeedbackHistory 等组件）（commit: 53a19d7）
- **工作树**：`worktree-remove-feedback-module` → PR #3 合并到 master

### 移除凭据页面

- **决策**：从前端移除凭据管理页面（commit: b7015f2）
- **工作树**：`worktree-remove-credentials-page` → PR #4 合并到 master

### 凭据管理重构（Keyring 优先级链）

- **决策**：Keyring 后端凭据管理 + WebUI 页面（commit: 0ca78ee）
- **决策**：凭据优先级链实现 — 环境变量 > .env 文件 > keyring > 浏览器存储（commit: bcc99f2）
- **决策**：首次运行引导检测（commit: bcc99f2）
- **决策**：`.env` 路径缓存、keyring 写入错误处理、初始化状态日志简化（commit: 486ad53）
- **测试**：凭据优先级和初始化状态测试（commit: 2e320c6）
- **测试**：`set_api_key` 单元测试 + LLM 同步集成测试（commit: ebace5f）
- **修复**：运行时 LLM 实例在通过凭据 UI 更新 API 密钥时同步（commit: 8cc047a）
- **修复**：flake8 F401, E402, W292 lint 错误（commit: e25ee3d）
- **修复**：从凭据页面移除安全提示卡片（commit: edaa20e）
- **工作树**：`worktree-worktree-fix-credential-priority-bootstrap` → PR #10/#11/#12