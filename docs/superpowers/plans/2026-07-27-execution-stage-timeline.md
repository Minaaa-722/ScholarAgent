# Stage Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `execution_details` rendering on the Execution page with a vertical timeline that shows each pipeline stage's output progressively as it completes.

**Architecture:** Extract a new `StageTimeline` component that receives execution details and stage status as props, rendering per-stage artifact cards in a vertical timeline. The parent `AgentExecution` page computes stage status from `current_stage` and `STAGE_ORDER`, then passes data down. No backend changes required.

**Tech Stack:** React (TypeScript), CSS-in-JS (inline styles, matching existing pattern in AgentExecution.tsx)

## Global Constraints

- No backend changes — all data is already available via `execution_details` from the WebSocket stream.
- Follow existing inline style patterns in `AgentExecution.tsx` (no CSS modules, no new dependencies).
- Stage artifact data may be null/missing — handle gracefully with fallback text.
- All existing tests must pass without modification.

---

### Task 1: Create `StageTimeline` component

**Files:**
- Create: `web/src/components/StageTimeline.tsx`
- Modify: none

**Interfaces:**
- Consumes: `ProgressInfo` shape (from `useWebSocket`), `STAGE_ORDER`, `STAGE_LABELS` (constants from `AgentExecution.tsx`)
- Produces: `<StageTimeline>` component with typed props

- [ ] **Step 1: Write the component skeleton with props interface**

```typescript
// web/src/components/StageTimeline.tsx
import React from "react";
import Card from "./Card";
import LoadingSkeleton from "./LoadingSkeleton";

export interface ExecutionDetails {
  plan?: { summary: string; preview: string[]; section_count: number };
  search_queries?: string[];
  papers?: { total: number; list: PaperInfo[] };
  analysis?: { summary: string; preview: string };
  sections?: SectionInfo[];
  validation?: Record<string, { score: number; passed: boolean; message: string }>;
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

export interface StageTimelineProps {
  currentStage: string;
  stageOrder: string[];
  stageLabels: Record<string, string>;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
}

type StageStatus = "completed" | "active" | "pending";

function getStageStatus(
  stage: string,
  currentStage: string,
  stageOrder: string[]
): StageStatus {
  const currentIdx = stageOrder.indexOf(currentStage);
  const stageIdx = stageOrder.indexOf(stage);
  if (currentIdx < 0 || stageIdx < 0) return "pending";
  if (stageIdx < currentIdx) return "completed";
  if (stageIdx === currentIdx) return "active";
  return "pending";
}

export default function StageTimeline(props: StageTimelineProps) {
  const { currentStage, stageOrder, stageLabels, executionDetails, currentMessage, pipelineRunning } = props;

  // Only show stages up to "retrying" (ignore "complete", "error" — those are handled by other panels)
  const displayStages = stageOrder.filter(s =>
    !["complete", "error", "retrying"].includes(s)
  );

  return (
    <div style={{ position: "relative" }}>
      {displayStages.map((stage, index) => {
        const status = getStageStatus(stage, currentStage, stageOrder);
        const label = stageLabels[stage] || stage;
        return (
          <StageEntry
            key={stage}
            stage={stage}
            label={label}
            status={status}
            isLast={index === displayStages.length - 1}
            executionDetails={executionDetails}
            currentMessage={currentMessage}
            pipelineRunning={pipelineRunning}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Write the `StageEntry` sub-component — handles the dot, connection line, and card rendering**

```typescript
// Inside StageTimeline.tsx, before StageTimeline default export

interface StageEntryProps {
  stage: string;
  label: string;
  status: StageStatus;
  isLast: boolean;
  executionDetails: ExecutionDetails | null;
  currentMessage: string;
  pipelineRunning: boolean;
}

