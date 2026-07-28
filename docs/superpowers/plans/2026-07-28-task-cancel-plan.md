# Task Cancel Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pause/resume/cancel with a single one-way "Cancel Task" that clears all data and shows a cancelled state in history.

**Architecture:** Backend adds `CANCELLED` state + `cancel()` method on Harness; frontend removes pause/resume buttons, calls `cancelSurvey()` on cancel, resets to blank page, and shows "已取消" in history detail.

**Tech Stack:** Python 3.10+ / FastAPI backend, React 18 / TypeScript frontend, Pydantic models.

## Global Constraints

- No changes to LLM calling code or paper retrieval business logic
- All existing state transitions must remain valid
- Duplicate cancel must not throw HTTP 500 (return friendly error in body)
- Cancelled task must appear in history with status "cancelled"
- After cancel, execution page must return to initial blank state (no timeline marks)
- History detail for cancelled tasks must show "任务已手动取消，无过程数据"

---

### Task 1: Backend State — Add CANCELLED to State Machine

**Files:**
- Modify: `agent/core/state.py`

**Interfaces:**
- Consumes: (none)
- Produces: `AgentState.CANCELLED` enum value, updated `_TRANSITIONS` dict, updated `interrupt()` guard, updated `is_terminal()`

- [ ] **Step 1: Add `CANCELLED` to `AgentState` enum**

In `agent/core/state.py`, add `CANCELLED = auto()` between `INTERRUPTED` and `COMPLETE`:

```python
class AgentState(Enum):
    IDLE = auto()
    PLANNING = auto()
    RETRIEVAL = auto()
    ANALYSIS = auto()
    WRITING = auto()
    VALIDATION = auto()
    FEEDBACK = auto()
    INTERRUPTED = auto()
    CANCELLED = auto()  # ← NEW
    COMPLETE = auto()
    ERROR = auto()
```

- [ ] **Step 2: Update `_TRANSITIONS` — add CANCELLED as a valid target from all non-terminal states**

In `_TRANSITIONS`, add `AgentState.CANCELLED` to every non-terminal state's allowed set, and add `AgentState.CANCELLED: set()` as a terminal entry:

```python
_TRANSITIONS = {
    AgentState.IDLE: {AgentState.PLANNING, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.PLANNING: {AgentState.RETRIEVAL, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.RETRIEVAL: {AgentState.ANALYSIS, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.ANALYSIS: {AgentState.WRITING, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.WRITING: {AgentState.VALIDATION, AgentState.FEEDBACK, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.VALIDATION: {AgentState.WRITING, AgentState.COMPLETE, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.FEEDBACK: {AgentState.WRITING, AgentState.RETRIEVAL, AgentState.ANALYSIS, AgentState.ERROR, AgentState.INTERRUPTED, AgentState.CANCELLED},
    AgentState.INTERRUPTED: {AgentState.PLANNING, AgentState.RETRIEVAL, AgentState.ANALYSIS,
                             AgentState.WRITING, AgentState.VALIDATION, AgentState.COMPLETE, AgentState.ERROR, AgentState.CANCELLED},
    AgentState.CANCELLED: set(),  # ← NEW: terminal state
    AgentState.COMPLETE: set(),
    AgentState.ERROR: {
        AgentState.IDLE,
        AgentState.PLANNING,
        AgentState.RETRIEVAL,
        AgentState.ANALYSIS,
        AgentState.WRITING,
        AgentState.VALIDATION,
    },
}
```

- [ ] **Step 3: Update `interrupt()` guard to also allow CANCELLED**

Change the guard in `interrupt()` so it also checks `AgentState.CANCELLED`:

```python
def interrupt(self) -> None:
    if self.current_state in (AgentState.INTERRUPTED, AgentState.CANCELLED, AgentState.IDLE, AgentState.COMPLETE):
        raise ValueError(f"Cannot interrupt from {self.current_state.name}")
```

- [ ] **Step 4: Update `is_terminal()` to include CANCELLED**

