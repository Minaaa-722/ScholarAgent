# Task Cancel Feature — Specification

## Overview

Replace the existing pause/resume/cancel mechanism with a single "Cancel Task" button. Cancelling a task is a one-way, irreversible action that marks the task as `cancelled` in history, clears all intermediate execution data, and resets the timeline UI to its initial blank state.

## Scope

Only state management, interrupt/cancel API, frontend button rendering, and history detail display. Existing LLM calls and paper retrieval business logic are untouched.

---

## 1. Backend: State Enum (`agent/core/state.py`)

### Change
Add `CANCELLED` to `AgentState` enum and update the transition matrix.

### New State
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
    CANCELLED = auto()       # ← NEW
    COMPLETE = auto()
    ERROR = auto()
```

### Transition Rules
- Any non-terminal state (IDLE, PLANNING, RETRIEVAL, ANALYSIS, WRITING, VALIDATION, FEEDBACK, INTERRUPTED) → CANCELLED
- CANCELLED → set() (terminal — no transitions out)
- COMPLETE, ERROR → CANCELLED is NOT allowed (already terminal)
- `is_terminal()` returns True for CANCELLED

### `interrupt()` Guard
Add `AgentState.CANCELLED` to the existing guard list so double-cancel is a no-op (ValueError caught by the API handler).

---

## 2. Backend: Harness Cancel Method (`agent/core/harness.py`)

### New Method: `cancel()`

```python
def cancel(self) -> None:
    # ① Validate state — already terminal/cancelled → raise
    if self.state.current_state in (
        AgentState.CANCELLED, AgentState.COMPLETE, AgentState.ERROR
    ):
        raise ValueError(
            f"Cannot cancel from terminal state: {self.state.current_state.name}"
        )
    if not self.task:
        raise ValueError("No active task to cancel")

    # ② Transition to CANCELLED
    self.state.transition_to(AgentState.CANCELLED)
    self._interrupt_event.set()       # Stop running pipeline thread
    self._pipeline_running = False
    self.current_stage = ""
    self.current_message = ""

    # ③ Save cancelled record to history
    result = {
        "status": "cancelled",
        "paper": "",
        "rounds": 0,
        "has_warnings": False,
        "papers": [],
        "execution_log": [],
    }
    self._memory_integration.save_task_history(self.task, result)

    # ④ Clear all intermediate data
    self._clear_all_data()

    # ⑤ Reset orchestrator state
    self._orchestrator.reset_state()
```

### New Helper: `_clear_all_data()`

Clears the following fields on both `self` (Harness) and `self._orchestrator`:

- `_plan`, `_papers`, `_analysis`, `_draft_sections`, `_validation_scores`
- `_retrieved_queries`, `_pending_expansions`, `_pending_revisions`
- `execution_log`, `latex_repair_log`, `last_result`
- `_pipeline_retry_count`, `_last_failed_stage`, `_error_message`
- `feedback_queue`, `feedback_history`
- `retry_count`, `has_warnings`

### How `reset_state()` works on PipelineOrchestrator

Reset all pipeline state fields to their default values (empty strings, empty lists, zeros, None). This is already partially implemented as the reset block at the top of `run_pipeline()` — extract it into a dedicated method.

---

## 3. Backend: API Route (`api/routes/survey.py`)

### New Endpoint: `POST /api/survey/cancel`

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

- Catches `ValueError` from duplicate cancel attempts and returns a friendly error message in the response body (not an HTTP 500).
- Returns `SurveyResponse` with status `CANCELLED` on success.

---

## 4. Frontend: API Client (`web/src/api/client.ts`)

### New Function

```typescript
export async function cancelSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/cancel`, { method: "POST" });
  return res.json();
}
```

---

## 5. Frontend: Agent Execution Page (`web/src/pages/AgentExecution.tsx`)

### Button Changes

| Before | After |
|--------|-------|
| ⏸ Pause (ghost button) | **Removed** |
| ▶ Resume (primary button) | **Removed** |
| ⏹ Cancel (danger button, with ConfirmDialog) | **Kept, unchanged** |

### State/Logic Changes

- Remove `handleInterrupt()` and `handleResume()` methods
- Remove `handleCancel()` body — replace `interruptSurvey()` call with `cancelSurvey()`
- Remove `interrupting` state variable (no longer needed)
- Remove `resumeSurvey` from imports
- After cancel succeeds: `setProgress(null)` — resets page to default blank state
- Update `pipelineFinished` condition: exclude `CANCELLED` status so it doesn't show as "completed"
- The `isInterrupted` variable is no longer used for button rendering, but may be kept for other display logic

### ConfirmDialog Message Update
Update message from: "This will stop the current pipeline. You can start a new task from the Dashboard."
To: "此操作将取消当前任务并清空所有过程数据，且不可恢复。确定取消？"

---

## 6. Frontend: History Detail Page (`web/src/pages/HistoryDetail.tsx`)

### When `entry.status === "cancelled"`

- Show a neutral card (no green/red border) with message:
  - **Status:** 已取消
  - **Message:** 任务已手动取消，无过程数据
- Do NOT render paper list section
- Do NOT render final paper section
- Do NOT render export buttons
- Show basic info (topic, keywords, goal, timestamp) only

### Badge Color
- `cancelled` → gray badge

---

## 7. Frontend: Dashboard (`web/src/pages/Dashboard.tsx`)

### History List Badge
Add `cancelled` to the status badge color mapping:
```typescript
item.status === "cancelled" ? "gray" : ...
```

---

## 8. Frontend: Stage Timeline (`web/src/components/StageTimeline.tsx`)

### When Pipeline is Cancelled

- Add a `pipelineCancelled` prop (optional, default false)
- When `pipelineCancelled` is true: all stages render as `pending` (gray dots, no ✓, no ✗, no ▶)
- No artifact cards shown
- Effectively the same visual as before any task was started

---

## Files Not Modified

| File | Reason |
|------|--------|
| `agent/core/pipeline.py` | No business logic change; interrupt event already respected |
| `agent/core/llm.py` | No change needed |
| `agent/memory/integration.py` | `save_task_history()` already accepts any status string |
| `agent/memory/session.py` | No change needed |
| `api/models.py` | `HistoryItem.status` and `SurveyResponse` fields are already generic strings |
| `web/src/App.tsx` | No routing changes |
| `web/src/components/ConfirmDialog.tsx` | Already generic; no change needed |
| Any LLM/tool/retrieval file | Business code untouched |

## Error Handling

- Duplicate cancel: `ValueError` caught at API layer → returned as `{error: "..."}` in response, not thrown as HTTP 500
- Cancel after complete/error: same as above
- Cancel with no task: same as above
- Frontend: `cancelSurvey()` catch → `showToast("error", "取消失败")`

## Test Scenarios

1. Cancel a running task → state = CANCELLED, history entry created, timeline cleared
2. Cancel a paused (INTERRUPTED) task → same as above
3. Double-click cancel → second call returns error message, no crash
4. Cancel after COMPLETE → error message returned
5. Cancel after ERROR → error message returned
6. Cancel with no task → error message returned
7. View cancelled task in history → shows "已手动取消，无过程数据"
8. Dashboard shows cancelled badge correctly