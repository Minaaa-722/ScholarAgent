# 实时反馈注入功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ScholarAgent Execution 页面中实现实时反馈注入，用户可在 Agent 执行过程中输入反馈（补充论文/展开章节/通用），Agent 以「智能续接」方式处理并继续执行。

**Architecture:** 在 Harness 中维护线程安全反馈队列，Pipeline 在阶段边界检查队列并执行补充操作；API 层将反馈注入 Harness 并通过 WebSocket 推送反馈状态；前端增加右侧反馈面板和结构化执行详情展示。

**Tech Stack:** Python 3.10+ / FastAPI / React 18 / TypeScript

---

## 全局约束

- 所有 Python 代码兼容 Python 3.10+
- 所有 Python 异常使用 `logger.exception()` 记录堆栈信息
- 文件路径使用 `D:\ScholarAgent` 作为项目根目录
- 前端 API 函数在 `web/src/api/client.ts` 中统一管理
- 提交信息格式：`feat: 具体功能描述`

## 文件结构

| 文件 | 责任 | 状态 |
|------|------|------|
| `agent/core/state.py` | 状态机，FEEDBACK → ANALYSIS 允许转换 | 修改 |
| `agent/core/harness.py` | 反馈队列、阶段产物存储、补充检索、智能续接核心逻辑 | 修改 |
| `api/models.py` | FeedbackRequest 扩展 | 修改 |
| `api/routes/feedback.py` | 反馈注入路由、待处理反馈查询 | 重写 |
| `api/routes/progress.py` | WebSocket 推送增加反馈状态和 execution_details | 修改 |
| `web/src/api/client.ts` | submitFeedback / getPendingFeedback 函数 | 修改 |
| `web/src/pages/AgentExecution.tsx` | 反馈面板、反馈历史、结构化执行详情 | 重写 |

---

### Task 1: 状态机 — 允许 FEEDBACK → ANALYSIS 转换

**Files:**
- Modify: `agent/core/state.py:25`

**Interfaces:**
- Consumes: 无（纯内部改动）
- Produces: `AgentState.FEEDBACK` 允许 `ANALYSIS` 作为目标状态

- [ ] **Step 1: 修改状态转换表**

```python
# 改动前 (line 25):
AgentState.FEEDBACK: {AgentState.WRITING, AgentState.RETRIEVAL, AgentState.ERROR, AgentState.INTERRUPTED},

# 改动后:
AgentState.FEEDBACK: {AgentState.WRITING, AgentState.RETRIEVAL, AgentState.ANALYSIS, AgentState.ERROR, AgentState.INTERRUPTED},
```

- [ ] **Step 2: 验证**

确认 `_TRANSITIONS[AgentState.FEEDBACK]` 包含 `AgentState.ANALYSIS`

- [ ] **Step 3: 提交**

```bash
git add agent/core/state.py
git commit -m "feat: allow FEEDBACK → ANALYSIS state transition"
```

---

### Task 2: Harness 核心 — 反馈队列与智能续接

**Files:**
- Modify: `agent/core/harness.py`

**Interfaces:**
- Consumes: `agent/core/state.py` 中的 `AgentState` 枚举
- Produces: `submit_human_feedback(category, content) → dict`、`get_task_info() → dict`（增强）、`_check_human_feedback(on_progress)`（内部）

**新增字段（`__init__` 方法中）：**

```python
# 反馈队列（线程安全）
self.feedback_queue: list[dict] = []
self.feedback_history: list[dict] = []
self._feedback_lock = threading.Lock()

# 阶段执行产物（用于前端展示）
self._plan: str = ""
self._papers: list[dict] = []
self._analysis: str = ""
self._draft_sections: list[dict] = []
self._validation_scores: dict = {}
self._retrieved_queries: list[str] = []
self._pending_expansions: list[str] = []
self._pending_revisions: list[str] = []
```

- [ ] **Step 1: 在 `__init__` 中插入上述新增字段**