function StageEntry({
  stage, label, status, isLast,
  executionDetails, currentMessage, pipelineRunning,
}: StageEntryProps) {
  const dotColor =
    status === "completed" ? "var(--color-success)" :
    status === "active" ? "var(--color-primary)" :
    "#ccc";

  const dotIcon =
    status === "completed" ? "✓" :
    status === "active" ? "▶" :
    "○";

  return (
    <div style={{ display: "flex", marginBottom: isLast ? 0 : "1rem", position: "relative" }}>
      {/* Left column: dot + connection line */}
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        width: 32, flexShrink: 0,
      }}>
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: dotColor, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "var(--font-size-xs)", fontWeight: 700,
          zIndex: 1,
          transition: "all 0.3s",
          animation: status === "active" && pipelineRunning ? "pulse 1.5s infinite" : "none",
        }}>
          {dotIcon}
        </div>
        {!isLast && (
          <div style={{
            width: 2, flex: 1,
            background: status === "completed" ? "var(--color-success)" :
                        status === "active" ? "var(--color-primary)" :
                        "#e0e0e0",
            marginTop: 4,
            transition: "background 0.3s",
          }} />
        )}
      </div>

      {/* Right column: stage label + artifact card */}
      <div style={{ flex: 1, marginLeft: "0.8rem", paddingBottom: isLast ? 0 : "0.5rem" }}>
        {/* Stage header */}
        <div style={{
          fontWeight: status === "active" ? 700 : 500,
          fontSize: "var(--font-size-sm)",
          color: status === "completed" ? "var(--color-success-dark)" :
                 status === "active" ? "var(--color-primary)" :
                 "var(--color-text-disabled)",
          marginBottom: status === "completed" || status === "active" ? "0.5rem" : 0,
          transition: "color 0.3s",
        }}>
          {label}
        </div>

        {/* Artifact card for completed/active stages */}
        {status === "completed" && (
          <StageArtifact stage={stage} details={executionDetails} />
        )}
        {status === "active" && pipelineRunning && (
          <div style={{
            background: "var(--color-primary-light)",
            borderRadius: "var(--radius-lg)", padding: "1rem",
            borderLeft: "3px solid var(--color-primary)",
          }}>
            <LoadingSkeleton variant="card" />
            {currentMessage && (
              <p style={{
                margin: "0.5rem 0 0", fontSize: "var(--font-size-sm)",
                color: "var(--color-text-secondary)", fontStyle: "italic",
              }}>
                {currentMessage}
              </p>
            )}
          </div>
        )}
        {status === "active" && !pipelineRunning && (
          <StageArtifact stage={stage} details={executionDetails} />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write the `StageArtifact` sub-component — renders the correct artifact for each stage**

```typescript
// Inside StageTimeline.tsx, before StageTimeline default export

function StageArtifact({ stage, details }: { stage: string; details: ExecutionDetails | null }) {
  if (!details) return null;

  switch (stage) {
    case "planning":
      return details.plan ? (
        <Card title="📋 研究计划">
          <p className="text-secondary mb-sm">共 {details.plan.section_count} 个章节/要点</p>
          {details.plan.preview.map((line, i) => (
            <p key={i} style={{
              margin: "0.2rem 0", paddingLeft: "0.5rem",
              borderLeft: "2px solid var(--color-primary)",
              fontSize: "var(--font-size-sm)",
            }}>
              {line}
            </p>
          ))}
        </Card>
      ) : <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>暂无计划数据</p>;

    case "retrieval":
      return (
        <>
          {details.search_queries && details.search_queries.length > 0 && (
            <Card title="🔍 搜索查询">
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {details.search_queries.map((q, i) => (
                  <span key={i} style={{
                    background: "var(--color-primary-light)", padding: "0.3rem 0.8rem",
                    borderRadius: "var(--radius-full)", fontSize: "var(--font-size-sm)",
                    color: "var(--color-primary-dark)",
                  }}>
                    {q}
                  </span>
                ))}
              </div>
            </Card>
          )}
          {details.papers && (
            <Card title={`📄 检索到的论文（共 ${details.papers.total} 篇）`}>
              <div style={{ maxHeight: 300, overflowY: "auto" }}>
                {details.papers.list.map((p, i) => (
                  <div key={i} style={{
                    padding: "0.5rem", marginBottom: "0.3rem",
                    background: "#fafafa", borderRadius: "var(--radius-md)",
                    border: "1px solid var(--color-border-light)",
                  }}>
                    <div style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}>{p.title}</div>
                    <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)", marginTop: "0.2rem" }}>
                      {p.authors} · {p.year} · 引用: {p.citations}
                    </div>
                  </div>
                ))}
                {details.papers.total > 10 && (
                  <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)", textAlign: "center" }}>
                    … 还有 {details.papers.total - 10} 篇
                  </p>
                )}
              </div>
            </Card>
          )}
          {!details.search_queries && !details.papers && (
            <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>暂无检索数据</p>
          )}
        </>
      );

    case "analysis":
      return details.analysis ? (
        <Card title="🔬 论文分析">
          <p style={{
            color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)",
            whiteSpace: "pre-wrap", margin: 0, lineHeight: 1.5,
          }}>
            {details.analysis.preview}
          </p>
        </Card>
      ) : <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>暂无分析数据</p>;

    case "writing":
      return details.sections && details.sections.length > 0 ? (
        <Card title="📑 论文结构">
          {details.sections.map((s, i) => (
            <div key={i} style={{
              padding: "0.3rem 0", paddingLeft: s.level === 0 ? "0" : "1.5rem",
              fontWeight: s.level === 0 ? 600 : 400, fontSize: "var(--font-size-sm)",
            }}>
              {s.level === 0 ? "▸ " : "  ◦ "}{s.title}
            </div>
          ))}
        </Card>
      ) : <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>暂无章节数据</p>;

    case "validation":
      return details.validation && Object.keys(details.validation).length > 0 ? (
        <Card title="✅ 质量验证">
          {Object.entries(details.validation).map(([name, v]) => (
            <div key={name} style={{
              display: "flex", alignItems: "center", gap: "0.5rem",
              padding: "0.3rem 0", borderBottom: "1px solid var(--color-border-light)",
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: v.passed ? "var(--color-success)" : "var(--color-danger)",
                display: "inline-block", flexShrink: 0,
              }} />
              <span style={{ fontWeight: 500, minWidth: 140, fontSize: "var(--font-size-sm)" }}>{name}</span>
              <span style={{
                fontSize: "var(--font-size-xs)", padding: "0.1rem 0.4rem",
                borderRadius: "var(--radius-full)",
                background: v.passed ? "var(--color-success-light)" : "var(--color-danger-light)",
                color: v.passed ? "var(--color-success-dark)" : "var(--color-danger-dark)",
              }}>
                {v.passed ? "通过" : "需改进"}
              </span>
              {v.message && (
                <span className="text-secondary" style={{ fontSize: "var(--font-size-xs)", marginLeft: "0.3rem" }}>
                  — {v.message}
                </span>
              )}
            </div>
          ))}
        </Card>
      ) : <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>暂无验证数据</p>;

    case "format_repair":
      return <p className="text-disabled" style={{ fontSize: "var(--font-size-sm)" }}>格式修复已完成</p>;

    default:
      return null;
  }
}
```

- [ ] **Step 4: Add the pulse keyframe animation**

Add a `<style>` tag or inline keyframes. Since the existing codebase uses inline styles, add a `<style>` element:

```typescript
// Add at the bottom of StageTimeline.tsx, before exports
const pulseKeyframes = `
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(var(--color-primary-rgb, 59, 130, 246), 0.4); }
  70% { box-shadow: 0 0 0 8px rgba(var(--color-primary-rgb, 59, 130, 246), 0); }
  100% { box-shadow: 0 0 0 0 rgba(var(--color-primary-rgb, 59, 130, 246), 0); }
}
`;

// In the component, inject the keyframes once
if (typeof document !== "undefined" && !document.getElementById("stage-timeline-keyframes")) {
  const style = document.createElement("style");
  style.id = "stage-timeline-keyframes";
  style.textContent = pulseKeyframes;
  document.head.appendChild(style);
}
```

