# Error Recovery System: Phase-Level Auto-Retry & One-Click Restart

## Overview

When the Agent harness encounters API connection errors or other transient failures during paper-writing tasks, the system should automatically retry the failed phase (preserving completed phases) up to 3 total attempts. If all retries are exhausted, an ERROR state is shown in the UI with a one-click "Restart" button that re-launches the task with the same parameters.

## Architecture

### State Machine Changes (`agent/core/state.py`)

Add ERROR → PLANNING | RETRIEVAL | ANALYSIS | WRITING | VALIDATION transitions so the harness can return from ERROR to the failed phase for retry:

```python
_TRANSITIONS = {
    ...
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

### Harness Changes (`agent/core/harness.py`)

#### New Config

```python
@dataclass
class HarnessConfig:
    ...
    max_pipeline_retries: int = 2  # Each phase gets 2 extra retries (3 total attempts)
```

#### New State Variables

```python
self._pipeline_retry_count: int = 0
self._last_failed_stage: Optional[AgentState] = None
self._error_message: str = ""
```

#### `_retry_on_error()` Helper

A new method that wraps any phase's execution with retry logic:

```python
def _retry_on_error(self, fn, stage, on_progress):
    for attempt in range(1, self.config.max_pipeline_retries + 2):
        try:
            self._ensure_state(stage)
            return fn()
        except Exception as e:
            self._pipeline_retry_count = attempt
            self._last_failed_stage = stage
            self._error_message = str(e)
            self._safe_transition(AgentState.ERROR)
            self._log("ERROR", {
                "stage": stage.name,
                "error": str(e),
                "attempt": attempt,
                "max_attempts": self.config.max_pipeline_retries + 1,
            })

            if attempt <= self.config.max_pipeline_retries:
                wait = 2 ** attempt  # 2s, 4s exponential backoff
                self._progress(on_progress, "retrying",
                    f"⚠ {stage.name} failed (attempt {attempt}/{self.config.max_pipeline_retries + 1}): "
                    f"{e!s:.80}. Retrying in {wait}s…")
                time.sleep(wait)
            else:
                raise  # All retries exhausted, propagate up
```

#### `_ensure_state()` Helper

```python
def _ensure_state(self, target: AgentState) -> None:
    """Transition to target state if not already there (handles ERROR recovery)."""
    if self.state.current_state != target:
        self._safe_transition(target)
```

#### `_pipeline()` Stage Wrapping

Each stage call in `_pipeline()` is wrapped with `_retry_on_error()`:

```python
# PLANNING
plan = self._retry_on_error(
    lambda: self._generate_plan(), AgentState.PLANNING, on_progress)

# RETRIEVAL
papers = self._retry_on_error(
    lambda: self._retrieve_papers(plan), AgentState.RETRIEVAL, on_progress)

# ANALYSIS
analysis = self._retry_on_error(
    lambda: self._analyze_papers(papers, plan), AgentState.ANALYSIS, on_progress)

# WRITING (inside the loop)
draft = self._retry_on_error(
    lambda: self._write_survey(analysis, plan, papers, rounds),
    AgentState.WRITING, on_progress)

# Feedback incorporation (inside the loop)
analysis = self._retry_on_error(
    lambda: self._incorporate_feedback(analysis, repairs, plan),
    AgentState.FEEDBACK, on_progress)
```

Local-only stages (format_repair, validation) are not wrapped since they don't make API calls.

#### `restart()` Method

```python
def restart(self) -> None:
    """One-click restart: re-launch the entire pipeline with the same parameters."""
    if self.state.current_state != AgentState.ERROR:
        raise ValueError("Can only restart from ERROR state")
    if not self.task:
        raise ValueError("No task to restart")

    # Reset error state
    self._pipeline_retry_count = 0
    self._last_failed_stage = None
    self._error_message = ""

    self.run_async(
        topic=self.task.topic,
        keywords=", ".join(self.task.keywords),
        goal=self.task.goal,
    )
```

#### `get_task_info()` Additions

```python
return {
    ...
    "error": self._error_message,                      # new
    "pipeline_retry_count": self._pipeline_retry_count,  # new
    "last_failed_stage": self._last_failed_stage.name if self._last_failed_stage else None,  # new
}
```

#### `run()` Error Handling

The existing top-level `try/except` in `run()` remains as the last line of defense. If all phase-level retries are exhausted, the exception propagates to `run()` which transitions to ERROR and returns `{"status": "error", ...}`.

### API Changes (`api/routes/survey.py`)

New endpoint:

```python
@router.post("/restart", response_model=SurveyResponse)
async def restart_survey(harness: Harness = Depends(get_harness)):
    harness.restart()
    info = harness.get_task_info()
    return SurveyResponse(**info)
