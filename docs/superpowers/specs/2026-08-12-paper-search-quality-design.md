# Paper Search Quality Improvement Design

## Problem

The current paper search pipeline retrieves many peripheral papers (e.g., edge detection used as a tool in other domains) while missing seminal works and core methodology papers. Analysis of an edge detection survey run showed:

- 10/19 papers were "edge detection as a tool" in unrelated domains (hidden writing, cosmology, planetary science)
- 0 papers from standard benchmarks (BSDS500, NYUDv2, BIPED)
- 0 papers using modern methods (Transformer, self-supervised learning)
- Most papers were pre-2020 despite the LLM being told to focus on 2020-2026

## Root Causes

| Cause | Impact |
|-------|--------|
| Year range not passed to search APIs | Old papers dominate results |
| Simple keyword queries only | Misses surveys, method-specific, benchmark-specific angles |
| No citation count sorting at API level | Low-quality and high-quality papers mixed |
| No field-of-study filtering | Papers from unrelated domains (physics, cosmology) included |
| No two-phase survey→key-papers strategy | Never finds the seminal papers that surveys cite |
| No venue filtering | Workshop papers rank equally with top conferences |

## Changes

### Change 1: API-level filters (`agent/tools/retrieval.py`)

**Semantic Scholar:**
- Add `year={year_start}-{year_end}` parameter to search URL
- Add `fieldsOfStudy=Computer Science` parameter
- Use `sortBy=citationCount` (descending by citation count)

**arXiv:**
- Add `cat:cs.CV` (computer vision) category filter to search query
- Add `last_updated_date:[YYYYMMDD TO YYYYMMDD]` year range filter

Both changes require passing `year_start` and `year_end` from the HarnessConfig through to the tool execution calls.

### Change 2: Multi-strategy query generation (`agent/core/pipeline.py`)

Replace simple "generate 3 queries" with 4 complementary strategies:

| Strategy | Example Query | Purpose |
|----------|--------------|---------|
| 1. Survey/review | `"edge detection" survey deep learning` | Find comprehensive reviews |
| 2. Method + benchmark | `edge detection BSDS500 benchmark` | Find papers evaluated on standard benchmarks |
| 3. Specific technique | `edge detection transformer self-attention` | Find modern methods |
| 4. Direction-specific | `edge detection self-supervised learning` | Find specific sub-directions |

Each strategy generates 2-3 queries, for a total of 8-12 queries.

### Change 3: Two-phase retrieval (`agent/core/pipeline.py`)

New flow:
1. **Phase 1**: Search for survey/review papers using strategy 1
2. **Phase 1b**: Citation expand the top-3 survey papers to get their reference lists
3. **Phase 2**: Search using strategies 2-4 for method and benchmark-specific papers
4. **Merge** all results, dedup, and rank

This ensures seminal papers (cited by surveys) and recent method papers (from direct search) are both included.

### Change 4: Restructure retrieval pipeline flow (`agent/core/pipeline.py`)

Reorder `_retrieve_papers()`:

```
Old:  search → merge → sort → truncate
New:  search → merge → sort → citation-expand on top-10 → merge → re-sort → truncate
```

### Change 5: Pass year range to tool calls (`agent/core/pipeline.py`)

The `ArxivSearch` and `SemanticScholarSearch` tools need to receive `year_start` and `year_end` parameters so they can apply API-level filters. This requires passing the config values from the pipeline to the tool execution parameters.

## Files Changed

| File | Changes |
|------|---------|
| `agent/tools/retrieval.py` | Add year range, fieldsOfStudy, sortBy, arXiv cat filter |
| `agent/core/pipeline.py` | Multi-strategy queries, two-phase retrieval, restructured flow |
| `agent/tools/citation.py` | (New) Citation expander tool for survey reference expansion |