- [ ] **Step 5: Verify the component compiles**

Run: `cd web && npx tsc --noEmit --pretty 2>&1 | head -50`
Expected: No TypeScript errors for `StageTimeline.tsx`

- [ ] **Step 6: Commit**

```bash
git add web/src/components/StageTimeline.tsx
git commit -m "feat: add StageTimeline component with per-stage artifact cards"
```

---

### Task 2: Integrate StageTimeline into AgentExecution page

**Files:**
- Modify: `web/src/pages/AgentExecution.tsx` (import StageTimeline, replace renderExecutionDetails, adjust layout)

**Interfaces:**
- Consumes: `StageTimeline` from `./components/StageTimeline`
- Produces: Updated AgentExecution page with timeline layout

- [ ] **Step 1: Add import and remove old renderExecutionDetails**

Replace the old `renderExecutionDetails` function reference. Add the import at the top:

```typescript
// Add import (line ~10, after useToast import)
import StageTimeline from "../components/StageTimeline";
```

Then remove the entire `renderExecutionDetails` function (lines 287-407 in the current file) and the `DetailCard` helper (lines 91-97).

- [ ] **Step 2: Update the two-column layout block**

Find the current two-column layout (lines ~590-594):
```tsx
{pipelineRunning ? (
  <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
    <div>{renderExecutionDetails()}</div>
    <div>{renderFeedbackPanel()}</div>
  </div>
) : (
  <div>
    {renderExecutionDetails()}
    {renderErrorPanel()}
    {pipelineFinished && progress?.status !== "ERROR" && (
      ...
    )}
  </div>
)}
```