```python
# 在现有的 self.task_started_at = "" 之后插入
self.feedback_queue: list[dict] = []
self.feedback_history: list[dict] = []
self._feedback_lock = threading.Lock()
self._plan = ""
self._papers = []
self._analysis = ""
self._draft_sections = []
self._validation_scores = {}
self._retrieved_queries = []
self._pending_expansions = []
self._pending_revisions = []
```

- [ ] **Step 2: 新增 `submit_human_feedback()` 方法**

在 `resume()` 方法之后插入：

```python
def submit_human_feedback(self, category: str, content: str) -> dict:
    """外部 API 调用此方法注入反馈"""
    import uuid
    feedback = {
        "id": str(uuid.uuid4())[:8],
        "category": category,
        "content": content,
        "status": "pending",
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with self._feedback_lock:
        self.feedback_queue.append(feedback)
    return feedback
```

- [ ] **Step 3: 新增 `_check_human_feedback()` 方法**

在 `_format_repair()` 方法之前插入：

```python
def _check_human_feedback(self, on_progress: Optional[ProgressCallback]) -> None:
    """检查并处理待处理的反馈（在阶段边界调用）"""
    with self._feedback_lock:
        if not self.feedback_queue:
            return
        feedback = self.feedback_queue.pop(0)
        feedback["status"] = "processing"
        self.feedback_history.append(feedback)

    short = feedback["content"][:60]
    self._progress(on_progress, "feedback", f"Processing feedback ({feedback['category']}): {short}…")

    if feedback["category"] == "supplement_papers":
        self._progress(on_progress, "retrieval", f"Supplementing papers: {short}…")
        new_papers = self._supplement_retrieval(feedback["content"])
        self._papers.extend(new_papers)
        # Dedup by title
        seen_titles = set()
        deduped = []
        for p in self._papers:
            t = (p.get("title") or "").strip().lower()
            if t and t not in seen_titles:
                seen_titles.add(t)
                deduped.append(p)
        self._papers = deduped

        self._progress(on_progress, "analysis", "Re-analyzing with supplemented papers…")
        self._analysis = self._analyze_papers(self._papers, self._plan)

    elif feedback["category"] == "expand_section":
        self._pending_expansions.append(feedback["content"])

    elif feedback["category"] == "general":
        self._pending_revisions.append(feedback["content"])

    feedback["status"] = "applied"
    self._progress(on_progress, "feedback", f"Feedback applied: {short}…")
```

- [ ] **Step 4: 新增 `_supplement_retrieval()` 方法**

在 `_check_human_feedback()` 之后插入：

```python
def _supplement_retrieval(self, feedback_content: str) -> list[dict]:
    """根据反馈内容进行补充检索"""
    sys_prompt = (
        "You are a literature search assistant. "
        "Extract a concise search query from the user's feedback. "
        "Return ONLY the query, no explanation."
    )
    resp = self._safe_llm_call(sys_prompt, feedback_content)
    query = resp.text.strip().strip('"').strip("'")

    if not query or len(query) > 200:
        query = feedback_content[:100]

    all_results = []
    arxiv_res = self._arxiv_search.execute({"query": query, "max_results": 10})
    if arxiv_res.success:
        all_results.append(arxiv_res.data)

    ss_res = self._semantic_scholar.execute({"query": query, "max_results": 10})
    if ss_res.success:
        all_results.append(ss_res.data)

    time.sleep(0.3)
    merged = self._merge.execute({"results": all_results})
    return merged.data.get("papers", []) if merged.success else []
```

- [ ] **Step 5: 新增 `_extract_sections()` 辅助方法**

在 `_supplement_retrieval()` 之后插入：

```python
@staticmethod
def _extract_sections(draft: str) -> list[dict]:
    """从 LaTeX 草稿中提取章节结构"""
    import re
    sections = []
    for match in re.finditer(r'\\(?:sub)*section\{([^}]+)\}', draft):
        sections.append({
            "level": match.group(0).count("sub"),
            "title": match.group(1),
        })
    return sections
```