```python
def is_terminal(self) -> bool:
    return self.current_state in (AgentState.COMPLETE, AgentState.ERROR, AgentState.CANCELLED)
```

- [ ] **Step 5: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add agent/core/state.py
git commit -m "feat: add CANCELLED state to state machine

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Backend Harness — Add `cancel()` Method

**Files:**
- Modify: `agent/core/harness.py` (add `cancel()`, `_clear_all_data()`, `reset_state()` on orchestrator)

**Interfaces:**
- Consumes: `AgentState.CANCELLED` (from Task 1), `self._memory_integration.save_task_history()`
- Produces: `Harness.cancel()`, `Harness._clear_all_data()`, `PipelineOrchestrator.reset_state()`

- [ ] **Step 1: Add `reset_state()` method to `PipelineOrchestrator` in `agent/core/pipeline.py`**

Extract the reset block at the top of `run_pipeline()` into a dedicated method:

```python
def reset_state(self) -> None:
    """Reset all pipeline state to defaults (called on cancel/restart)."""
    self.execution_log = []
    self._pipeline_retry_count = 0
    self._last_failed_stage = None
    self._error_message = ""
    self._plan = ""
    self._papers = []
    self._analysis = ""
    self._draft_sections = []
    self._validation_scores = {}
    self._retrieved_queries = []
    self._pending_expansions = []
    self._pending_revisions = []
    self.latex_repair_log = None
    self.current_stage = ""
    self.current_message = ""
```

Then replace the inline reset block at the top of `run_pipeline()` with a call to `self.reset_state()`.

- [ ] **Step 2: Add `_clear_all_data()` to `Harness`**

```python
def _clear_all_data(self) -> None:
    """Clear all intermediate execution data — called on cancel."""
    self._plan = ""
    self._papers = []
    self._analysis = ""
    self._draft_sections = []
    self._validation_scores = {}
    self._retrieved_queries = []
    self._pending_expansions = []
    self._pending_revisions = []
    self.execution_log = []
    self.latex_repair_log = None
    self.last_result = None
    self._pipeline_retry_count = 0
    self._last_failed_stage = None
    self._error_message = ""
    self.feedback_queue = []
    self.feedback_history = []
    self.retry_count = 0
    self.has_warnings = False
```

- [ ] **Step 3: Add `cancel()` method to `Harness`**

```python
def cancel(self) -> None:
    """Cancel the current task irreversibly — mark as CANCELLED, save to history, clear all data."""
    if self.state.current_state in (
        AgentState.CANCELLED, AgentState.COMPLETE, AgentState.ERROR
    ):
        raise ValueError(
            f"Cannot cancel from terminal state: {self.state.current_state.name}"
        )
    if not self.task:
        raise ValueError("No active task to cancel")

    # Transition to CANCELLED
    self.state.transition_to(AgentState.CANCELLED)
    self._interrupt_event.set()
    self._pipeline_running = False
    self.current_stage = ""
    self.current_message = ""

    # Save cancelled record to history
    result = {
        "status": "cancelled",
        "paper": "",
        "rounds": 0,
        "has_warnings": False,
        "papers": [],
        "execution_log": [],
    }
    self._memory_integration.save_task_history(self.task, result)

    # Clear all intermediate data
    self._clear_all_data()
    self._orchestrator.reset_state()
```

- [ ] **Step 4: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add agent/core/harness.py agent/core/pipeline.py
git commit -m "feat: add cancel() method to Harness with data cleanup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Backend API — Add Cancel Endpoint

**Files:**
- Modify: `api/routes/survey.py`

**Interfaces:**
- Consumes: `Harness.cancel()` (from Task 2)
- Produces: `POST /api/survey/cancel` endpoint

- [ ] **Step 1: Add cancel endpoint to survey router**

```python
@router.post("/cancel", response_model=SurveyResponse)
async def cancel_survey(harness: Harness = Depends(get_harness)):
    try:
        harness.cancel()
    except ValueError as e:
        info = harness.get_task_info()
        info["error"] = str(e)
        return SurveyResponse(**info)
    info = harness.get_task_info()
    return SurveyResponse(**info)
```