Replace with:
```tsx
{pipelineRunning ? (
  <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem" }}>
    <div>
      <StageTimeline
        currentStage={currentStage}
        stageOrder={STAGE_ORDER}
        stageLabels={STAGE_LABELS}
        executionDetails={progress?.execution_details ?? null}
        currentMessage={progress?.current_message ?? ""}
        pipelineRunning={pipelineRunning}
      />
    </div>
    <div>{renderFeedbackPanel()}</div>
  </div>
) : (
  <div>
    <StageTimeline
      currentStage={currentStage}
      stageOrder={STAGE_ORDER}
      stageLabels={STAGE_LABELS}
      executionDetails={progress?.execution_details ?? null}
      currentMessage={progress?.current_message ?? ""}
      pipelineRunning={pipelineRunning}
    />
    {renderErrorPanel()}
    {pipelineFinished && progress?.status !== "ERROR" && (
      <div style={{
        background: "var(--color-success-light)", borderRadius: "var(--radius-lg)", padding: "1rem 1.5rem",
        borderLeft: "4px solid var(--color-success)",
      }}>
        <p style={{ margin: 0, color: "var(--color-success-dark)", fontWeight: 600 }}>
          ✓ Pipeline completed. {progress.has_warnings && "Completed with warnings."}
        </p>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 3: Verify the page compiles**

Run: `cd web && npx tsc --noEmit --pretty 2>&1 | head -50`
Expected: No TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/AgentExecution.tsx web/src/components/StageTimeline.tsx
git commit -m "feat: integrate StageTimeline into AgentExecution page"
```

---

### Task 3: Test the timeline rendering

**Files:**
- Create: `web/src/__tests__/StageTimeline.test.tsx`
- Modify: none

**Interfaces:**
- Tests: `StageTimeline` component with various combinations of execution details and stage statuses

- [ ] **Step 1: Write basic rendering tests**

