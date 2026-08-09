# Execution Page Progress Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic loading skeleton on the Execution page with rich, real-time progress messages and stage-specific quantitative metrics.

**Architecture:** Add `stage_messages` (typed log entries) and `stage_metrics` (structured counters) fields to the backend progress pipeline, propagate them through the Harness and WebSocket to the frontend, and render them in StageTimeline as a scrolling message list with per-stage metric cards.

**Tech Stack:** Python (PipelineOrchestrator, Harness), TypeScript/React (StageTimeline, AgentExecution)

## Global Constraints

- All `stage_messages` entries must have `type` in `{"info", "success", "warning", "error"}`
- `stage_metrics` keys must be optional (frontend uses `?.` access)
- Progress messages must be reset at the start of each pipeline run
- The progress callback must pass the last 20 messages (not the full list) to avoid bloating the WebSocket payload
- Frontend must auto-scroll the message list to the bottom on new messages
- No new backend dependencies

---

### Task 1: Add `stage_messages` and `stage_metrics` to PipelineOrchestrator

**Files:**
- Modify: `agent/core/pipeline.py:129-135` (init fields)
- Modify: `agent/core/pipeline.py:233-234` (reset in run_pipeline)
- Modify: `agent/core/pipeline.py:1104-1109` (update _progress)

**Interfaces:**
- Consumes: `PipelineOrchestrator` init, `run_pipeline()`, `_progress()` method
- Produces: `self.stage_messages: list[dict]`, `self.stage_metrics: dict`, `_emit_progress()` helper method

- [ ] **Step 1: Add fields to `__init__`**

After line 131 (`self.current_message: str = ""`), add:
```python
# Progress details (consumed by frontend for rich stage display)
self.stage_messages: list[dict] = []
self.stage_metrics: dict = {}
```

- [ ] **Step 2: Add `_emit_progress` helper method**

After `_build_citation_anchors()` (around line 635), add:
```python
def _emit_progress(self, msg_type: str, message: str, metrics: Optional[dict] = None) -> None:
    """Record a progress message and optionally update stage metrics.

    Args:
        msg_type: One of "info", "success", "warning", "error".
        message: Human-readable description of the current sub-step.
        metrics: Optional dict of quantitative indicators to merge into
            stage_metrics (e.g. {"papers_found": 5, "queries_completed": 2}).
    """
    entry = {
        "type": msg_type,
        "message": message,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    self.stage_messages.append(entry)
    if metrics:
        self.stage_metrics.update(metrics)
```

- [ ] **Step 3: Add reset in `run_pipeline()`**

After line 234 (`self.current_message = ""`), add:
```python
self.stage_messages.clear()
self.stage_metrics.clear()
```

- [ ] **Step 4: Update `_progress()` to include new fields**

Replace lines 1104-1109 with:
```python
def _progress(self, cb: Optional[ProgressCallback], stage: str, msg: str) -> None:
    """Dispatch progress callback if set."""
    self.current_stage = stage
    self.current_message = msg
    detail = self._build_task_info()
    # Include last 20 messages to keep WebSocket payload bounded
    detail["stage_messages"] = self.stage_messages[-20:]
    detail["stage_metrics"] = dict(self.stage_metrics)
    if cb:
        cb(stage, msg, detail)
```

- [ ] **Step 5: Reset in `cancel()` and `reset_error_state()`**

In `reset_error_state()` (line 151-155), add:
```python
self.stage_messages.clear()
self.stage_metrics.clear()
```

