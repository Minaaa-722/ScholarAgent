# ScholarAgent Gap Analysis & Refactoring Design

> **Date**: 2026-07-27
> **Context**: Post-first-implementation review of ScholarAgent against SPEC.md requirements
> **Focus Areas**: Agent Execution UX, Knowledge Explorer, Frontend Product Design, Survey Generation Quality

---

## 1. Problem Statement

The first implementation of ScholarAgent delivered a working end-to-end pipeline, but a systematic review against SPEC.md reveals significant gaps across all four focus areas. The most critical issues are:

- **Disconnected subsystems**: Guardrails, memory, and tool registry exist as code but are never invoked by the harness
- **Incomplete user stories**: Knowledge Explorer (US-6) is a log viewer, not a paper explorer; Final Review (US-4) lacks quality scores; no memory management page (US-5)
- **Shallow validators**: All 5 feedback validators are regex-based with no semantic understanding
- **No design system**: Inline styles throughout, inconsistent UX

---

## 2. Gap Analysis

### 2.1 Agent Execution UX (US-2, US-3)

**Implemented**: Stage chain visualization, current message banner, feedback panel (3 categories), error panel with restart, execution details cards

**Missing**:
- Interrupt/resume buttons (API endpoints exist, no UI controls)
- Stop/cancel button for running pipeline
- Section-level detail drill-down (sections shown as flat list)
- WebSocket exponential backoff reconnection
- Feedback panel visibility gating (shown even when pipeline is idle)

### 2.2 Knowledge Explorer (US-6)

**Implemented**: Execution log viewer (color-coded stages, click-to-expand JSON), paper preview (first 2000 chars)

**Missing**:
- Paper relationship graph (D3.js/vis.js force-directed graph)
- Sortable paper list table (title, year, citations, source columns)
- Citation network visualization
- Paper metadata display (structured, not raw output)
- Search/filter bar

### 2.3 Frontend Product Design (US-4, US-5, US-7)

**Implemented**: 5-page routing, sidebar navigation, Dashboard with current task, Research Creation form, Final Review with .tex download

**Missing**:
- Quality score summary on Final Review (validation scores only in AgentExecution)
- BibTeX export button
- Quality report with per-check pass/warning/fail
- Memory management page for user preferences
- Preference auto-loading on ResearchCreation
- Credential management UI (SPEC §7.1)
- Design system (Open Design per SPEC §8)
- Loading skeletons, error boundaries, toast notifications
- Responsive design
- Form validation

### 2.4 Survey Generation Quality (SPEC §9.3)

**Implemented**: 5 validators, feedback aggregator, repair generator, multi-round iteration (max 3), LaTeX format repair

**Missing/Wired incorrectly**:
- Guardrails not wired into harness (5 classes exist, never called)
- Memory not wired into harness (SessionMemory and PersistentMemory exist, unused)
- ToolRegistry not used (harness directly instantiates tools)
- Validators are shallow (all regex-based)
- HallucinationDetector only checks for `[citation-needed]` markers
- CoherenceChecker only counts transition words
- RepairGenerator outputs instructions but doesn't auto-fix
- PDF download/parse are stubs
- Google Scholar not implemented
- WebSearch/ShellExec are stubs

### 2.5 Cross-Cutting Issues

- Harness class is 993 lines — violates SRP
- No frontend tests
- No CI workflow
- No coverage reporting

---

## 3. Refactoring Plan

### Phase 1: Tighten the Harness (High Priority)

**Goal**: Wire up the existing but disconnected subsystems (guardrails, memory) and break down the monolithic Harness class.

1. Extract PipelineOrchestrator from Harness
2. Wire guardrails into PipelineOrchestrator via GuardrailManager
3. Wire memory into Harness (auto-load preferences, persist session data)
4. Add human feedback resume mechanism

**Files**: `agent/core/harness.py`, `agent/core/pipeline.py` (new), `agent/guardrails/manager.py` (new), `agent/memory/integration.py` (new)

### Phase 2: Knowledge Explorer (High Priority)

**Goal**: Transform the log viewer into a real paper explorer with graph visualization.

1. Add paper metadata API endpoints (`GET /api/survey/papers`, `GET /api/survey/papers/graph`)
2. Build sortable paper list table
3. Build D3.js citation graph visualization
4. Add paper detail panel

**Files**: `api/routes/survey.py`, `web/src/pages/KnowledgeExplorer.tsx`, `web/src/components/PaperGraph.tsx`, `web/src/components/PaperTable.tsx`

### Phase 3: Frontend Product Design (Medium Priority)

**Goal**: Elevate all 5 pages to production quality with a consistent design system.

1. Add design system (CSS modules, color palette, typography, reusable components)
2. Enhance Dashboard (task history, onboarding, empty states)
3. Enhance ResearchCreation (preference auto-loading, year range, validation)
4. Enhance AgentExecution (interrupt/resume buttons, cancel, WebSocket backoff)
5. Enhance FinalReview (quality scores, BibTeX export, section review)
6. Add Memory Management page
7. Add Credential Management UI

**Files**: All 5 pages, `web/src/components/*`, `web/src/pages/MemoryManager.tsx`, `web/src/pages/Credentials.tsx`

### Phase 4: Survey Generation Quality (Medium Priority)

**Goal**: Deepen validators, implement guardrail enforcement, add synthetic quality evaluation.

1. Deepen all 5 validators with semantic checks
2. Implement repair auto-execution
3. Implement stub tools (PDF download/parse, WebSearch, ShellExec)

**Files**: `agent/feedback/*.py`, `agent/tools/processing.py`, `agent/tools/auxiliary.py`, `agent/feedback/auto_repair.py` (new)

### Phase 5: Architecture & Testing (Low Priority)

**Goal**: Close test gaps, add CI, make architecture maintainable.

1. Integration tests for guardrails, memory, feedback
2. Frontend tests (React Testing Library)
3. Coverage reporting (pytest-cov)
4. GitHub Actions CI

**Files**: `tests/*.py`, `web/src/**/*.test.tsx`, `.github/workflows/`, `pyproject.toml`

---

## 4. Dependencies

```
P1: Tighten the Harness ───┬─── P2: Knowledge Explorer (needs paper API)
                           └─── P4: Survey Quality (needs guardrail wiring)
P3: Frontend Design ─── (independent)
P5: Testing ─── (after P1-P4)
```

---

## 5. Phase Selection for First Sprint

**Recommended: Phase 3 — Frontend Product Design**

Rationale:
- Independent of all other phases (no blockers)
- Highest user-visible impact
- Design system work benefits all subsequent phases
- Lower risk than refactoring the harness core
- Quick wins: interrupt/resume buttons, design system, quality scores