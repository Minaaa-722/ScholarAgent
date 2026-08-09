# Execution Page Progress Enhancement Design

**Date:** 2026-08-09
**Status:** Approved Design

## 1. Problem Statement

The Execution page currently shows only a generic loading skeleton and a single text message for each agent stage. Users cannot see the detailed progress within a stage — e.g., during paper search, they see only "Searching arXiv and Semantic Scholar?" with no indication of which query is active, how many papers have been found, or what sub-step is currently executing.

## 2. Solution Overview

Add two new fields to the progress data pushed from the backend to the frontend:

1. **`stage_messages`** — A list of timestamped, typed log messages showing the step-by-step narrative within each stage.
2. **`stage_metrics`** — A structured dictionary of quantitative indicators specific to the current stage.

The frontend replaces the generic `LoadingSkeleton` with a rich progress display that combines a scrolling message list with stage-specific metric cards.

## 3. Data Types

### Backend (Python)

```python
# In PipelineOrchestrator / Harness

stage_messages: list[dict] = [
    {"type": "info" | "success" | "warning" | "error",
     "message": str,
     "timestamp": str}  # ISO format
]

stage_metrics: dict = {
    # Planning stage
    "sections_count": int,
    # Retrieval stage
    "queries_total": int,
    "queries_completed": int,
    "papers_found": int,
    "papers_downloaded": int,
    "papers_total": int,
    # Analysis stage
    "papers_analyzed": int,
    "total_papers": int,
    "claims_extracted": int,
    "claims_verified": int,
    "benchmark_records": int,
    # Writing stage
    "round": int,
    "total_rounds": int,
    "sections_count": int,
    "word_count": int,
    "citations_injected": int,
    # Format repair stage
    "changes_count": int,
    # Validation stage
    "validators_passed": int,
    "validators_total": int,
    "overall_score": float,
}
```

### Frontend (TypeScript)

```typescript
interface StageMessage {
  type: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string;
}

interface StageMetrics {
  queries_total?: number;
  queries_completed?: number;
  papers_found?: number;
  papers_downloaded?: number;
  papers_total?: number;
  sections_count?: number;
  papers_analyzed?: number;
  total_papers?: number;
  claims_extracted?: number;
  claims_verified?: number;
  benchmark_records?: number;
  round?: number;
  total_rounds?: number;
  word_count?: number;
  citations_injected?: number;
  changes_count?: number;
  validators_passed?: number;
  validators_total?: number;
  overall_score?: number;
}
```

The `ProgressInfo` interface in `AgentExecution.tsx` gains:
```typescript
interface ProgressInfo {
  // ... existing fields
  stage_messages: StageMessage[];
  stage_metrics: StageMetrics;
}
```

## 4. Backend Changes

### 4.1 PipelineOrchestrator (`agent/core/pipeline.py`)

Add `stage_messages` and `stage_metrics` fields to `PipelineOrchestrator.__init__()`:
```python
self.stage_messages: list[dict] = []
self.stage_metrics: dict = {}
```

Add a helper method to emit progress messages:
```python
def _emit_progress(self, msg_type: str, message: str, metrics: Optional[dict] = None) -> None:
    """Record a progress message and optionally update stage metrics."""
    entry = {
        "type": msg_type,
        "message": message,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    self.stage_messages.append(entry)
    if metrics:
        self.stage_metrics.update(metrics)
```

Add `_progress()` calls with granular messages in each stage function:

**`_generate_plan()`:**
- Before LLM call: `_emit_progress("info", "Generating research plan...")`
- After LLM call: `_emit_progress("success", f"Research plan generated with {sections_count} sections", {"sections_count": sections_count})`

**`_retrieve_papers()`:**
- After generating queries: `_emit_progress("success", f"Generated {n} search queries", {"queries_total": n, "queries_completed": 0})`
- Per query, per source: alternating `_emit_progress("info", "Searching arXiv: query (i/n)...")` and `_emit_progress("success", f"arXiv: found {n} papers")`
- After merge: `_emit_progress("success", f"Merged: {n} unique papers", {"papers_found": n})`
- Per PDF download: `_emit_progress("info", f"Downloading PDFs ({i}/{total})...")` and `_emit_progress("success", f"PDF downloaded: {id}")` or `_emit_progress("warning", f"PDF download failed: {id}")`
- Per evidence extraction: `_emit_progress("info", f"Extracting evidence ({i}/{total})...")` and results