Place this after the existing `interrupt` endpoint.

- [ ] **Step 2: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add api/routes/survey.py
git commit -m "feat: add POST /api/survey/cancel endpoint

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Frontend API Client — Add `cancelSurvey()`

**Files:**
- Modify: `web/src/api/client.ts`

**Interfaces:**
- Consumes: (none)
- Produces: `cancelSurvey()` export

- [ ] **Step 1: Add `cancelSurvey()` function**

```typescript
export async function cancelSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/cancel`, { method: "POST" });
  return res.json();
}
```

Place it after the existing `interruptSurvey()` function.

- [ ] **Step 2: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add web/src/api/client.ts
git commit -m "feat: add cancelSurvey API client function

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Frontend AgentExecution — Remove Pause/Resume, Keep Cancel

**Files:**
- Modify: `web/src/pages/AgentExecution.tsx`

**Interfaces:**
- Consumes: `cancelSurvey()` (from Task 4), `getSurveyStatus()`, `ConfirmDialog`, `useToast`
- Produces: Updated execution page with only "Cancel Task" button

- [ ] **Step 1: Update imports — remove `resumeSurvey`, add `cancelSurvey`**

Change:
```typescript
import { getSurveyStatus, submitFeedback, restartSurvey, interruptSurvey, resumeSurvey } from "../api/client";
```
To:
```typescript
import { getSurveyStatus, submitFeedback, restartSurvey, cancelSurvey } from "../api/client";
```

- [ ] **Step 2: Remove `handleInterrupt()` and `handleResume()` methods**

Delete the `handleInterrupt` function (lines 185-195) and `handleResume` function (lines 197-204).

- [ ] **Step 3: Remove `interrupting` state variable**

Delete line:
```typescript
const [interrupting, setInterrupting] = useState(false);
```

- [ ] **Step 4: Update `handleCancel()` to call `cancelSurvey()` and reset page**

Change:
```typescript
const handleCancel = async () => {
    setShowCancelDialog(false);
    try {
      await interruptSurvey();
      showToast("info", "Task cancelled");
    } catch {
      showToast("error", "Cancel failed");
    }
};
```
To:
```typescript
const handleCancel = async () => {
    setShowCancelDialog(false);
    try {
      await cancelSurvey();
      setProgress(null);
      showToast("info", "任务已取消");
    } catch {
      showToast("error", "取消失败");
    }
};
```

- [ ] **Step 5: Update pipeline control buttons — remove Pause/Resume, keep only Cancel**

Replace the button area (lines 510-528):
```tsx
{/* Pipeline control buttons */}
<div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
  {pipelineRunning && (
    <>
      <Button variant="ghost" size="sm" onClick={handleInterrupt} loading={interrupting}
        style={{ color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}>
        ⏸ Pause
      </Button>
      <Button variant="danger" size="sm" onClick={() => setShowCancelDialog(true)}>
        ⏹ Cancel
      </Button>
    </>
  )}
  {isInterrupted && (
    <Button variant="primary" size="sm" onClick={handleResume}
      style={{ background: "var(--color-success)", color: "#fff" }}>
      ▶ Resume
    </Button>
  )}
</div>
```
With:
```tsx
{/* Pipeline control buttons — only Cancel */}
<div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
  {pipelineRunning && (
    <Button variant="danger" size="sm" onClick={() => setShowCancelDialog(true)}>
      ⏹ 取消任务
    </Button>
  )}
</div>
```

- [ ] **Step 6: Update ConfirmDialog message**

Change:
```tsx
message="This will stop the current pipeline. You can start a new task from the Dashboard."
```
To:
```tsx
message="此操作将取消当前任务并清空所有过程数据，且不可恢复。确定取消？"
```

- [ ] **Step 7: Update `pipelineFinished` condition to exclude CANCELLED**

Change:
```typescript
const pipelineFinished = !connected
    && progress?.pipeline_running === false
    && progress?.task_started_at
    && (progress?.status === "COMPLETE" || progress?.status === "ERROR");
```
To:
```typescript
const pipelineFinished = !connected
    && progress?.pipeline_running === false
    && progress?.task_started_at
    && progress?.status !== "CANCELLED"
    && (progress?.status === "COMPLETE" || progress?.status === "ERROR");
```

- [ ] **Step 8: Remove unused `isInterrupted` variable (or keep it — it's harmless)**

The `isInterrupted` variable is no longer used for rendering, but it doesn't cause errors. No change needed.

- [ ] **Step 9: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add web/src/pages/AgentExecution.tsx
git commit -m "feat: remove pause/resume buttons, update cancel to call cancelSurvey

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Frontend HistoryDetail — Show Cancelled State

**Files:**
- Modify: `web/src/pages/HistoryDetail.tsx`

**Interfaces:**
- Consumes: `entry.status === "cancelled"` from history API
- Produces: Cancelled-appropriate rendering

- [ ] **Step 1: Add cancelled status badge color**

In the summary card, update the badge color logic. Find the `borderColor` and `Badge` color mappings:

Change:
```tsx
borderColor={entry.has_warnings ? "var(--color-warning)" : "var(--color-success)"}
```
To:
```tsx
borderColor={entry.status === "cancelled" ? "var(--color-text-disabled)" : entry.has_warnings ? "var(--color-warning)" : "var(--color-success)"}
```

Change the title text:
```tsx
title={<span style={{ fontWeight: 600 }}>Status: {entry.status === "complete" ? "Completed" : entry.status}</span>}
```
To:
```tsx
title={<span style={{ fontWeight: 600 }}>Status: {entry.status === "complete" ? "Completed" : entry.status === "cancelled" ? "已取消" : entry.status}</span>}
```

- [ ] **Step 2: Add cancelled message card**

After the summary card (before the papers section), add a cancelled-state card:

```tsx
{entry.status === "cancelled" && (
  <Card borderColor="var(--color-text-disabled)">
    <div style={{ textAlign: "center", padding: "2rem 1rem" }}>
      <div style={{ fontSize: "3rem", marginBottom: "0.5rem" }}>🛑</div>
      <h3 style={{ margin: "0 0 0.5rem", color: "var(--color-text-secondary)" }}>
        任务已手动取消
      </h3>
      <p style={{ margin: 0, color: "var(--color-text-disabled)", fontSize: "var(--font-size-sm)" }}>
        该任务已被手动取消，无过程数据可展示。
      </p>
    </div>
  </Card>
)}
```

- [ ] **Step 3: Guard paper list, final paper, and export buttons**

Wrap the paper list section, final paper section, and export buttons with `{entry.status !== "cancelled" && (`:

```tsx
{entry.status !== "cancelled" && entry.papers.length > 0 && (
  <Card title="📚 Retrieved Papers">
    ...
  </Card>
)}

{entry.status !== "cancelled" && sections.length > 0 && (
  <Card title="📄 Final Paper">
    ...
  </Card>
)}

{entry.status !== "cancelled" && sections.length === 0 && entry.final_paper && (
  <Card title="📄 Full Paper">
    ...
  </Card>
)}

{entry.status !== "cancelled" && entry.final_paper && (
  <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
    ...
  </div>
)}
```

- [ ] **Step 4: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add web/src/pages/HistoryDetail.tsx
git commit -m "feat: show cancelled state in history detail page

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Frontend Dashboard + StageTimeline — Badge + Cleared Timeline

**Files:**
- Modify: `web/src/pages/Dashboard.tsx`
- Modify: `web/src/components/StageTimeline.tsx`

**Interfaces:**
- Consumes: `progress?.status === "CANCELLED"` for timeline, `item.status === "cancelled"` for dashboard
- Produces: Gray badge for cancelled in history list, cleared timeline after cancel

- [ ] **Step 1: Dashboard - add cancelled badge color**

In `Dashboard.tsx`, find the badge color mapping in the history list section:

```tsx
<Badge color={item.status === "complete" ? "green" : item.status === "error" ? "red" : "gray"}>
  {item.status}
</Badge>
```

Change `item.status === "error" ? "red" : "gray"` to `item.status === "error" ? "red" : item.status === "cancelled" ? "gray" : "gray"`:

```tsx
<Badge color={item.status === "complete" ? "green" : item.status === "error" ? "red" : item.status === "cancelled" ? "gray" : "gray"}>
  {item.status === "cancelled" ? "已取消" : item.status}
</Badge>
```

- [ ] **Step 2: StageTimeline - add `pipelineCancelled` prop**

In `StageTimeline.tsx`, add `pipelineCancelled` to the props interface:

```typescript
export interface StageTimelineProps {
  currentStage: string;
  stageOrder: string[];
  stageLabels: Record<string, string>;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
  pipelineError?: boolean;
  pipelineCancelled?: boolean;  // ← NEW
}
```

- [ ] **Step 3: StageTimeline - handle cancelled state**

In `getStageStatus()`, when `pipelineCancelled` is true, return `"pending"` for all stages:

Add a parameter:
```typescript
function getStageStatus(
  stage: string,
  currentStage: string,
  stageOrder: string[],
  pipelineCancelled?: boolean,
): StageStatus {
  if (pipelineCancelled) return "pending";  // ← NEW: all pending when cancelled
  const currentIdx = stageOrder.indexOf(currentStage);
  const stageIdx = stageOrder.indexOf(stage);
  if (currentIdx < 0 || stageIdx < 0) return "pending";
  if (stageIdx < currentIdx) return "completed";
  if (stageIdx === currentIdx) return "active";
  return "pending";
}
```

- [ ] **Step 4: StageTimeline - pass prop through**

In the main `StageTimeline` component, destructure `pipelineCancelled` from props and pass it to `getStageStatus`:

```typescript
const { pipelineCancelled = false } = props;

// Then in the map:
const status = getStageStatus(stage, currentStage, stageOrder, pipelineCancelled);
```

- [ ] **Step 5: AgentExecution - pass `pipelineCancelled` to StageTimeline**

In `AgentExecution.tsx`, add the `pipelineCancelled` prop to both `StageTimeline` usages:

```tsx
<StageTimeline
  currentStage={currentStage}
  stageOrder={STAGE_ORDER}
  stageLabels={STAGE_LABELS}
  executionDetails={progress?.execution_details ?? null}
  currentMessage={progress?.current_message ?? ""}
  pipelineRunning={pipelineRunning}
  pipelineError={progress?.status === "ERROR"}
  pipelineCancelled={progress?.status === "CANCELLED"}  // ← NEW
/>
```

- [ ] **Step 6: Commit**

```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
git add web/src/pages/Dashboard.tsx web/src/components/StageTimeline.tsx
git commit -m "feat: support cancelled badge in dashboard and cleared timeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Verification

- [ ] **Run backend tests**
```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature
python -m pytest tests/ -v
```

- [ ] **Build frontend**
```bash
cd D:/ScholarAgent/.claude/worktrees/task-cancel-feature/web
npm run build 2>&1 | tail -20
```

- [ ] **Final review checklist**
  - [ ] `state.py` has CANCELLED enum value and transitions
  - [ ] `harness.py` has `cancel()` method that saves to history and clears data
  - [ ] `pipeline.py` has `reset_state()` method
  - [ ] `survey.py` has `POST /api/survey/cancel` endpoint
  - [ ] `client.ts` has `cancelSurvey()` function
  - [ ] `AgentExecution.tsx` has no pause/resume buttons, only cancel
  - [ ] `HistoryDetail.tsx` shows "已取消" for cancelled tasks
  - [ ] `Dashboard.tsx` shows gray badge for cancelled history items
  - [ ] `StageTimeline.tsx` clears all marks when cancelled