```typescript
// web/src/__tests__/StageTimeline.test.tsx
import React from "react";
import { render, screen } from "@testing-library/react";
import StageTimeline from "../components/StageTimeline";

const STAGE_ORDER = ["starting", "planning", "retrieval", "analysis", "writing", "validation", "format_repair", "retrying", "complete", "error"];
const STAGE_LABELS: Record<string, string> = {
  starting: "Starting…",
  planning: "Planning Agent",
  retrieval: "Search Agent",
  analysis: "Analysis Agent",
  writing: "Writing Agent",
  validation: "Validation Agent",
  format_repair: "Format Repair",
  complete: "Complete",
  error: "Error",
};

describe("StageTimeline", () => {
  test("renders all non-terminal stages", () => {
    render(
      <StageTimeline
        currentStage="planning"
        stageOrder={STAGE_ORDER}
        stageLabels={STAGE_LABELS}
        executionDetails={null}
        currentMessage=""
        pipelineRunning={true}
      />
    );
    expect(screen.getByText("Planning Agent")).toBeInTheDocument();
    expect(screen.getByText("Search Agent")).toBeInTheDocument();
    expect(screen.getByText("Analysis Agent")).toBeInTheDocument();
    expect(screen.getByText("Writing Agent")).toBeInTheDocument();
    expect(screen.getByText("Validation Agent")).toBeInTheDocument();
    // "complete" and "error" should NOT be in the timeline
    expect(screen.queryByText("Complete")).not.toBeInTheDocument();
    expect(screen.queryByText("Error")).not.toBeInTheDocument();
  });

  test("shows planning artifact when planning stage is completed", () => {
    const details = {
      plan: {
        summary: "Research plan",
        preview: ["- Introduction", "- Background", "- Methods"],
        section_count: 6,
      },
    };
    render(
      <StageTimeline
        currentStage="retrieval"  // planning is in the past
        stageOrder={STAGE_ORDER}
        stageLabels={STAGE_LABELS}
        executionDetails={details}
        currentMessage=""
        pipelineRunning={true}
      />
    );
    expect(screen.getByText("📋 研究计划")).toBeInTheDocument();
    expect(screen.getByText(/6 个章节/)).toBeInTheDocument();
  });

  test("shows loading skeleton for active stage", () => {
    render(
      <StageTimeline
        currentStage="analysis"
        stageOrder={STAGE_ORDER}
        stageLabels={STAGE_LABELS}
        executionDetails={null}
        currentMessage="Analyzing papers…"
        pipelineRunning={true}
      />
    );
    // Active stage should show the current message
    expect(screen.getByText("Analyzing papers…")).toBeInTheDocument();
  });

  test("shows 'no data' for completed stage with missing artifact", () => {
    render(
      <StageTimeline
        currentStage="retrieval"
        stageOrder={STAGE_ORDER}
        stageLabels={STAGE_LABELS}
        executionDetails={{}}
        currentMessage=""
        pipelineRunning={true}
      />
    );
    expect(screen.getByText("暂无计划数据")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd web && npx jest --testPathPattern="StageTimeline" --no-coverage`
Expected: All 4 tests pass

- [ ] **Step 3: Commit**

```bash
git add web/src/__tests__/StageTimeline.test.tsx web/src/components/StageTimeline.tsx web/src/pages/AgentExecution.tsx
git commit -m "test: add StageTimeline rendering tests"
```

---

### Task 4: Manual verification and polish

**Files:**
- Verify: `web/src/pages/AgentExecution.tsx`
- Verify: `web/src/components/StageTimeline.tsx`

- [ ] **Step 1: Verify the full app builds without errors**

Run: `cd web && npx vite build 2>&1 | tail -20`
Expected: Build succeeds with no errors

- [ ] **Step 2: Visual review checklist**

Open the Execution page in the browser and verify:
- [ ] Loading state (no progress yet): shows nothing (unchanged)
- [ ] Running state, planning stage: plan card appears in timeline
- [ ] Running state, retrieval stage: plan card (completed) + search/papers cards (active skeleton)
- [ ] Running state, analysis stage: plan + retrieval cards completed, analysis card active
- [ ] Running state, writing stage: sections card appears
- [ ] Running state, validation stage: validation scores card appears
- [ ] Completed state: all stages show their artifacts, no loading skeletons
- [ ] Error state: completed stages still visible, error shown in error panel below
- [ ] Two-column layout: timeline on left, feedback panel on right
- [ ] Single-column layout: timeline fills width, no feedback panel

- [ ] **Step 3: Fix any visual issues found**

If visual issues are found during review, fix them directly in `StageTimeline.tsx`.

- [ ] **Step 4: Final commit with any fixes**

```bash
git add -A
git commit -m "fix: polish StageTimeline layout and edge cases"
```