**`_analyze_papers()`:**
- Before LLM: `_emit_progress("info", f"Analyzing {n} papers via LLM...")`
- After LLM: `_emit_progress("success", "Paper analysis completed", {"papers_analyzed": n, "total_papers": n})`
- After claims: `_emit_progress("success", f"Extracted {n} claims", {"claims_extracted": n})`
- After verification: `_emit_progress("success", f"{n}/{total} claims verified", {"claims_verified": n})`
- After benchmarks: results

**`_write_survey()`:**
- Reference building, evidence context, LLM call, post-processing: each gets a message

**`_format_repair()`:**
- Result message with change count

**`_run_validators()`:**
- Per validator: `_emit_progress("info", f"Running {name}...")` followed by result
- After aggregation: `_emit_progress("info", f"Overall score: {score}", {"validators_passed": n, "validators_total": total, "overall_score": score})`

### 4.2 `_progress()` callback

Update `_progress()` to pass `stage_messages` and `stage_metrics`:
```python
def _progress(self, cb, stage, msg):
    self.current_stage = stage
    self.current_message = msg
    detail = self._build_task_info()
    detail["stage_messages"] = self.stage_messages[-20:]  # Last 20 messages
    detail["stage_metrics"] = self.stage_metrics
    if cb:
        cb(stage, msg, detail)
```

### 4.3 Harness (`agent/core/harness.py`)

`get_task_info()` should include `stage_messages` and `stage_metrics` from the orchestrator:
```python
"stage_messages": self._orchestrator.stage_messages[-20:],
"stage_metrics": self._orchestrator.stage_metrics,
```

### 4.4 Reset on pipeline start

In `run_pipeline()`, reset:
```python
self.stage_messages.clear()
self.stage_metrics.clear()
```

## 5. Frontend Changes

### 5.1 `AgentExecution.tsx`

Pass `stage_messages` and `stage_metrics` from progress data to `StageTimeline`:
```tsx
<StageTimeline
  currentStage={currentStage}
  stageOrder={STAGE_ORDER}
  stageLabels={STAGE_LABELS}
  executionDetails={progress?.execution_details ?? null}
  currentMessage={progress?.current_message ?? ""}
  pipelineRunning={pipelineRunning}
  stageMessages={progress?.stage_messages ?? []}
  stageMetrics={progress?.stage_metrics ?? {}}
/>
```

### 5.2 `StageTimeline.tsx`

**New props:**
```typescript
interface StageTimelineProps {
  // ... existing props
  stageMessages: StageMessage[];
  stageMetrics: StageMetrics;
}
```

**Replace LoadingSkeleton in `StageEntry`:**

When a stage is active and running, replace the current LoadingSkeleton block with:

1. **Metrics card** (if stage has relevant metrics) — shows quantitative progress
2. **Message list** — scrolling list of recent messages with icons

**Message rendering:**
```tsx
const MESSAGE_ICONS = {
  info: "⏳",
  success: "✅",
  warning: "⚠️",
  error: "❌",
};

const MESSAGE_COLORS = {
  info: "var(--color-primary)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  error: "var(--color-danger)",
};
```

**Metric rendering by stage:**

| Stage | Metric Display |
|-------|---------------|
| `planning` | Section count badge |
| `retrieval` | Progress bar: papers_downloaded/papers_total + "Found X papers" |
| `analysis` | Progress bar: papers_analyzed/total_papers + claims verified count |
| `writing` | Round indicator: "Round X/Y" + word count |
| `format_repair` | Changes count badge |
| `validation` | Validator results grid + overall score bar |

**Auto-scroll behavior:**
The message list container auto-scrolls to the bottom when new messages arrive. A CSS animation highlights new messages briefly.

### 5.3 CSS additions

```css
@keyframes message-fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.stage-message {
  animation: message-fade-in 0.3s ease-out;
}
```

## 6. Scope

### In Scope
- Add `stage_messages` and `stage_metrics` to backend progress push
- Add granular `_progress()` calls to all pipeline stages
- Update frontend `StageTimeline` to render rich progress
- Stage-specific metric cards

### Out of Scope (future)
- Interactive progress bar (click to see details)
- Historical progress replay
- Progress export/download

## 7. Files Changed

| File | Change |
|------|--------|
| `agent/core/pipeline.py` | Add `stage_messages`/`stage_metrics` fields, granular progress calls, reset logic |
| `agent/core/harness.py` | Pass `stage_messages`/`stage_metrics` in `get_task_info()` |
| `web/src/pages/AgentExecution.tsx` | Pass new props to StageTimeline |
| `web/src/components/StageTimeline.tsx` | Replace LoadingSkeleton, add message list + metric cards, new props interface |