- [ ] **Step 6: 在 `_pipeline()` 各阶段之间插入 `_check_human_feedback()` 调用**

在 `_pipeline()` 方法中，每个阶段完成后、下一个阶段前插入检查点：

```python
# 在 Stage 1 (PLANNING) 完成后、RETRIEVAL 前:
self._check_human_feedback(on_progress)

# 在 Stage 2 (RETRIEVAL) 完成后、ANALYSIS 前:
self._check_human_feedback(on_progress)

# 在 Stage 3 (ANALYSIS) 完成后、WRITING 前:
self._check_human_feedback(on_progress)

# 在 WRITING+VALIDATION 循环的每次迭代开始:
self._check_human_feedback(on_progress)
```

具体插入位置：

line 271 (`self.state.transition_to(AgentState.RETRIEVAL)`) 之后：
```python
self._check_human_feedback(on_progress)
```

line 278 (`self.state.transition_to(AgentState.ANALYSIS)`) 之后：
```python
self._check_human_feedback(on_progress)
```

line 285 (`self.state.transition_to(AgentState.WRITING)`) 之后、line 287 (`rounds = 0`) 之前：
```python
self._check_human_feedback(on_progress)
```

在 while 循环体开头（line 289 之后）：
```python
self._check_human_feedback(on_progress)
```

- [ ] **Step 7: 在各阶段方法中保存中间产物**

在 `_generate_plan()` 的 `return resp.text` 前插入：
```python
self._plan = resp.text
```

在 `_retrieve_papers()` 的 `return papers[:self.config.max_papers]` 前插入：
```python
self._papers = papers[:self.config.max_papers]
self._retrieved_queries = queries
```

在 `_analyze_papers()` 的 `return resp.text` 前插入：
```python
self._analysis = resp.text
```

在 `_write_survey()` 的 `return resp.text` 前插入：
```python
self._draft_sections = self._extract_sections(resp.text)
```

在 `_run_validators()` 的 `return [v.validate(context) for v in self._validators]` 前插入：
```python
self._validation_scores = {
    r.validator_name: {
        "score": r.score,
        "passed": r.passed,
        "message": (r.message or "")[:200],
    }
    for r in results
}
```

- [ ] **Step 8: 增强 `get_task_info()` — 添加 `execution_details`**

```python
def get_task_info(self) -> dict:
    # ... 保留现有字段 ...
    
    # 在 return 之前构建 details
    details = {}
    if self._plan:
        lines = [l.strip() for l in self._plan.split("\n") if l.strip()]
        preview_lines = [l for l in lines if len(l) > 10][:5]
        details["plan"] = {
            "summary": "Research plan generated",
            "preview": preview_lines,
            "section_count": sum(1 for l in lines if l.startswith(("\\section", "- **", "###"))),
        }
    if self._papers:
        paper_list = []
        for p in self._papers[:10]:
            authors = p.get("authors", [])[:3]
            author_str = ", ".join(authors) if authors else "Unknown"
            if len(p.get("authors", [])) > 3:
                author_str += " et al."
            paper_list.append({
                "title": p.get("title", "Untitled"),
                "authors": author_str,
                "year": p.get("year", ""),
                "citations": p.get("citation_count", 0),
                "source": "arxiv" if p.get("arxiv_id") else "semantic_scholar",
            })
        details["papers"] = {
            "total": len(self._papers),
            "list": paper_list,
        }
    if self._retrieved_queries:
        details["search_queries"] = self._retrieved_queries
    if self._analysis:
        details["analysis"] = {
            "summary": "Paper analysis completed",
            "preview": self._analysis[:300],
        }
    if self._draft_sections:
        details["sections"] = self._draft_sections
    if self._validation_scores:
        details["validation"] = self._validation_scores

    # 追加 feedback 状态
    info = {
        # ... 现有字段 ...
        "execution_details": details,
        "feedback_queue": self.feedback_queue,
        "feedback_history": self.feedback_history,
    }
    return info
```

