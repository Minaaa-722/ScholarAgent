# Error Recovery System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add phase-level auto-retry and one-click restart to the Agent harness so that transient API errors don't force users to re-enter task parameters.

**Architecture:** Wrap each pipeline stage (PLANNING, RETRIEVAL, ANALYSIS, WRITING, FEEDBACK) in a retry helper that catches exceptions, transitions to ERROR, and retries the stage. After all retries are exhausted, expose a REST endpoint that re-launches the pipeline with the saved task parameters. The frontend detects the ERROR state and shows a restart button.

**Tech Stack:** Python 3.10+, FastAPI, React/TypeScript, WebSocket

**Current branch:** `feat/realtime-feedback` (all changes on this branch)

## Global Constraints

- State machine transitions must be explicitly listed in `_TRANSITIONS`
- The `_pipeline()` method is sequential — each stage depends on the previous stage's result
- LLM module (`OpenAILLM`) already has its own retry logic for transient errors — this is a second layer at the pipeline level
- All frontend state is driven by WebSocket messages from the server
- Frontend uses inline styles (no CSS modules or styled-components)
- API responses use `SurveyResponse` pydantic model

---

### Task 1: State Machine — Add ERROR recovery transitions

**Files:**
- Modify: `agent/core/state.py:18-29`

**Interfaces:**
- Consumes: existing `AgentState` enum and `_TRANSITIONS` dict
- Produces: updated `_TRANSITIONS` allowing `ERROR → PLANNING | RETRIEVAL | ANALYSIS | WRITING | VALIDATION`

- [ ] **Step 1: Modify `_TRANSITIONS` to add ERROR recovery paths**

Edit `agent/core/state.py` — change the `ERROR` entry from:
```python
AgentState.ERROR: {AgentState.IDLE},
```
to:
```python
AgentState.ERROR: {
    AgentState.IDLE,
    AgentState.PLANNING,
    AgentState.RETRIEVAL,
    AgentState.ANALYSIS,
    AgentState.WRITING,
    AgentState.VALIDATION,
},
```

- [ ] **Step 2: Verify the change**

```bash
cd D:/ScholarAgent
python -c "
from agent.core.state import StateMachine, AgentState
sm = StateMachine()
sm.transition_to(AgentState.ERROR)  # IDLE -> ERROR should fail
"
```

Expected: This should raise `ValueError` because `IDLE → ERROR` is not currently allowed. (The state machine can only reach ERROR via `_safe_transition` inside the harness.)

```bash
python -c "
from agent.core.state import StateMachine, AgentState
sm = StateMachine()
# Force ERROR state
sm.current_state = AgentState.ERROR
# Test new transitions
sm.transition_to(AgentState.PLANNING)
print('OK: ERROR -> PLANNING')
sm.transition_to(AgentState.ERROR)
sm.transition_to(AgentState.RETRIEVAL)
print('OK: ERROR -> RETRIEVAL')
sm.transition_to(AgentState.ERROR)
sm.transition_to(AgentState.ANALYSIS)
print('OK: ERROR -> ANALYSIS')
sm.transition_to(AgentState.ERROR)
sm.transition_to(AgentState.WRITING)
print('OK: ERROR -> WRITING')
sm.transition_to(AgentState.ERROR)
sm.transition_to(AgentState.VALIDATION)
print('OK: ERROR -> VALIDATION')
"
```

Expected: All 5 transitions succeed.

- [ ] **Step 3: Commit**

```bash
cd D:/ScholarAgent
git add agent/core/state.py
git commit -m "feat: add ERROR -> PLANNING|RETRIEVAL|ANALYSIS|WRITING|VALIDATION transitions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: API Model — Add error fields to SurveyResponse

**Files:**
- Modify: `api/models.py`

**Interfaces:**
- Consumes: existing `SurveyResponse` pydantic model
- Produces: `SurveyResponse` with `error`, `pipeline_retry_count`, `last_failed_stage` fields

- [ ] **Step 1: Add new fields to `SurveyResponse`**

Edit `api/models.py` — add three new fields after `task_started_at`:
```python
class SurveyResponse(BaseModel):
    ...
    task_started_at: str = ""
    error: str = ""
    pipeline_retry_count: int = 0
    last_failed_stage: str = ""
