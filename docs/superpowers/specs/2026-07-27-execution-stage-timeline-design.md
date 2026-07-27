# Execution Page: Stage Result Timeline

## Summary

Transform the current flat `execution_details` rendering on the Agent Execution page into a vertical timeline that displays each pipeline stage's output progressively as it completes, enabling users to review and provide feedback on intermediate results.

## Motivation

Currently, when the stage chain at the top of the Execution page advances (e.g., from "Planning" to "Retrieval"), the section below shows all execution details in a single flat block without clear visual association to their originating stage. Users cannot tell which stage produced which artifact, making it hard to review intermediate results (e.g., the agent's plan) and provide timely feedback.

## Design

### Stage–Artifact Mapping

Each pipeline stage produces a specific artifact. The timeline groups artifacts by stage:

| Stage | Artifact(s) | Data Source (`execution_details.*`) |
|-------|-------------|--------------------------------------|
| planning | Research plan (section count, preview lines) | `plan` |
| retrieval | Search queries, paper list | `search_queries`, `papers` |
| analysis | Analysis summary/preview | `analysis` |
| writing | Paper section structure | `sections` |
| validation | Quality check scores (pass/fail per dimension) | `validation` |
| format_repair | Change count summary | (derived from execution_log) |
| complete | Completion message | status text |

### Component Architecture

**New component: `StageTimeline`**

A vertical timeline component that replaces the current `renderExecutionDetails()` function. It is subdivided into per-stage sections.

**Props / data:**

```typescript
interface StageTimelineProps {
  currentStage: string;           // progress.current_stage
  stageOrder: string[];           // STAGE_ORDER
  executionDetails: ExecutionDetails;
  currentMessage: string;
  pipelineRunning: boolean;
}
```

**State derivation (no new backend fields needed):**

Each stage's status is computed from `currentStage` and `STAGE_ORDER`:

```typescript
function getStageStatus(stage: string, currentStage: string, stageOrder: string[]): "completed" | "active" | "pending" {
  const currentIdx = stageOrder.indexOf(currentStage);
  const stageIdx = stageOrder.indexOf(stage);
  if (stageIdx < currentIdx) return "completed";
  if (stageIdx === currentIdx) return "active";
  return "pending";
}
```

### Visual Layout

```
┌─ Stage Chain (horizontal bar, unchanged) ───────────────────┐
│  ▶ Planning → ✓ Retrieval → ○ Analysis → ○ Writing → ...  │
└─────────────────────────────────────────────────────────────┘

┌─ Timeline (left column, 2fr) ─────┐  ┌─ Feedback (1fr) ──┐
│                                    │  │                    │
│ ● ✅ Planning                      │  │  [feedback form]   │
│ │  ┌─ Plan Card ────────────────┐  │  │                    │
│ │  │ 6 sections, preview lines  │  │  │  [feedback history]│
│ │  └────────────────────────────┘  │  │                    │
│ │                                  │  │                    │
│ ● ▶ Retrieval (active...)          │  │                    │
│ │  [LoadingSkeleton]               │  │                    │
│ │  "Searching papers..."           │  │                    │
│ │                                  │  │                    │
│ ● ○ Analysis                       │  │                    │
│ ● ○ Writing                        │  │                    │
│ ● ○ Validation                     │  │                    │
│                                    │  │                    │
└────────────────────────────────────┘  └────────────────────┘
```

#### Stage entry visuals

| Status | Icon | Dot | Card background | Contents |
|--------|------|-----|-----------------|----------|
| Completed | ✅ | Green dot | White/light | Show full artifact card |
| Active | ▶ (pulsing) | Blue dot | Primary-light | Show LoadingSkeleton + current_message |
| Pending | ○ | Gray dot | None | Show stage label only |

#### Connection line

A vertical line runs along the left side connecting all dots, creating a timeline visual. The line color segments: green for completed, blue for active, gray for pending.

### Behavior

- **Completed stages remain visible** — users can scroll back to review earlier results.
- **Active stage** shows a loading skeleton and the current message from the backend.
- **Pending stages** are shown as gray placeholder entries with just the stage name.
- **On pipeline completion** all stages show their final artifacts; the timeline switches to single-column layout (no sidebar).
- **Error state** — the failed stage is marked with ❌ and shows the error message; earlier stages' artifacts remain visible.

### Layout Changes

**Two-column (running):** Timeline (2fr) + Feedback (1fr) — same as current grid but with timeline instead of flat details.

**Single-column (finished/error):** Timeline fills width. Feedback panel is hidden (feedback is no longer relevant after completion). Error panel renders below the timeline.

### Error Handling

- If `execution_details` is empty or null for a stage (e.g., stage completed but artifact wasn't saved), show a subtle "No data available" message instead of breaking the layout.
- If the pipeline errors during a stage, show ❌ for that stage with the error message, but keep preceding stages' artifacts visible.
- If `currentStage` is not found in `STAGE_ORDER` (unexpected value), render it as a generic "Unknown stage" entry.

## Files Changed

| File | Change |
|------|--------|
| `web/src/pages/AgentExecution.tsx` | Add `StageTimeline` component (`~120 lines`), replace `renderExecutionDetails()` calls, update layout logic |
| `web/src/pages/AgentExecution.tsx` | Remove `renderExecutionDetails()` function (replaced by `StageTimeline`) |
| `web/src/pages/AgentExecution.tsx` | Keep `renderStageChain()`, `renderCurrentMessage()`, `renderFeedbackPanel()`, `renderErrorPanel()` unchanged |

## What Does NOT Change

- Backend (Harness, PipelineOrchestrator, progress routes) — no changes needed.
- WebSocket hook — unchanged.
- Stage chain (horizontal bar) — unchanged.
- Feedback panel — unchanged.
- Error panel — unchanged.
- Confirm dialog — unchanged.
- Existing tests — unaffected.

## Testing

- **Unit:** Test `getStageStatus()` utility with completed/active/pending/edge cases.
- **Visual:** Verify each stage card renders correctly when its artifact data is present vs. absent.
- **Integration:** Run a full pipeline and confirm timeline entries appear progressively.
- **Edge cases:** Empty details, pipeline error mid-stage, rapid stage transitions, pipeline interrupted.