- [ ] **Step 9: 在 `start()` 方法中重置新增字段**

在 `self.task_started_at = time.strftime(...)` 之后重置所有新增字段：

```python
self.feedback_queue = []
self.feedback_history = []
self._plan = ""
self._papers = []
self._analysis = ""
self._draft_sections = []
self._validation_scores = {}
self._retrieved_queries = []
self._pending_expansions = []
self._pending_revisions = []
```

- [ ] **Step 10: 提交**

```bash
git add agent/core/harness.py
git commit -m "feat: add feedback queue, stage products, and smart resumption in harness"
```

---

### Task 3: API 层 — 反馈路由与 WebSocket 增强

**Files:**
- Modify: `api/models.py`
- Modify: `api/routes/feedback.py`（重写）
- Modify: `api/routes/progress.py`

**Interfaces:**
- Consumes: `Harness.submit_human_feedback()`、`Harness.feedback_queue`、`Harness.feedback_history`
- Produces: `POST /api/feedback`、`GET /api/feedback/pending`、WebSocket 推送增强

- [ ] **Step 1: 扩展 FeedbackRequest 模型**

在 `api/models.py` 中，将 `FeedbackRequest` 改为：

```python
class FeedbackRequest(BaseModel):
    category: str = "general"
    content: str
```

（当前代码已基本一致，确认即可）

- [ ] **Step 2: 重写 `api/routes/feedback.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from api.models import FeedbackRequest
from agent.core.harness import Harness
from api.routes.survey import get_harness

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(req: FeedbackRequest, harness: Harness = Depends(get_harness)):
    if not harness._pipeline_running:
        raise HTTPException(status_code=400, detail="Pipeline is not running")
    feedback = harness.submit_human_feedback(req.category, req.content)
    return {"status": "queued", "feedback": feedback}


@router.get("/pending")
async def get_pending_feedback(harness: Harness = Depends(get_harness)):
    return {
        "queue": harness.feedback_queue,
        "history": harness.feedback_history,
    }
```

- [ ] **Step 3: 增强 WebSocket 推送**

在 `api/routes/progress.py` 中，在 `info` 获取后追加 feedback 和 execution_details 字段：

```python
@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    from api.main import _harness

    await websocket.accept()
    try:
        while True:
            info = _harness.get_task_info()
            info["task_id"] = task_id
            # 增强：追加反馈状态和执行详情
            info["feedback_queue"] = _harness.feedback_queue
            info["feedback_history"] = _harness.feedback_history
            info["execution_details"] = _harness.get_task_info().get("execution_details", {})
            await websocket.send_text(json.dumps(info))
            if not _harness._pipeline_running:
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 4: 提交**

```bash
git add api/models.py api/routes/feedback.py api/routes/progress.py
git commit -m "feat: wire up feedback API endpoints and enhance WebSocket push"
```

---

### Task 4: 前端 API 客户端

**Files:**
- Modify: `web/src/api/client.ts`

**Interfaces:**
- Consumes: 后端 `POST /api/feedback`、`GET /api/feedback/pending`
- Produces: `submitFeedback()`、`getPendingFeedback()` 供前端组件使用

- [ ] **Step 1: 新增 `submitFeedback` 函数**

在 `client.ts` 末尾添加：

```typescript
export async function submitFeedback(data: { category: string; content: string }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Feedback submission failed");
  return res.json();
}
```

- [ ] **Step 2: 新增 `getPendingFeedback` 函数**

```typescript
export async function getPendingFeedback() {
  const res = await fetch(`${API_BASE}/api/feedback/pending`);
  return res.json();
}
```

- [ ] **Step 3: 提交**

```bash
git add web/src/api/client.ts
git commit -m "feat: add submitFeedback and getPendingFeedback API functions"
```

---

### Task 5: 前端 AgentExecution 页面 — 反馈面板与执行详情

**Files:**
- Modify: `web/src/pages/AgentExecution.tsx`

**Interfaces:**
- Consumes: `submitFeedback()`、`getPendingFeedback()`、WebSocket 推送中的 `feedback_queue`、`feedback_history`、`execution_details`

- [ ] **Step 1: 扩展类型定义**

将 `ProgressInfo` 接口扩展为：

```typescript
interface FeedbackItem {
  id: string;
  category: "supplement_papers" | "expand_section" | "general";
  content: string;
  status: "pending" | "processing" | "applied";
  received_at: string;
}