```

- [ ] **Step 2: Verify the model loads**

```bash
cd D:/ScholarAgent
python -c "
from api.models import SurveyResponse
r = SurveyResponse(status='error', error='test error', pipeline_retry_count=2, last_failed_stage='WRITING')
print(r.model_dump())
"
```

Expected: Prints the model with all fields, including the new error fields.

- [ ] **Step 3: Commit**

```bash
cd D:/ScholarAgent
git add api/models.py
git commit -m "feat: add error, pipeline_retry_count, last_failed_stage to SurveyResponse

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Harness — Add `_retry_on_error`, `restart()`, and stage wrapping

**Files:**
- Modify: `agent/core/harness.py:28-34` (HarnessConfig), `agent/core/harness.py:114-155` (__init__), `agent/core/harness.py:160-186` (start), `agent/core/harness.py:188-252` (get_task_info), `agent/core/harness.py:296-323` (run/run_async), `agent/core/harness.py:349-433` (_pipeline), `agent/core/harness.py:841-849` (_safe_llm_call area)
- Add new methods: `_retry_on_error()`, `_ensure_state()`, `restart()`

**Interfaces:**
- Consumes: `AgentState` enum, `HarnessConfig`, `ProgressCallback`, `StateMachine`
- Produces:
  - `HarnessConfig.max_pipeline_retries: int = 2`
  - `Harness.restart() -> None` — re-launches pipeline with saved task params
  - `Harness._retry_on_error(fn, stage, on_progress) -> Any` — wraps a stage call with retry
  - `Harness._ensure_state(target: AgentState) -> None` — transitions to target if not already there
  - `get_task_info()` now includes `error`, `pipeline_retry_count`, `last_failed_stage`
  - `_pipeline()` uses `_retry_on_error()` for all LLM-dependent stages

- [ ] **Step 1: Add `max_pipeline_retries` to `HarnessConfig`**

Edit `agent/core/harness.py` — add field after `quality_threshold`:
```python
@dataclass
class HarnessConfig:
    max_papers: int = 20
    max_retries: int = 3
    quality_threshold: float = 0.7
    max_pipeline_retries: int = 2  # Per-phase retries for transient errors (2 = 3 total attempts)
    year_start: int = 2020
    year_end: int = 2026
```

- [ ] **Step 2: Add new instance variables to `Harness.__init__`**

Edit `agent/core/harness.py` — add after `self.latex_repair_log = None` (~line 142):
```python
self._pipeline_retry_count: int = 0
self._last_failed_stage: Optional[AgentState] = None
self._error_message: str = ""
```

Also add the import if `Optional` is not already imported (it should be from line 5).

- [ ] **Step 3: Reset error state in `start()`**

Edit `agent/core/harness.py` — add after `self.retry_count = 0` (~line 167):
```python
self._pipeline_retry_count = 0
self._last_failed_stage = None
self._error_message = ""
```

- [ ] **Step 4: Add `_ensure_state()` and `_retry_on_error()` methods**

Add after `_check_human_feedback` (~line 773):
```python
# ------------------------------------------------------------------
# Error recovery helpers
# ------------------------------------------------------------------
def _ensure_state(self, target: AgentState) -> None:
    """Transition to target state if not already there."""
    if self.state.current_state != target:
        self._safe_transition(target)

def _retry_on_error(
    self,
    fn: Callable[[], Any],
    stage: AgentState,
    on_progress: Optional[ProgressCallback],
) -> Any:
    """Execute a stage function with phase-level retry.

    Retries up to max_pipeline_retries times on exception, with
    exponential backoff.  Preserves results from completed phases.
    """
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
                wait = 2 ** attempt  # 2s, 4s
                logger.warning(
                    "Stage %s failed (attempt %d/%d): %s. Retrying in %ds …",
                    stage.name, attempt, self.config.max_pipeline_retries + 1, e, wait,
                )
                self._progress(
                    on_progress, "retrying",
                    f"⚠ {stage.name} failed (attempt {attempt}/"
                    f"{self.config.max_pipeline_retries + 1}): "
                    f"{e!s:.80}. Retrying in {wait}s …",
                )
                time.sleep(wait)
            else:
                logger.error(
                    "Stage %s failed after %d attempts. Giving up.",
                    stage.name, self.config.max_pipeline_retries + 1,
                )
                raise  # All retries exhausted
```

