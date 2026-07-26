# 实时反馈注入功能设计文档

## 概述
在 ScholarAgent 的 Execution 页面增加实时反馈能力：用户可以在 Agent 执行过程中输入反馈（如要求补充某子领域论文或展开某章节），Agent 收到后以「智能续接」方式暂停当前任务，执行修正，然后继续。全链路从 Web UI → API → Agent 后端打通。

## 架构变化

### 当前架构
```
Frontend (React)  ←WS→  FastAPI  ←thread→  Harness._pipeline()
  (只读状态)           (progress.py)        (线性执行 5 阶段)
                       feedback.py (空壳)
```

### 目标架构
```
Frontend (React)  ←WS→  FastAPI  ←thread→  Harness._pipeline()
  (交互式反馈面板)        feedback.py          (阶段边界检查反馈队列)
  (结构化执行详情)        (注入 Harness)        → 补充检索 → 重新分析 → 继续
```

## 核心设计决策

1. **智能续接** — 不丢弃当前进度，而是在阶段边界检查反馈队列，执行补充操作后继续
2. **反馈队列 + 阶段边界检查点** — 不中断正在执行的阶段，自然过渡到下一个阶段前处理反馈
3. **三种反馈类别** — `supplement_papers`（补充论文）、`expand_section`（展开章节）、`general`（通用）

## 文件改动清单

### Agent 后端层

| 文件 | 改动 |
|------|------|
| `agent/core/harness.py` | 新增反馈队列、阶段中间产物存储、反馈处理方法、补充检索逻辑 |
| `agent/core/state.py` | 扩展 FEEDBACK 状态转换允许 → ANALYSIS |

### API 层

| 文件 | 改动 |
|------|------|
| `api/models.py` | 扩展 FeedbackRequest 字段 |
| `api/routes/feedback.py` | 重写为注入 Harness 的反馈路由，新增 GET /pending |
| `api/routes/progress.py` | WS 推送加入 feedback 状态和 execution_details |

### 前端层

| 文件 | 改动 |
|------|------|
| `web/src/api/client.ts` | 新增 submitFeedback / getPendingFeedback |
| `web/src/pages/AgentExecution.tsx` | 新增反馈面板、反馈历史、结构化执行详情 |

## 详细实现

### 1. Harness 核心改动

- 新增 `feedback_queue: list[dict]`、`feedback_history: list[dict]`、`_feedback_lock`
- 新增 `_plan`、`_papers`、`_analysis`、`_draft_sections`、`_validation_scores`、`_retrieved_queries` 字段存储阶段产物
- 新增 `submit_human_feedback(category, content)` 方法
- 新增 `_check_human_feedback(on_progress)` 方法，在 `_pipeline()` 每个阶段边界调用
- 新增 `_supplement_retrieval(feedback_content)` 方法
- 增强 `get_task_info()` 返回 `execution_details` 结构化字段
- 新增 `_extract_sections(draft)` 辅助方法解析 LaTeX 章节

### 2. 状态机

- FEEDBACK → ANALYSIS 添加允许转换

### 3. API 路由

- `POST /api/feedback` — 调用 `harness.submit_human_feedback()`
- `GET /api/feedback/pending` — 返回队列和历史
- WebSocket 推送增加 `feedback_queue`、`feedback_history`、`execution_details`

### 4. 前端

- 右侧反馈面板（类别选择 + 文本输入 + 发送按钮）
- 反馈历史列表（状态指示：排队/处理中/已处理）
- 动态执行详情卡片（研究计划、搜索查询、论文列表、分析预览、章节结构、验证评分）
- DetailCard 可复用组件

## 数据流

```
用户输入反馈 → POST /api/feedback
  → Harness.submit_human_feedback() 加入队列
    → Pipeline 到达阶段边界
      → _check_human_feedback() 取出队列
        → 执行补充操作（补充检索/重新分析/标记扩展）
          → 状态设为 applied
            → WS 推送更新 → 前端反馈历史刷新
```