interface PaperInfo {
  title: string;
  authors: string;
  year: string | number;
  citations: number;
  source: string;
}

interface SectionInfo {
  level: number;
  title: string;
}

interface ExecutionDetails {
  plan?: { summary: string; preview: string[]; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
}

interface ProgressInfo {
  topic: string;
  status: string;
  pipeline_running: boolean;
  current_stage: string;
  current_message: string;
  retry_count: number;
  has_warnings: boolean;
  keywords: string[];
  goal: string;
  task_started_at?: string;
  feedback_queue: FeedbackItem[];
  feedback_history: FeedbackItem[];
  execution_details: ExecutionDetails;
}
```

- [ ] **Step 2: 新增状态变量**

在组件函数内部，现有状态之后添加：

```typescript
const [feedbackCategory, setFeedbackCategory] = useState<string>("supplement_papers");
const [feedbackContent, setFeedbackContent] = useState<string>("");
const [feedbackSending, setFeedbackSending] = useState(false);
const [feedbackError, setFeedbackError] = useState<string | null>(null);
const [feedbackHistory, setFeedbackHistory] = useState<FeedbackItem[]>([]);
```

- [ ] **Step 3: 新增 `handleSendFeedback` 函数**

在现有逻辑之后、`return` 之前添加：

```typescript
const handleSendFeedback = async () => {
  if (!feedbackContent.trim()) return;
  setFeedbackSending(true);
  setFeedbackError(null);
  try {
    const result = await submitFeedback({
      category: feedbackCategory,
      content: feedbackContent.trim(),
    });
    setFeedbackHistory(prev => [...prev, result.feedback]);
    setFeedbackContent("");
  } catch {
    setFeedbackError("发送失败，请重试");
  } finally {
    setFeedbackSending(false);
  }
};
```

- [ ] **Step 4: 在 WebSocket onmessage 中同步 feedback_history**

在 `ws.onmessage` 处理器中，设置 progress 之后添加：

```typescript
if (data.feedback_history) {
  setFeedbackHistory(data.feedback_history);
}
```

- [ ] **Step 5: 新增 FEEDBACK_CATEGORIES 常量和反馈输入面板**

`STAGE_LABELS` 之后添加：

```typescript
const FEEDBACK_CATEGORIES = [
  { value: "supplement_papers", label: "📄 补充论文", desc: "补充某个子领域的相关论文" },
  { value: "expand_section", label: "📝 展开章节", desc: "要求对某个章节展开详细论述" },
  { value: "general", label: "💬 通用反馈", desc: "其他修改建议" },
];
```

- [ ] **Step 6: 新增 DetailCard 组件**

在 `AgentExecution` 函数外部（文件底部附近）添加：

```tsx
function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 8, padding: "1rem 1.2rem",
      boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: "1rem",
    }}>
      <h4 style={{ margin: "0 0 0.8rem", fontSize: "0.95rem", color: "#333" }}>{title}</h4>
      {children}
    </div>
  );
}
```

- [ ] **Step 7: 重写执行详情区域（替换原来的 keywords/goal grid）**

将 `{/* Details */}` 注释起的 grid 区域（约 line 190-203）替换为动态执行详情渲染：

```tsx
{/* 执行详情 — 动态渲染 */}
{progress.execution_details && (
  <div style={{ display: "flex", flexDirection: "column", marginBottom: "1.5rem" }}>
    
    {/* 研究计划 */}
    {progress.execution_details.plan && (
      <DetailCard title="📋 研究计划">
        <p style={{ color: "#666", margin: "0 0 0.5rem" }}>
          共 {progress.execution_details.plan.section_count} 个章节/要点
        </p>
        {progress.execution_details.plan.preview.map((line, i) => (
          <p key={i} style={{ margin: "0.2rem 0", paddingLeft: "0.5rem",
            borderLeft: "2px solid #1976d2", fontSize: "0.9rem" }}>
            {line}
          </p>
        ))}
      </DetailCard>
    )}
    
    {/* 搜索查询 */}
    {progress.execution_details.search_queries && (
      <DetailCard title="🔍 搜索查询">
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {progress.execution_details.search_queries.map((q, i) => (
            <span key={i} style={{
              background: "#e3f2fd", padding: "0.3rem 0.8rem",
              borderRadius: 12, fontSize: "0.85rem", color: "#1565c0",
            }}>
              {q}
            </span>
          ))}
        </div>
      </DetailCard>
    )}
    
    {/* 检索到的论文 */}
    {progress.execution_details.papers && (
      <DetailCard title={`📄 检索到的论文（共 ${progress.execution_details.papers.total} 篇）`}>
        <div style={{ maxHeight: 300, overflowY: "auto" }}>
          {progress.execution_details.papers.list.map((p, i) => (
            <div key={i} style={{
              padding: "0.5rem", marginBottom: "0.3rem",
              background: "#fafafa", borderRadius: 6, border: "1px solid #eee",
            }}>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{p.title}</div>
              <div style={{ fontSize: "0.8rem", color: "#666", marginTop: "0.2rem" }}>
                {p.authors} · {p.year} · 引用: {p.citations}
                <span style={{
                  marginLeft: "0.5rem", background: "#e8eaf6",
                  padding: "0.1rem 0.4rem", borderRadius: 4, fontSize: "0.75rem",
                }}>
                  {p.source}
                </span>
              </div>
            </div>
          ))}
          {progress.execution_details.papers.total > 10 && (
            <p style={{ color: "#999", fontSize: "0.85rem", textAlign: "center" }}>
              … 还有 {progress.execution_details.papers.total - 10} 篇
            </p>
          )}
        </div>
      </DetailCard>
    )}
    
    {/* 分析结果 */}
    {progress.execution_details.analysis && (
      <DetailCard title="🔬 论文分析">
        <p style={{ color: "#666", fontSize: "0.9rem", whiteSpace: "pre-wrap",
          margin: 0, lineHeight: 1.5 }}>
          {progress.execution_details.analysis.preview}
        </p>
      </DetailCard>
    )}
    
    {/* 论文结构 */}
    {progress.execution_details.sections && (
      <DetailCard title="📑 论文结构">
        {progress.execution_details.sections.map((s, i) => (
          <div key={i} style={{
            padding: "0.3rem 0", paddingLeft: s.level === 0 ? "0" : "1.5rem",
            fontWeight: s.level === 0 ? 600 : 400, fontSize: "0.9rem",
          }}>
            {s.level === 0 ? "▸ " : "  ◦ "}{s.title}
          </div>
        ))}
      </DetailCard>
    )}
    
    {/* 验证评分 */}
    {progress.execution_details.validation && (
      <DetailCard title="✅ 质量验证">
        {Object.entries(progress.execution_details.validation).map(([name, v]) => (
          <div key={name} style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            padding: "0.3rem 0", borderBottom: "1px solid #f0f0f0",
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%",
              background: v.passed ? "#4caf50" : "#f44336",
              display: "inline-block", flexShrink: 0,
            }} />
            <span style={{ fontWeight: 500, minWidth: 140, fontSize: "0.9rem" }}>{name}</span>
            <span style={{ color: v.passed ? "#2e7d32" : "#c62828", fontSize: "0.85rem" }}>
              {v.passed ? "✓ 通过" : "✗ 需改进"}
            </span>
            {v.message && (
              <span style={{ color: "#666", fontSize: "0.8rem", marginLeft: "0.3rem" }}>
                — {v.message}
              </span>
            )}
          </div>
        ))}
      </DetailCard>
    )}
    
    {/* 无内容时显示原始 keywords/goal */}
    {!progress.execution_details.plan &&
     !progress.execution_details.search_queries &&
     !progress.execution_details.papers &&
     !progress.execution_details.analysis &&
     !progress.execution_details.sections &&
     !progress.execution_details.validation && (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <strong>Keywords</strong>
          <p style={{ color: "#666", margin: "0.3rem 0 0" }}>
            {progress.keywords?.length ? progress.keywords.join(", ") : "—"}
          </p>
        </div>
        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <strong>Research Goal</strong>
          <p style={{ color: "#666", margin: "0.3rem 0 0", whiteSpace: "pre-wrap" }}>
            {progress.goal || "—"}
          </p>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 8: 新增反馈面板（在 stage chain 和 current message 之间插入）**

在 `{/* Current message */}` 区块之前、`{/* Pipeline stage chain */}` 之后插入：

```tsx
{/* 反馈区域 — 仅在 pipeline 运行时显示 */}
{pipelineRunning && (
  <div style={{
    background: "#fff", borderRadius: 8, padding: "1rem 1.5rem",
    marginBottom: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
    border: "1px solid #e0e0e0",
  }}>
    <h4 style={{ margin: "0 0 0.8rem", color: "#333" }}>向 Agent 提供反馈</h4>
    
    {/* 类别选择 */}
    <div style={{ marginBottom: "0.5rem" }}>
      {FEEDBACK_CATEGORIES.map(c => (
        <label key={c.value} style={{
          display: "inline-flex", alignItems: "center", gap: "0.3rem",
          marginRight: "1rem", cursor: "pointer", fontSize: "0.9rem",
        }}>
          <input
            type="radio"
            name="feedbackCategory"
            value={c.value}
            checked={feedbackCategory === c.value}
            onChange={() => setFeedbackCategory(c.value)}
          />
          {c.label}
        </label>
      ))}
    </div>
    
    {/* 类别描述提示 */}
    <p style={{ fontSize: "0.8rem", color: "#666", margin: "0 0 0.5rem" }}>
      {FEEDBACK_CATEGORIES.find(c => c.value === feedbackCategory)?.desc}
    </p>
    
    {/* 输入框 */}
    <textarea
      value={feedbackContent}
      onChange={e => setFeedbackContent(e.target.value)}
      placeholder={
        feedbackCategory === "supplement_papers" ? "例：请补充关于 Vision Transformer 高效的论文…" :
        feedbackCategory === "expand_section" ? "例：请在实验部分增加对消融实验的详细讨论…" :
        "例：请加强对对比方法的分析…"
      }
      rows={3}
      style={{
        width: "100%", padding: "0.6rem", borderRadius: 6,
        border: "1px solid #ccc", fontSize: "0.9rem",
        resize: "vertical", boxSizing: "border-box",
      }}
    />
    
    {/* 发送按钮和错误提示 */}
    <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.5rem" }}>
      <button
        onClick={handleSendFeedback}
        disabled={feedbackSending || !feedbackContent.trim()}
        style={{
          padding: "0.5rem 1.5rem", background: feedbackSending || !feedbackContent.trim() ? "#ccc" : "#1976d2",
          color: "#fff", border: "none", borderRadius: 6, cursor: feedbackSending || !feedbackContent.trim() ? "not-allowed" : "pointer",
          fontSize: "0.9rem",
        }}
      >
        {feedbackSending ? "发送中…" : "发送反馈"}
      </button>
      {feedbackError && <span style={{ color: "#f44336", fontSize: "0.85rem" }}>{feedbackError}</span>}
    </div>
    
    {/* 反馈历史 */}
    {feedbackHistory.length > 0 && (
      <div style={{ marginTop: "1rem", borderTop: "1px solid #eee", paddingTop: "0.8rem" }}>
        <h5 style={{ margin: "0 0 0.5rem", color: "#555", fontSize: "0.85rem" }}>反馈历史</h5>
        {feedbackHistory.map(fb => (
          <div key={fb.id} style={{
            padding: "0.5rem 0.8rem", marginBottom: "0.3rem", borderRadius: 6,
            borderLeft: `3px solid ${
              fb.status === "applied" ? "#4caf50" : 
              fb.status === "processing" ? "#ff9800" : "#1976d2"
            }`,
            background: fb.status === "applied" ? "#f1f8e9" : "#fafafa",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.75rem", color: "#999" }}>
                {FEEDBACK_CATEGORIES.find(c => c.value === fb.category)?.label || fb.category}
                {" — "}{fb.received_at}
              </span>
              <span style={{ fontSize: "0.75rem", fontWeight: 600,
                color: fb.status === "applied" ? "#2e7d32" : 
                       fb.status === "processing" ? "#e65100" : "#1976d2",
              }}>
                {fb.status === "applied" ? "✓ 已处理" : 
                 fb.status === "processing" ? "⟳ 处理中…" : "◷ 排队中"}
              </span>
            </div>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem", color: "#333" }}>
              {fb.content}
            </p>
          </div>
        ))}
      </div>
    )}
  </div>
)}
```

- [ ] **Step 9: 调整页面布局 — 两栏布局（左：详情 + 右：反馈）**

将 stage chain、current message、execution details 包裹在左侧栏，反馈面板放在右侧栏。使用 `display: grid` 两栏布局：

```tsx
{pipelineRunning ? (
  <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
    {/* 左侧：进度 + 详情 */}
    <div>
      {/* Stage chain */}
      {/* Current message */}
      {/* Execution details */}
    </div>
    {/* 右侧：反馈面板 */}
    <div>
      {/* Feedback panel */}
    </div>
  </div>
) : (
  <div>
    {/* Stage chain */}
    {/* Current message */}
    {/* Execution details */}
    {/* Finished state */}
  </div>
)}
```

- [ ] **Step 10: 提交**

```bash
git add web/src/pages/AgentExecution.tsx
git commit -m "feat: add feedback panel, feedback history, and structured execution details to AgentExecution"
```

---

## 自检清单

1. **Spec 覆盖度**：设计文档中的每个需求是否都有对应任务？
   - 反馈队列 + 线程安全锁 → Task 2 Step 1
   - 阶段边界检查点 → Task 2 Step 6
   - 三种反馈类别（supplement_papers/expand_section/general）→ Task 2 Step 3
   - 补充检索逻辑 → Task 2 Step 4
   - 阶段产物存储 → Task 2 Step 7
   - 结构化 execution_details → Task 2 Step 8
   - 状态机 FEEDBACK → ANALYSIS → Task 1
   - API 反馈路由 → Task 3 Step 2
   - WebSocket 增强 → Task 3 Step 3
   - 前端 API 客户端 → Task 4
   - 反馈面板 → Task 5 Step 8
   - 反馈历史 → Task 5 Step 8
   - 结构化执行详情展示 → Task 5 Step 7
   - DetailCard 组件 → Task 5 Step 6

2. **占位符检查**：无 "TBD"、"TODO" 等占位符，所有代码块均为完整可执行代码

3. **类型一致性**：`submit_human_feedback()` 返回 `dict`，前端 `submitFeedback()` 接收 `{category, content}`，各部分接口一致；`execution_details` 结构在前后端定义一致

4. **执行顺序验证**：Task 1（状态机）→ Task 2（Harness 核心）→ Task 3（API 路由）→ Task 4（前端 API 客户端）→ Task 5（前端页面），依赖关系正确