- [ ] **Step 5: Add `restart()` method**

Add after the `_retry_on_error` method:
```python
def restart(self) -> None:
    """Re-launch the pipeline with the same task parameters from ERROR state."""
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

- [ ] **Step 6: Update `get_task_info()` to include error fields**

Edit `agent/core/harness.py` — find the return dict in `get_task_info()` (~line 236-251) and add:
```python
return {
    "topic": self.task.topic,
    "keywords": self.task.keywords,
    "goal": self.task.goal,
    "max_papers": self.task.max_papers,
    "status": self.state.current_state.name,
    "pipeline_running": self._pipeline_running,
    "current_stage": self.current_stage,
    "current_message": self.current_message,
    "retry_count": self.retry_count,
    "has_warnings": self.has_warnings,
    "task_started_at": self.task_started_at,
    "error": self._error_message,                          # new
    "pipeline_retry_count": self._pipeline_retry_count,      # new
    "last_failed_stage": self._last_failed_stage.name        # new
        if self._last_failed_stage else "",                  # new
    "execution_details": details,
    "feedback_queue": self.feedback_queue,
    "feedback_history": self.feedback_history,
}
```

Also add the same new fields to the early-return dict (when `self.task` is falsy, ~line 229-235):
```python
if not self.task:
    return {
        "status": self.state.current_state.name,
        "pipeline_running": self._pipeline_running,
        "error": self._error_message,
        "pipeline_retry_count": self._pipeline_retry_count,
        "last_failed_stage": self._last_failed_stage.name if self._last_failed_stage else "",
        "execution_details": details,
        "feedback_queue": self.feedback_queue,
        "feedback_history": self.feedback_history,
    }
```

- [ ] **Step 7: Wrap each stage in `_pipeline()` with `_retry_on_error()`**

Edit `agent/core/harness.py` — modify the `_pipeline()` method.

Replace the PLANNING stage call:
```python
# OLD:
plan = self._generate_plan()
# NEW:
plan = self._retry_on_error(
    lambda: self._generate_plan(), AgentState.PLANNING, on_progress)
```

Replace the RETRIEVAL stage call:
```python
# OLD:
papers = self._retrieve_papers(plan)
# NEW:
papers = self._retry_on_error(
    lambda: self._retrieve_papers(plan), AgentState.RETRIEVAL, on_progress)
```

Replace the ANALYSIS stage call:
```python
# OLD:
analysis = self._analyze_papers(papers, plan)
# NEW:
analysis = self._retry_on_error(
    lambda: self._analyze_papers(papers, plan), AgentState.ANALYSIS, on_progress)
```

Replace the WRITING stage call inside the loop:
```python
# OLD:
draft = self._write_survey(analysis, plan, papers, rounds)
# NEW:
draft = self._retry_on_error(
    lambda: self._write_survey(analysis, plan, papers, rounds),
    AgentState.WRITING, on_progress)
```

Replace the `_incorporate_feedback` call inside the loop:
```python
# OLD:
analysis = self._incorporate_feedback(analysis, repairs, plan)
# NEW:
analysis = self._retry_on_error(
    lambda: self._incorporate_feedback(analysis, repairs, plan),
    AgentState.FEEDBACK, on_progress)
