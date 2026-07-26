# AGENT_LOG — 关键决策与人工干预记录

> 按时间顺序记录 ScholarAgent 项目开发过程中的关键决策、架构变更、bug 修复和人工干预节点。

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