```

### WebSocket Changes (`api/routes/progress.py`)

Modify the stop condition so WebSocket continues pushing during ERROR state:

```python
if not _harness._pipeline_running and _harness.state.current_state != AgentState.ERROR:
    break
```

### API Model Changes (`api/models.py`)

Add optional error fields to `SurveyResponse`:

```python
class SurveyResponse(BaseModel):
    ...
    error: str = ""
    pipeline_retry_count: int = 0
    last_failed_stage: str = ""
```

### Frontend Client (`web/src/api/client.ts`)

```typescript
export async function restartSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/restart`, { method: "POST" });
  return res.json();
}
```

### Frontend: AgentExecution.tsx

**New stage label for retrying state:**

```typescript
const STAGE_LABELS: Record<string, string> = {
  ...
  retrying: "Retrying…",
  error: "Error",
};
```

**Error state detection:**

```typescript
const isError = progress?.status === "error" && !pipelineRunning;
```

**Error panel (shown when pipeline finishes with error):**

```
┌──────────────────────────────────────────────┐
│  ⚠ Pipeline Error                            │
│  Stage: WRITING (2/3 attempts)               │
│  Error: LLM API connection timeout            │
│                                              │
│  [🔄 一键重启]  [📋 查看执行日志]            │
│                                              │
│  Previous stages completed:                   │
│  ✓ Planning  ✓ Retrieval  ✓ Analysis         │
└──────────────────────────────────────────────┘
```

**Restart handler:**

```typescript
const handleRestart = async () => {
  try {
    await restartSurvey();
    // Reset local state; WebSocket will pick up the new task
    setProgress(null);
    setConnected(false);
  } catch (e) {
    setRestartError("重启失败，请稍后重试");
  }
};
```

**Retrying indicator (shown during auto-retry):**

The stage chain shows the failed stage with orange pulsing background and "Retrying (2/3)" text. The `current_message` from the server shows the retry countdown.

### Frontend: Dashboard.tsx

Add error state display with restart button:

```
┌──────────────────────────────────────┐
│  ⚠ Error: Writing phase failed       │
│  after 3 attempts                     │
│                                      │
│  [🔄 一键重启]  [View Error →]       │
└──────────────────────────────────────┘
```

### Frontend: FinalReview.tsx

Add restart button to the existing error panel alongside the error message:

```tsx
{result.status === "error" && (
  <div>
    <h3>Pipeline Error</h3>
    <p>{result.error}</p>
    <button onClick={handleRestart}>🔄 一键重启</button>
  </div>
)}
```

## Data Flow

```
[Phase execution] → Exception thrown → Harness._retry_on_error()
    ↓
[Retries remaining] → Show "Retrying (2/3)…" → Exponential backoff → Re-execute phase
    ↓
[Retries exhausted] → ERROR state → WebSocket keeps pushing error info
    ↓
[User clicks "Restart"] → POST /api/survey/restart
    ↓
[Harness.restart()] → Re-launch with same topic/keywords/goal via run_async()
    ↓
[WebSocket detects new task_started_at] → Frontend resets → Shows new progress
```

## Files Changed

| File | Change |
|------|--------|
| `agent/core/state.py` | Add ERROR→PLANNING/RETRIEVAL/ANALYSIS/WRITING/VALIDATION transitions |
| `agent/core/harness.py` | Add `_retry_on_error()`, `restart()`, `_ensure_state()`, state variables, modify `_pipeline()` stages |
| `api/routes/survey.py` | Add `POST /api/survey/restart` endpoint |
| `api/routes/progress.py` | Modify WebSocket stop condition for ERROR state |
| `api/models.py` | Add `error`, `pipeline_retry_count`, `last_failed_stage` to SurveyResponse |
| `web/src/api/client.ts` | Add `restartSurvey()` function |
| `web/src/pages/AgentExecution.tsx` | Add error panel, retrying indicator, restart button |
| `web/src/pages/Dashboard.tsx` | Add error state display + restart button |
| `web/src/pages/FinalReview.tsx` | Add restart button to error panel |

## Edge Cases

- **Non-retryable errors**: API auth failures (401/403) should not be retried — the LLM module's `_is_retryable()` already filters these; they propagate immediately.
- **Restart during retry**: If the user navigates away during auto-retry, the retry continues in the background thread. The WebSocket reconnects and the user sees the updated state.
- **Multiple rapid errors**: If the retry itself fails immediately (e.g., network is down), each retry has exponential backoff (2s, 4s). Total wait before exhaustion is ~6s per phase.
- **Restart after restart**: If the restarted task also fails, the user can restart again (no limit on manual restarts).