```

- [ ] **Step 8: Verify the imports are complete**

Check that `Any` is imported from typing at the top of the file. If not, add it:
```python
from typing import Callable, Optional, Any
```
(It should already be there from `Callable` and `Optional` on line 5.)

- [ ] **Step 9: Test the harness compiles and runs**

```bash
cd D:/ScholarAgent
python -c "
from agent.core.harness import Harness, HarnessConfig
from agent.core.llm import MockLLM
llm = MockLLM(fixed_response='test')
h = Harness(HarnessConfig(max_pipeline_retries=1), llm)
print('Config.max_pipeline_retries:', h.config.max_pipeline_retries)
print('Instance vars:', h._pipeline_retry_count, h._last_failed_stage, h._error_message)

# Test restart raises when not in ERROR
try:
    h.restart()
    print('ERROR: should have raised')
except ValueError as e:
    print('OK: restart from non-ERROR raises:', e)

# Test _ensure_state
h.state.transition_to(AgentState.PLANNING)
h._ensure_state(AgentState.PLANNING)
print('OK: _ensure_state same state does nothing')
h._ensure_state(AgentState.ERROR)
print('OK: _ensure_state transitions')
"
```

Expected: All checks pass, restart raises ValueError when not in ERROR state.

- [ ] **Step 10: Commit**

```bash
cd D:/ScholarAgent
git add agent/core/harness.py
git commit -m "feat: add _retry_on_error, restart(), and stage-level retry wrapping

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: API — Add restart endpoint

**Files:**
- Modify: `api/routes/survey.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Harness.restart()` from Task 3, `SurveyResponse` from Task 2
- Produces: `POST /api/survey/restart` endpoint

- [ ] **Step 1: Add restart endpoint**

Edit `api/routes/survey.py` — add after `resume_survey`:
```python
@router.post("/restart", response_model=SurveyResponse)
async def restart_survey(harness: Harness = Depends(get_harness)):
    harness.restart()
    info = harness.get_task_info()
    return SurveyResponse(**info)
```

- [ ] **Step 2: Verify the endpoint loads**

```bash
cd D:/ScholarAgent
python -c "
from api.routes.survey import router
routes = [r.path for r in router.routes]
print('Routes:', routes)
assert '/restart' in routes, 'restart endpoint not found'
print('OK: restart endpoint registered')
"
```

Expected: Prints routes including `/restart`.

- [ ] **Step 3: Commit**

```bash
cd D:/ScholarAgent
git add api/routes/survey.py
git commit -m "feat: add POST /api/survey/restart endpoint for one-click restart

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: WebSocket — Keep streaming during ERROR state

**Files:**
- Modify: `api/routes/progress.py:18-19`

**Interfaces:**
- Consumes: `AgentState.ERROR` from state module
- Produces: WebSocket continues pushing updates when pipeline is in ERROR state

- [ ] **Step 1: Modify WebSocket stop condition**

Edit `api/routes/progress.py` — change the break condition:
```python
# OLD:
if not _harness._pipeline_running:
    break

# NEW:
from agent.core.state import AgentState
if not _harness._pipeline_running and _harness.state.current_state != AgentState.ERROR:
    break
```

- [ ] **Step 2: Verify the import is correct**

```bash
cd D:/ScholarAgent
python -c "
from agent.core.state import AgentState
print('AgentState.ERROR:', AgentState.ERROR)
"
```

Expected: Prints `AgentState.ERROR: AgentState.ERROR`.

- [ ] **Step 3: Commit**

```bash
cd D:/ScholarAgent
git add api/routes/progress.py
git commit -m "fix: keep WebSocket streaming during ERROR state so frontend sees error details

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Frontend API Client — Add restartSurvey()

**Files:**
- Modify: `web/src/api/client.ts`

**Interfaces:**
- Consumes: existing API base URL pattern
- Produces: `restartSurvey() -> Promise<any>` function

- [ ] **Step 1: Add `restartSurvey` function**