Also add the same reset to the error-handling path in `_pipeline()` if needed (the `_retry_on_error` method propagates exceptions, so `run_pipeline`'s except block will handle it — but verify that `self.current_stage = ""` and `self.current_message = ""` already reset in the except block).

- [ ] **Step 6: Commit**

```bash
git add agent/core/pipeline.py
git commit -m "feat(pipeline): add stage_messages and stage_metrics fields for progress tracking"
```

---

### Task 2: Add granular progress calls to `_generate_plan()`

**Files:**
- Modify: `agent/core/pipeline.py:374-400`

**Interfaces:**
- Consumes: `_emit_progress()` from Task 1
- Produces: Progress messages visible in frontend during planning stage

- [ ] **Step 1: Add progress call before LLM call**

After line 377 (`goal = ...`), before the guardrail check at line 396, add:
```python
self._emit_progress("info", "Generating research plan...")
```

- [ ] **Step 2: Add progress call after plan is generated**

After line 399 (`self._plan = resp.text`), before `return resp.text`, add:
```python
# Count sections for the metrics
section_count = sum(1 for l in resp.text.split("\n")
                    if l.strip().startswith(("\\section", "- **", "###")))
self._emit_progress(
    "success", f"Research plan generated with {section_count} sections",
    {"sections_count": section_count},
)
```

- [ ] **Step 3: Commit**

```bash
git add agent/core/pipeline.py
git commit -m "feat(pipeline): add granular progress messages to plan generation"
```

---

### Task 3: Add granular progress calls to `_retrieve_papers()`

**Files:**
- Modify: `agent/core/pipeline.py:402-540`

**Interfaces:**
- Consumes: `_emit_progress()` from Task 1
- Produces: Progress messages with queries, paper counts, PDF download/evidence extraction progress

- [ ] **Step 1: Emit message after generating queries**

After line 437 (`queries.append(...)`), add:
```python
self._emit_progress(
    "success", f"Generated {len(queries)} search queries",
    {"queries_total": len(queries), "queries_completed": 0},
)
```

- [ ] **Step 2: Wrap the search loop with progress messages**

Replace lines 439-458 with:
```python
# Search both sources
all_results = []
for i, q in enumerate(queries):
    self._emit_progress(
        "info",
        f"Searching arXiv with query {i+1}/{len(queries)}: \"{q[:60]}\"",
    )
    arxiv_tool = self.tools.get("arxiv_search")
    if arxiv_tool:
        arxiv_res = arxiv_tool.execute({
            "query": q, "max_results": self.config.max_papers,
        })
        if arxiv_res.success:
            papers_count = len(arxiv_res.data.get("papers", []))
            self._emit_progress(
                "success", f"arXiv: found {papers_count} papers",
            )
            all_results.append(arxiv_res.data)
        else:
            self._emit_progress("warning", f"arXiv search failed for query: {q[:60]}")

    self._emit_progress(
        "info",
        f"Searching Semantic Scholar with query {i+1}/{len(queries)}: \"{q[:60]}\"",
    )
    ss_tool = self.tools.get("semantic_scholar_search")
    if ss_tool:
        ss_res = ss_tool.execute({
            "query": q, "max_results": self.config.max_papers,
        })
        if ss_res.success:
            papers_count = len(ss_res.data.get("papers", []))
            self._emit_progress(
                "success", f"Semantic Scholar: found {papers_count} papers",
            )
            all_results.append(ss_res.data)
        else:
            self._emit_progress("warning", f"Semantic Scholar search failed for query: {q[:60]}")

    time.sleep(0.3)
```

- [ ] **Step 3: Emit merge and sort progress**

After line 462 (`papers = merged.data...`), add:
```python
self._emit_progress(
    "success", f"Merged and deduplicated: {len(papers)} unique papers",
    {"papers_found": len(papers)},
)
```

After line 469 (`papers = sorted_res...`), add:
```python
self._emit_progress("success", f"Sorted {len(papers)} papers by citation count")
```

- [ ] **Step 4: Add progress around PDF download and evidence extraction**

Replace lines 488-532 with:
```python
import os
os.makedirs("output/pdfs", exist_ok=True)

papers_with_arxiv = [p for p in self._papers if p.get("arxiv_id")]
total_pdfs = len(papers_with_arxiv)
self._emit_progress(
    "info", f"Downloading and parsing PDFs ({total_pdfs} papers with arXiv IDs)...",
)

for idx, paper in enumerate(papers_with_arxiv, 1):
    arxiv_id = paper.get("arxiv_id", "")
    paper_id = paper.get("paper_id", arxiv_id)
    if not arxiv_id:
        continue

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    save_path = f"output/pdfs/{arxiv_id}.pdf"

    self._emit_progress(
        "info",
        f"Downloading PDF ({idx}/{total_pdfs}): {arxiv_id}",
        {"papers_downloaded": idx - 1, "papers_total": total_pdfs},
    )

    try:
        # Download PDF
        pdf_tool = self.tools.get("pdf_download")
        if pdf_tool:
            dl_res = pdf_tool.execute({"url": pdf_url, "save_path": save_path})
            if not dl_res.success:
                self._emit_progress(
                    "warning",
                    f"PDF download failed for {arxiv_id}: {dl_res.error}",
                )
                self._evidence_unavailable.add(paper_id)
                continue
        else:
            continue

        # Parse into chunks
        chunks = self._pdf_parser.parse(paper_id, save_path)
        if not chunks:
            self._emit_progress("warning", f"PDF parsing returned no chunks for {arxiv_id}")
            self._evidence_unavailable.add(paper_id)
            continue

        self._pdf_chunks[paper_id] = chunks

        # Extract evidence references
        refs = self._evidence_extractor.extract(chunks)
        if refs:
            self._evidence_refs.extend(refs)
            self._emit_progress(
                "success", f"Evidence: {len(refs)} refs extracted from {arxiv_id}",
            )
        else:
            self._emit_progress("info", f"Evidence: no refs extracted from {arxiv_id}")

    except Exception as e:
        self._emit_progress("warning", f"Evidence extraction failed for {arxiv_id}: {e}")
        self._evidence_unavailable.add(paper_id)

# Update metrics with final PDF count
self._emit_progress(
    "info",
    f"Evidence: {len(self._pdf_chunks)} papers with evidence, "
    f"{len(self._evidence_unavailable)} unavailable, "
    f"{len(self._evidence_refs)} total refs",
    {"papers_downloaded": len(self._pdf_chunks)},
)
```

- [ ] **Step 5: Commit**

```bash
git add agent/core/pipeline.py
git commit -m "feat(pipeline): add granular progress messages to paper retrieval and PDF extraction"
```

---

### Task 4: Add granular progress calls to `_analyze_papers()`

**Files:**
- Modify: `agent/core/pipeline.py:542-610`

**Interfaces:**
- Consumes: `_emit_progress()`
- Produces: Progress messages for LLM analysis, claims extraction, verification, benchmarks

- [ ] **Step 1: Add LLM analysis progress**

In the `if not papers:` branch (line 547), before the LLM call (line 563), add:
```python
self._emit_progress("info", "No papers retrieved — generating analysis from topic knowledge...")
```

In the `else:` branch (line 573), before line 596, add:
```python
self._emit_progress(
    "info", f"Analyzing {len(papers)} papers via LLM...",
    {"papers_analyzed": 0, "total_papers": len(papers)},
)
```

After the LLM call (line 602 `resp = self._safe_llm_call(...)`), add:
```python
self._emit_progress(
    "success", "Paper analysis completed",
    {"papers_analyzed": len(papers) if papers else 0, "total_papers": len(papers) if papers else 0},
)
```

- [ ] **Step 2: Add claims extraction progress**

In `_analyze_papers()`, after line 605 `self._extract_and_verify_claims(papers)`, add:
```python
# Note: _extract_and_verify_claims already logs internally;
# we add a progress message here for the frontend
verified_count = self._evidence_store.verified_count()
if verified_count > 0:
    self._emit_progress(
        "success", f"{verified_count} claims verified",
        {"claims_verified": verified_count},
    )
```

- [ ] **Step 3: Add progress inside `_extract_and_verify_claims()`**

In `_extract_and_verify_claims()` (line 834), before the `try` block, add:
```python
self._emit_progress("info", "Extracting claims from analysis...")
```

Inside the `try` block, after `claims = self._claim_extractor.extract(...)` (line 841), add:
```python
if claims:
    self._emit_progress("success", f"Extracted {len(claims)} claims", {"claims_extracted": len(claims)})
```

- [ ] **Step 4: Add benchmark and knowledge extraction progress**

In `_extract_benchmarks_and_knowledge()` (line 637), before the `try` block, add:
```python
self._emit_progress("info", "Extracting benchmark data and paper knowledge...")
```

Inside the `if self._evidence_refs:` block, after benchmark extraction (line 648), add:
```python
if benchmark_records:
    self._emit_progress("success", f"{len(benchmark_records)} benchmark records extracted", {"benchmark_records": len(benchmark_records)})
```

After knowledge extraction (line 658), add:
```python
if knowledge_list:
    self._emit_progress("success", f"Knowledge extracted for {len(knowledge_list)} papers")
```

- [ ] **Step 5: Add citation anchor progress**

In `_build_citation_anchors()` (line 612), before the `try` block, add:
```python
self._emit_progress("info", "Building citation anchors...")
```

After the anchor build (line 627), add:
```python
if verified:
    self._emit_progress("success", f"{self._citation_anchor_store.anchor_count()} citation anchors built")
```

- [ ] **Step 6: Commit**

```bash
git add agent/core/pipeline.py
git commit -m "feat(pipeline): add granular progress messages to paper analysis"
```

---

### Task 5: Add granular progress calls to `_write_survey()`, `_format_repair()`, and `_run_validators()`

**Files:**
- Modify: `agent/core/pipeline.py:666-779`, `1040-1055`, `878-900`

**Interfaces:**
- Consumes: `_emit_progress()`
- Produces: Progress messages for writing, format repair, validation

- [ ] **Step 1: Add writing progress messages**

In `_write_survey()` (line 666), after building `ref_text` (line 681), add:
```python
self._emit_progress(
    "success", f"Built reference list ({len(self._papers)} papers)",
)
```

After line 754 (`evidence_context = ...`), add:
```python
self._emit_progress("info", "Retrieving evidence context for factual grounding...")
```

After line 757 (`citation_context = ...`), add:
```python
self._emit_progress("info", "Retrieving citation anchor context...")
```

Before the LLM call at line 773, add:
```python
self._emit_progress(
    "info",
    f"Writing survey draft (round {round_num + 1}/{self.config.max_retries + 1})...",
    {"round": round_num + 1, "total_rounds": self.config.max_retries + 1},
)
```

After line 774 (`self._draft_sections = ...`), add:
```python
word_count = len(resp.text.split())
self._emit_progress(
    "success",
    f"Draft written ({word_count} words, {len(self._draft_sections)} sections)",
    {"sections_count": len(self._draft_sections), "word_count": word_count},
)
```

After `_post_process()` (line 777), add:
```python
self._emit_progress("info", "Injecting citations and generating benchmark tables...")
```

- [ ] **Step 2: Add post-processing progress inside `_post_process()`**

At line 815, after the docstring, add:
```python
self._emit_progress("info", "Post-processing: injecting citations...")
```

Before line 829 (`if self._benchmark_store:`), add:
```python
self._emit_progress("info", "Post-processing: generating benchmark tables...")
```

- [ ] **Step 3: Add format repair progress**

In `_format_repair()` (line 1040), before `repair_log = ...`, add:
```python
self._emit_progress("info", "Running CVPR format repair...")
```

After line 1047 (after `repair_log.change_count`), add:
```python
if repair_log.has_changes:
    self._emit_progress(
        "success",
        f"Format repair: {repair_log.change_count} issue(s) fixed",
        {"changes_count": repair_log.change_count},
    )
else:
    self._emit_progress("success", "Format repair: no changes needed")
```

- [ ] **Step 4: Add per-validator progress messages**

In `_run_validators()` (line 878), before the results loop, add:
```python
validator_names = [v.__class__.__name__ for v in self._validators]
```

Replace lines 891-899 with:
```python
results = []
for v in self._validators:
    vname = v.__class__.__name__
    self._emit_progress("info", f"Running validator: {vname}...")
    try:
        result = v.validate(context)
        results.append(result)
        if result.passed:
            self._emit_progress(
                "success", f"{vname}: passed (score {result.score:.2f})",
            )
        else:
            self._emit_progress(
                "warning", f"{vname}: needs improvement (score {result.score:.2f})",
            )
    except Exception as e:
        self._emit_progress("error", f"{vname}: failed with error: {e}")
        # Create a failure result so aggregator can handle it
        from agent.feedback.base import ValidationResult
        results.append(ValidationResult(
            validator_name=vname,
            score=0.0, passed=False,
            repair_instructions=f"Validator crashed: {e}",
        ))

# Update validation scores
self._validation_scores = {
    r.validator_name: {
        "score": r.score,
        "passed": r.passed,
        "message": (r.repair_instructions or "")[:200],
    }
    for r in results
}
```

After the results loop, after `report = self._aggregate_results(results)` (line 326 in the calling code), add progress emission there instead (in `_pipeline()`):
```python
validators_passed = sum(1 for r in results if r.passed)
self._emit_progress(
    "info",
    f"Validation: {validators_passed}/{len(results)} passed, "
    f"overall score {report['overall_score']:.2f}",
    {
        "validators_passed": validators_passed,
        "validators_total": len(results),
        "overall_score": report["overall_score"],
    },
)
```

- [ ] **Step 5: Commit**

```bash
git add agent/core/pipeline.py
git commit -m "feat(pipeline): add granular progress messages to writing, format repair, and validation"
```

---

### Task 6: Propagate `stage_messages` and `stage_metrics` through Harness to API

**Files:**
- Modify: `agent/core/harness.py:278-348` (get_task_info)
- Modify: `agent/core/harness.py:597-609` (_sync_orchestrator_state)

**Interfaces:**
- Consumes: `self._orchestrator.stage_messages`, `self._orchestrator.stage_metrics`
- Produces: `stage_messages` and `stage_metrics` fields in API responses

- [ ] **Step 1: Add `stage_messages` and `stage_metrics` to `get_task_info()`**

In the `if not self.task:` block (line 319-329), add after `execution_details`:
```python
"stage_messages": self._orchestrator.stage_messages[-20:],
"stage_metrics": self._orchestrator.stage_metrics,
```

In the main return dict (line 330-348), add after `execution_details`:
```python
"stage_messages": self._orchestrator.stage_messages[-20:],
"stage_metrics": self._orchestrator.stage_metrics,
```

- [ ] **Step 2: Commit**

```bash
git add agent/core/harness.py
git commit -m "feat(harness): propagate stage_messages and stage_metrics to API responses"
```

---

### Task 7: Update `AgentExecution.tsx` to pass new props

**Files:**
- Modify: `web/src/pages/AgentExecution.tsx:44-61` (ProgressInfo interface)
- Modify: `web/src/pages/AgentExecution.tsx:511-518` (StageTimeline props)

**Interfaces:**
- Consumes: `StageMessage`, `StageMetrics` types from backend
- Produces: `stageMessages` and `stageMetrics` props passed to `StageTimeline`

- [ ] **Step 1: Add `StageMessage` and `StageMetrics` interfaces**

After the existing `ExecutionDetails` interface (line 42), add:
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

- [ ] **Step 2: Add `stage_messages` and `stage_metrics` to `ProgressInfo`**

In the `ProgressInfo` interface (line 44-61), add after `execution_details`:
```typescript
stage_messages: StageMessage[];
stage_metrics: StageMetrics;
```

- [ ] **Step 3: Pass new props to `StageTimeline`**

In the two `<StageTimeline>` usage blocks (lines 511-518 and 524-531), add after `pipelineRunning`:
```tsx
stageMessages={progress?.stage_messages ?? []}
stageMetrics={progress?.stage_metrics ?? {}}
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/AgentExecution.tsx
git commit -m "feat(web): pass stage_messages and stage_metrics to StageTimeline"
```

---

### Task 8: Update `StageTimeline.tsx` to render rich progress

**Files:**
- Modify: `web/src/components/StageTimeline.tsx:126-133` (StageTimelineProps)
- Modify: `web/src/components/StageTimeline.tsx:430-438` (StageEntryProps)
- Modify: `web/src/components/StageTimeline.tsx:548-578` (replace LoadingSkeleton)
- Modify: `web/src/components/StageTimeline.tsx` (add new rendering components)

**Interfaces:**
- Consumes: `StageMessage[]`, `StageMetrics` from props
- Produces: Rich progress UI with message list and metric cards

- [ ] **Step 1: Add StageMessage and StageMetrics imports**

Near the top of the file, after the existing imports, add:
```typescript
export interface StageMessage {
  type: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string;
}

export interface StageMetrics {
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

- [ ] **Step 2: Update `StageTimelineProps`**

Add two new props:
```typescript
stageMessages: StageMessage[];
stageMetrics: StageMetrics;
```

- [ ] **Step 3: Update `StageEntryProps`**

Add the same two props to `StageEntryProps`.

- [ ] **Step 4: Create `StageProgressView` component**

Before the `StageEntry` component, add:
```typescript
const MESSAGE_ICONS: Record<string, string> = {
  info: "⏳",
  success: "✅",
  warning: "⚠️",
  error: "❌",
};

const MESSAGE_COLORS: Record<string, string> = {
  info: "var(--color-primary)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  error: "var(--color-danger)",
};

function StageProgressView({
  stage,
  messages,
  metrics,
  currentMessage,
}: {
  stage: string;
  messages: StageMessage[];
  metrics: StageMetrics;
  currentMessage: string;
}) {
  // Auto-scroll to bottom
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div>
      {/* Metrics card */}
      {renderStageMetrics(stage, metrics)}

      {/* Message list */}
      <div
        ref={listRef}
        style={{
          maxHeight: "240px",
          overflowY: "auto",
          background: "var(--color-bg-card)",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-border-light)",
          padding: "0.5rem",
        }}
      >
        {messages.length === 0 && currentMessage && (
          <div
            style={{
              padding: "0.4rem 0.6rem",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-secondary)",
              fontStyle: "italic",
            }}
          >
            {currentMessage}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className="stage-message"
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "0.4rem",
              padding: "0.25rem 0.4rem",
              fontSize: "var(--font-size-xs)",
              color: "var(--color-text-secondary)",
              borderBottom: i < messages.length - 1
                ? "1px solid var(--color-border-light)"
                : "none",
            }}
          >
            <span style={{ flexShrink: 0, fontSize: "0.85rem" }}>
              {MESSAGE_ICONS[m.type] || "•"}
            </span>
            <span style={{ color: MESSAGE_COLORS[m.type] || "inherit" }}>
              {m.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `renderStageMetrics` function**

Before `StageProgressView`, add:
```typescript
function renderStageMetrics(stage: string, metrics: StageMetrics): React.ReactNode {
  if (!metrics || Object.keys(metrics).length === 0) return null;

  switch (stage) {
    case "retrieval": {
      const { papers_downloaded, papers_total, papers_found } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {papers_found != null && (
            <MetricBadge label="Papers found" value={String(papers_found)} color="blue" />
          )}
          {papers_downloaded != null && papers_total != null && papers_total > 0 && (
            <MetricProgress
              label="PDFs downloaded"
              current={papers_downloaded}
              total={papers_total}
            />
          )}
        </div>
      );
    }
    case "analysis": {
      const { papers_analyzed, total_papers, claims_extracted, claims_verified } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {papers_analyzed != null && total_papers != null && total_papers > 0 && (
            <MetricProgress label="Papers analyzed" current={papers_analyzed} total={total_papers} />
          )}
          {claims_extracted != null && <MetricBadge label="Claims" value={String(claims_extracted)} color="blue" />}
          {claims_verified != null && <MetricBadge label="Verified" value={String(claims_verified)} color="green" />}
        </div>
      );
    }
    case "writing": {
      const { round, total_rounds, word_count } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {round != null && total_rounds != null && total_rounds > 0 && (
            <MetricProgress label="Writing round" current={round} total={total_rounds} />
          )}
          {word_count != null && <MetricBadge label="Words" value={String(word_count)} color="blue" />}
        </div>
      );
    }
    case "validation": {
      const { validators_passed, validators_total, overall_score } = metrics;
      return (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          {validators_passed != null && validators_total != null && validators_total > 0 && (
            <MetricProgress label="Validators passed" current={validators_passed} total={validators_total} />
          )}
          {overall_score != null && (
            <MetricBadge
              label="Score"
              value={`${(overall_score * 100).toFixed(0)}%`}
              color={overall_score >= 0.7 ? "green" : "orange"}
            />
          )}
        </div>
      );
    }
    case "planning": {
      const { sections_count } = metrics;
      return sections_count != null ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <MetricBadge label="Sections" value={String(sections_count)} color="blue" />
        </div>
      ) : null;
    }
    case "format_repair": {
      const { changes_count } = metrics;
      return changes_count != null ? (
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <MetricBadge
            label="Fixes applied"
            value={String(changes_count)}
            color={changes_count > 0 ? "orange" : "green"}
          />
        </div>
      ) : null;
    }
    default:
      return null;
  }
}

interface MetricBadgeProps {
  label: string;
  value: string;
  color: "blue" | "green" | "orange" | "red";
}

function MetricBadge({ label, value, color }: MetricBadgeProps) {
  const colorMap: Record<string, { bg: string; text: string }> = {
    blue: { bg: "var(--color-primary-light)", text: "var(--color-primary-dark)" },
    green: { bg: "var(--color-success-light)", text: "var(--color-success-dark)" },
    orange: { bg: "var(--color-warning-light)", text: "var(--color-warning-dark)" },
    red: { bg: "var(--color-danger-light)", text: "var(--color-danger-dark)" },
  };
  const c = colorMap[color] || colorMap.blue;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.3rem",
        background: c.bg,
        color: c.text,
        padding: "0.2rem 0.6rem",
        borderRadius: "var(--radius-full)",
        fontSize: "var(--font-size-xs)",
        fontWeight: 500,
      }}
    >
      <strong>{value}</strong>
      <span style={{ opacity: 0.8 }}>{label}</span>
    </span>
  );
}

function MetricProgress({
  label,
  current,
  total,
}: {
  label: string;
  current: number;
  total: number;
}) {
  const pct = Math.min(100, Math.round((current / total) * 100));
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        background: "var(--color-primary-light)",
        padding: "0.2rem 0.6rem",
        borderRadius: "var(--radius-full)",
        fontSize: "var(--font-size-xs)",
      }}
    >
      <span style={{ color: "var(--color-primary-dark)", fontWeight: 500, whiteSpace: "nowrap" }}>
        {label}: {current}/{total}
      </span>
      <div
        style={{
          width: 60,
          height: 6,
          background: "var(--color-border-light)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "var(--color-primary)",
            borderRadius: 3,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Replace LoadingSkeleton in StageEntry**

In `StageEntry`, find the block at lines 551-578 where `status === "active" && pipelineRunning` is handled. Replace the entire content block (the `LoadingSkeleton` + message) with:

```tsx
{status === "active" && pipelineRunning && (
  stageHasData(stage, executionDetails) ? (
    <StageArtifact stage={stage} details={executionDetails} />
  ) : (
    <StageProgressView
      stage={stage}
      messages={stageMessages || []}
      metrics={stageMetrics || {}}
      currentMessage={currentMessage}
    />
  )
)}
```

- [ ] **Step 7: Add CSS animation keyframes**

Add to the `PULSE_KEYFRAMES` style block (around line 590-596):
```css
.stage-message {
  animation: message-fade-in 0.3s ease-out;
}

@keyframes message-fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 8: Pass new props through StageEntry**

In `StageTimeline`'s render loop (around line 628-643), pass the new props to `StageEntry`:
```tsx
<StageEntry
  key={stage}
  stage={stage}
  label={label}
  status={status}
  isLast={index === displayStages.length - 1}
  executionDetails={executionDetails}
  currentMessage={currentMessage}
  pipelineRunning={pipelineRunning}
  stageMessages={stageMessages}
  stageMetrics={stageMetrics}
/>
```

- [ ] **Step 9: Commit**

```bash
git add web/src/components/StageTimeline.tsx
git commit -m "feat(web): replace LoadingSkeleton with rich progress messages and metrics"
```

---

### Task 9: Add `import { useEffect, useRef }` if missing in StageTimeline.tsx

**Files:**
- Modify: `web/src/components/StageTimeline.tsx`

**Details:** The `StageProgressView` component uses `useEffect` and `useRef` for auto-scroll. Verify these are already imported at the top of the file. If not, add them.

- [ ] **Step 1: Check imports**

The file currently imports React but not hooks. Add at the top:
```typescript
import React, { useEffect, useRef } from "react";
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/StageTimeline.tsx
git commit -m "fix: add missing React hooks imports to StageTimeline"
```

---

### Task 10: Self-Review and Verification

**Files:**
- All modified files

- [ ] **Step 1: Verify spec coverage**

Check that every requirement from the spec has a corresponding task:
- stage_messages as typed list → Task 1, 2, 3, 4, 5
- stage_metrics dict → Task 1, 2, 3, 4, 5
- Harness propagation → Task 6
- Frontend props → Task 7
- Rich progress rendering → Task 8
- Reset on pipeline start → Task 1, Step 3

- [ ] **Step 2: Verify no type inconsistencies**

Check that `StageMessage` and `StageMetrics` types match between `AgentExecution.tsx` (Task 7) and `StageTimeline.tsx` (Task 8). They are identical — no mismatch.

- [ ] **Step 3: Build check**

Run the frontend build to verify TypeScript compilation:
```bash
cd web && npx tsc --noEmit
```

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "fix: resolve type errors and finalize progress enhancement"
```