Edit `web/src/api/client.ts` — add after `resumeSurvey`:
```typescript
export async function restartSurvey() {
  const res = await fetch(`${API_BASE}/api/survey/restart`, { method: "POST" });
  return res.json();
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScholarAgent
git add web/src/api/client.ts
git commit -m "feat: add restartSurvey() API client function

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: AgentExecution — Add error panel and restart button

**Files:**
- Modify: `web/src/pages/AgentExecution.tsx`

- [ ] **Step 1: Add `restartSurvey` import**

Edit `web/src/pages/AgentExecution.tsx` — add `restartSurvey` to the import from `../api/client`:
```typescript
import { getSurveyStatus, submitFeedback, restartSurvey } from "../api/client";
```

- [ ] **Step 2: Add state for restart error and loading**

After `const [feedbackHistory, setFeedbackHistory] = useState<FeedbackItem[]>([]);` (~line 96), add:
```typescript
const [restarting, setRestarting] = useState(false);
const [restartError, setRestartError] = useState<string | null>(null);
```

- [ ] **Step 3: Add `retrying` stage label**

Edit `STAGE_LABELS`:
```typescript
const STAGE_LABELS: Record<string, string> = {
  starting: "Starting…",
  planning: "Planning Agent",
  retrieval: "Search Agent",
  analysis: "Analysis Agent",
  writing: "Writing Agent",
  validation: "Validation Agent",
  format_repair: "Format Repair",
  retrying: "Retrying…",
  complete: "Complete",
  error: "Error",
};
```

- [ ] **Step 4: Add `retrying` to `STAGE_ORDER`**

Add `"retrying"` before `"complete"`:
```typescript
const STAGE_ORDER = ["starting", "planning", "retrieval", "analysis", "writing", "validation", "format_repair", "retrying", "complete", "error"];
```

- [ ] **Step 5: Add handleRestart function**

After `handleSendFeedback` (after ~line 183), add:
```typescript
const handleRestart = async () => {
  setRestarting(true);
  setRestartError(null);
  try {
    await restartSurvey();
    setProgress(null);
    setConnected(false);
  } catch {
    setRestartError("重启失败，请稍后重试");
  } finally {
    setRestarting(false);
  }
};
```

- [ ] **Step 6: Add error panel rendering**

After `renderFeedbackPanel` (after ~line 488), add a new function:
```typescript
const renderErrorPanel = () => {
  if (progress?.status !== "ERROR" || pipelineRunning) return null;

  return (
    <div style={{
      background: "#ffebee", borderRadius: 8, padding: "1.5rem",
      borderLeft: "4px solid #f44336", marginBottom: "1.5rem",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <span style={{ fontSize: "1.5rem" }}>⚠</span>
        <h3 style={{ margin: 0, color: "#c62828" }}>Pipeline Error</h3>
      </div>

      {progress.last_failed_stage && (
        <p style={{ margin: "0.3rem 0", color: "#b71c1c", fontSize: "0.9rem" }}>
          Failed at stage: <strong>{progress.last_failed_stage}</strong>
          {progress.pipeline_retry_count > 0 && (
            <span> (after {progress.pipeline_retry_count} attempt{progress.pipeline_retry_count > 1 ? "s" : ""})</span>
          )}
        </p>
      )}

      {progress.error && (
        <div style={{
          background: "#fff", borderRadius: 6, padding: "0.8rem", marginTop: "0.5rem",
          fontFamily: "monospace", fontSize: "0.85rem", color: "#c62828",
          whiteSpace: "pre-wrap", wordBreak: "break-all",
        }}>
          {progress.error}
        </div>
      )}

      <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
        <button
          onClick={handleRestart}
          disabled={restarting}
          style={{
            padding: "0.7rem 2rem",
            background: restarting ? "#ccc" : "#f44336",
            color: "#fff", border: "none", borderRadius: 6,
            cursor: restarting ? "not-allowed" : "pointer",
            fontSize: "1rem", fontWeight: 600,
            display: "flex", alignItems: "center", gap: "0.5rem",
          }}
        >
          {restarting ? "重启中…" : "🔄 一键重启"}
        </button>
        {restartError && <span style={{ color: "#b71c1c", fontSize: "0.85rem" }}>{restartError}</span>}
      </div>
    </div>
  );
};
```

- [ ] **Step 7: Update the render logic to show error panel**

In the main return JSX, find the `pipelineFinished` section (around line 538-548) and replace it. Change the condition from `pipelineFinished` to handle error state separately:

Find the section:
```tsx
{pipelineFinished && (
  <div style={{...}}>
    <p>✓ Pipeline completed...</p>
  </div>
)}
```

Replace with:
```tsx
{/* Error panel */}
{renderErrorPanel()}

{/* Pipeline finished (success) */}
{pipelineFinished && progress?.status !== "ERROR" && (
  <div style={{
    background: "#e8f5e9", borderRadius: 8, padding: "1rem 1.5rem",
    borderLeft: "4px solid #4caf50",
  }}>
    <p style={{ margin: 0, color: "#2e7d32", fontWeight: 600 }}>
      ✓ Pipeline completed. {progress.has_warnings && "Completed with warnings."}
    </p>
  </div>
)}
```

- [ ] **Step 8: Update the `ProgressInfo` interface**

Add the new fields to the interface:
```typescript
interface ProgressInfo {
  ...
  error?: string;
  pipeline_retry_count?: number;
  last_failed_stage?: string;
  ...
}
```

- [ ] **Step 9: Commit**

```bash
cd D:/ScholarAgent
git add web/src/pages/AgentExecution.tsx
git commit -m "feat: add error panel with retry info and one-click restart button to AgentExecution

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Dashboard — Show error state with restart button

**Files:**
- Modify: `web/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add restartSurvey import**

```typescript
import { getSurveyStatus, restartSurvey } from "../api/client";
```

- [ ] **Step 2: Add restart state and handler**

After `const [currentTask, setCurrentTask] = useState<any>(null);`:
```typescript
const [restarting, setRestarting] = useState(false);
const [restartError, setRestartError] = useState<string | null>(null);

const handleRestart = async () => {
  setRestarting(true);
  setRestartError(null);
  try {
    await restartSurvey();
    setCurrentTask(null);
    // Re-fetch status
    const data = await getSurveyStatus();
    if (data.topic) setCurrentTask(data);
  } catch {
    setRestartError("重启失败，请稍后重试");
  } finally {
    setRestarting(false);
  }
};
```

- [ ] **Step 3: Add error state display**

Inside the currentTask card, after the status line (`<p>Status: {currentTask.status}</p>`), add error handling:
```tsx
{currentTask.status === "ERROR" && (
  <div style={{
    background: "#ffebee", borderRadius: 6, padding: "0.8rem",
    margin: "0.5rem 0", borderLeft: "3px solid #f44336",
  }}>
    <p style={{ margin: 0, color: "#c62828", fontSize: "0.85rem" }}>
      Error: {currentTask.error || "Unknown error"}
    </p>
    <button
      onClick={handleRestart}
      disabled={restarting}
      style={{
        marginTop: "0.5rem", padding: "0.4rem 1rem",
        background: restarting ? "#ccc" : "#f44336", color: "#fff",
        border: "none", borderRadius: 4, cursor: restarting ? "not-allowed" : "pointer",
        fontSize: "0.85rem",
      }}
    >
      {restarting ? "重启中…" : "🔄 一键重启"}
    </button>
    {restartError && <p style={{ color: "#b71c1c", fontSize: "0.8rem" }}>{restartError}</p>}
  </div>
)}
```

- [ ] **Step 4: Commit**

```bash
cd D:/ScholarAgent
git add web/src/pages/Dashboard.tsx
git commit -m "feat: add error state display and restart button to Dashboard

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: FinalReview — Add restart button to error panel

**Files:**
- Modify: `web/src/pages/FinalReview.tsx`

- [ ] **Step 1: Add restartSurvey import**

```typescript
import { getPaper, getSurveyStatus, restartSurvey } from "../api/client";
```

- [ ] **Step 2: Add restart state and handler**

After `const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);`:
```typescript
const [restarting, setRestarting] = useState(false);
const [restartError, setRestartError] = useState<string | null>(null);

const handleRestart = async () => {
  setRestarting(true);
  setRestartError(null);
  try {
    await restartSurvey();
    setResult(null);
    setLoading(true);
    // Re-fetch
    const [paperData, statusData] = await Promise.all([getPaper(), getSurveyStatus()]);
    setResult(paperData);
    setTaskInfo(statusData);
    setLoading(false);
  } catch {
    setRestartError("重启失败，请稍后重试");
  } finally {
    setRestarting(false);
  }
};
```

- [ ] **Step 3: Add restart button to error section**

Find the error section in the render (around line 90-103):
```tsx
if (result.status === "error") {
  return (
    <div>
      <h2>Final Review</h2>
      <div style={{...}}>
        <h3 style={{...}}>Pipeline Error</h3>
        <p style={{...}}>{result.error}</p>
      </div>
    </div>
  );
}
```

Replace with:
```tsx
if (result.status === "error") {
  return (
    <div>
      <h2>Final Review</h2>
      <div style={{
        background: "#ffebee", borderRadius: 8, padding: "1.5rem",
        borderLeft: "4px solid #f44336",
      }}>
        <h3 style={{ color: "#c62828", margin: 0 }}>Pipeline Error</h3>
        <p style={{ color: "#b71c1c" }}>{result.error}</p>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem" }}>
          <button
            onClick={handleRestart}
            disabled={restarting}
            style={{
              padding: "0.7rem 2rem",
              background: restarting ? "#ccc" : "#f44336",
              color: "#fff", border: "none", borderRadius: 6,
              cursor: restarting ? "not-allowed" : "pointer",
              fontSize: "1rem", fontWeight: 600,
              display: "flex", alignItems: "center", gap: "0.5rem",
            }}
          >
            {restarting ? "重启中…" : "🔄 一键重启"}
          </button>
          {restartError && <span style={{ color: "#b71c1c", fontSize: "0.85rem" }}>{restartError}</span>}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
cd D:/ScholarAgent
git add web/src/pages/FinalReview.tsx
git commit -m "feat: add restart button to error panel in FinalReview

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 10: Tests — Verify error recovery end-to-end

**Files:**
- Create: `tests/test_error_recovery.py`
- Test: full coverage of retry logic and restart

- [ ] **Step 1: Write test for `_retry_on_error` retries and succeeds**

```python
"""Tests for error recovery in the Agent harness."""
import time
import pytest
from agent.core.state import AgentState, StateMachine
from agent.core.harness import Harness, HarnessConfig
from agent.core.llm import MockLLM


class TestRetryOnError:
    """Phase-level retry logic."""

    def test_retry_eventually_succeeds(self):
        """Retry after transient failure, then succeed."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=2), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()
        h.state.current_state = AgentState.PLANNING

        call_count = [0]

        def flaky_fn():
            call_count[0] += 1
            if call_count[0] < 2:  # Fail first call
                raise ConnectionError("API timeout")
            return "success"

        result = h._retry_on_error(flaky_fn, AgentState.PLANNING, None)
        assert result == "success"
        assert call_count[0] == 2  # 1 fail + 1 success

    def test_retry_exhausted_raises(self):
        """All retries exhausted should raise the original exception."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=1), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()
        h.state.current_state = AgentState.PLANNING

        def always_fails():
            raise RuntimeError("API unreachable")

        with pytest.raises(RuntimeError, match="API unreachable"):
            h._retry_on_error(always_fails, AgentState.PLANNING, None)

        assert h._pipeline_retry_count == 2  # 2 attempts (1 initial + 1 retry)
        assert h._last_failed_stage == AgentState.PLANNING
        assert h.state.current_state == AgentState.ERROR

    def test_retry_succeeds_first_try(self):
        """No retry needed when stage succeeds immediately."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=2), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()
        h.state.current_state = AgentState.PLANNING

        def works_first_time():
            return "immediate success"

        result = h._retry_on_error(works_first_time, AgentState.PLANNING, None)
        assert result == "immediate success"
        assert h._pipeline_retry_count == 0  # Never failed
        assert h._error_message == ""

    def test_retry_transitions_to_error(self):
        """Each failure transitions state to ERROR."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(max_pipeline_retries=1), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()
        h.state.current_state = AgentState.PLANNING
        call_count = [0]

        def fails_twice():
            call_count[0] += 1
            raise ValueError("bad data")

        with pytest.raises(ValueError):
            h._retry_on_error(fails_twice, AgentState.PLANNING, None)

        assert h.state.current_state == AgentState.ERROR


class TestRestart:
    """One-click restart from ERROR state."""

    def test_restart_from_error(self):
        """Restart should re-launch with saved task params."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test_topic", "keywords": ["kw1"], "goal": "test goal"})()
        h.state.current_state = AgentState.ERROR
        h._error_message = "something broke"

        h.restart()

        # After restart, should have started a new pipeline
        assert h._pipeline_running is True
        assert h._error_message == ""  # Reset

    def test_restart_not_error_raises(self):
        """Restart from non-ERROR state should raise."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.state.current_state = AgentState.COMPLETE

        with pytest.raises(ValueError, match="ERROR"):
            h.restart()

    def test_restart_no_task_raises(self):
        """Restart with no saved task should raise."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = None
        h.state.current_state = AgentState.ERROR

        with pytest.raises(ValueError, match="No task"):
            h.restart()


class TestGetTaskInfo:
    """Error fields in task info."""

    def test_error_fields_in_info(self):
        """get_task_info should include error, retry count, and failed stage."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()
        h.state.current_state = AgentState.ERROR
        h._error_message = "connection failed"
        h._pipeline_retry_count = 2
        h._last_failed_stage = AgentState.WRITING

        info = h.get_task_info()
        assert info["error"] == "connection failed"
        assert info["pipeline_retry_count"] == 2
        assert info["last_failed_stage"] == "WRITING"

    def test_error_fields_empty_when_no_error(self):
        """Error fields should be empty/default when no error."""
        llm = MockLLM(fixed_response="plan content")
        h = Harness(HarnessConfig(), llm)
        h.task = type("Task", (), {"topic": "test", "keywords": [], "goal": ""})()

        info = h.get_task_info()
        assert info["error"] == ""
        assert info["pipeline_retry_count"] == 0
        assert info["last_failed_stage"] == ""
```

- [ ] **Step 2: Run the tests**

```bash
cd D:/ScholarAgent
python -m pytest tests/test_error_recovery.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Run existing tests to ensure no regressions**

```bash
cd D:/ScholarAgent
python -m pytest tests/ -v
```

Expected: All existing tests still pass.

- [ ] **Step 4: Commit**

```bash
cd D:/ScholarAgent
git add tests/test_error_recovery.py
git commit -m "test: add error recovery tests for retry, restart, and task info

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 11: Integration verification — Run full pipeline with mock

**Files:**
- Run: entire test suite

- [ ] **Step 1: Run full test suite**

```bash
cd D:/ScholarAgent
python -m pytest tests/ -v 2>&1
```

Expected: All tests pass.

- [ ] **Step 2: Verify the harness handles a simulated error gracefully**

```bash
cd D:/ScholarAgent
python -c "
from agent.core.harness import Harness, HarnessConfig
from agent.core.llm import MockLLM

# Test with a mock LLM that fails on first call then succeeds
class FlakyMockLLM(MockLLM):
    def __init__(self):
        super().__init__(fixed_response='test response')
        self.call_count = 0
    def generate(self, system_prompt, user_message, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            raise ConnectionError('Simulated API timeout')
        return super().generate(system_prompt, user_message, tools)

llm = FlakyMockLLM()
h = Harness(HarnessConfig(max_pipeline_retries=1), llm)

result = h.run('test topic', keywords='test', goal='test goal')
print('Result status:', result['status'])
print('Pipeline retry count:', h._pipeline_retry_count)
print('Has papers:', len(h._papers) > 0 if h._papers else False)
print('Has plan:', bool(h._plan))
print('Error message:', h._error_message)
"
```

Expected: The pipeline should succeed (retry works), or if it fails at a later stage, show appropriate error state.

- [ ] **Step 3: Commit**

```bash
cd D:/ScholarAgent
git add -A
git commit -m "test: integration verification of error recovery pipeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```