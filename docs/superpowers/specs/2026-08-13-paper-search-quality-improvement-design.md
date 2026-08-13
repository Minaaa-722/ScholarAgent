# Paper Search Quality Improvement Design

> **For agentic workers:** This spec addresses two core defects in the unified paper retrieval pipeline: (1) excessive downstream application papers and insufficient core method innovation papers, and (2) citation-count-dominated ranking that suppresses 2025–2026 frontier papers. All changes are backward-compatible with the existing B-scheme architecture, Paper model, and pipeline.

**Goal:** Improve paper retrieval quality for survey generation by shifting from citation-heavy, application-oriented results toward methodologically diverse, temporally balanced paper sets.

**Architecture:** Additive changes across 6 modules — prompts, config, models, retrieval, relevance, processing — with one new pipeline orchestration step for year-stratified sampling. No existing interface is removed; only extended.

**Tech Stack:** Python 3.13+, dataclasses, arXiv API, Semantic Scholar API, LLM (MockLLM for testing)

**Spec:** `docs/superpowers/specs/2026-08-13-paper-search-unified-model-design.md` (parent spec — this extends it)

---

## 1. Methodology Query Generation

### Problem
The current `SEARCH_QUERY_PROMPT` generates only "full name -> abbreviation" pairs. These queries all target the same dimensions — concrete model names — and systematically miss broader methodological innovation categories (e.g., "attention mechanism design", "position encoding variants", "normalization techniques").

### Solution
Add a second prompt `METHODOLOGY_QUERY_PROMPT` that generates 5 queries focused on core methodological innovation categories. The LLM is instructed to avoid application-specific terms and instead generate method-family-level queries.

### New Prompt

```python
METHODOLOGY_QUERY_PROMPT = """\
You are a research methodology search query generator for academic paper retrieval.

TASK: Generate exactly 5 search queries to find **core methodological innovation papers**
for a survey on "{topic}".

CRITICAL RULES:
- Each query MUST target a **method category / design space / technique family**
  — NOT a specific model name, NOT a downstream application
- AVOID: "for X", "in X", "using X for Y", "X-based", "application of X to Y"
- PREFER: general mechanism categories like "X variants", "X design space",
  "X mechanism", "efficient X", "X architecture design", "X formulation"
- Output BOTH a broad method category AND a focused variant on each line,
  separated by " -> "
  Example: "attention mechanism design -> attention mechanism"
  → This will be expanded into two separate queries
- NO generic words: deep learning, survey, review, advances, recent, trends
- NO conversational text, NO numbering, NO explanation, NO markdown
- Be specific about the methodology dimension

OUTPUT FORMAT (exactly one pair per line):
method category -> focused variant
method category -> focused variant
...

Example for topic="Efficient Transformer":
attention mechanism optimization -> attention optimization
position encoding design -> position encoding
model compression technique -> model compression
architectural search space -> neural architecture search
training efficiency method -> training efficiency
"""
```

### Pipeline Integration

In `_generate_search_queries`:
1. Call Phase A with `SEARCH_QUERY_PROMPT` → 5 name-based queries
2. Call Phase B with `METHODOLOGY_QUERY_PROMPT` → 5 methodology queries
3. Concatenate and return both sets (10 raw lines)

`_expand_and_dedup_queries` already handles the "->" split and dedup, so no changes needed there — the methodology queries just produce more unique terms.

### Config Changes

No new config fields for this change.

---

## 2. Year-Segmented Dynamic minCitationCount

### Problem
Semantic Scholar's single `min_citation_count` parameter is a blunt instrument. A high value (e.g., 5) filters out all 2025–2026 preprints; a low value (0) returns too many low-quality old papers. The current default of 3 misses both frontier papers and foundational work.

### Solution
Replace the single SS call per query with three parallel calls, each targeting a different year segment with its own `minCitationCount`.

### New Config Fields

```python
@dataclass
class SearchConfig:
    # ... existing fields ...

    # Year-segmented SS search
    ss_year_segments: list[dict] = field(default_factory=lambda: [
        {"start": 2025, "end": 2026, "min_citation_count": 0, "label": "frontier"},
        {"start": 2022, "end": 2024, "min_citation_count": 3, "label": "mid"},
        {"start": 0,    "end": 2021, "min_citation_count": 5, "label": "foundational"},
    ])
    ss_frontier_max_results: int = 30  # higher cap for frontier to catch more preprints
    ss_mid_max_results: int = 20
    ss_foundational_max_results: int = 15
```

### New Retrieval Function

```python
def segmented_ss_search(
    ss_tool: "SemanticScholarSearch",
    query: str,
    config: "SearchConfig",
    topic: str = "",
) -> list["Paper"]:
    """Execute three parallel SS searches per query with year-segmented thresholds.

    Each segment gets its own year range and minCitationCount.
    Papers are tagged with hit_channel = "ss_frontier", "ss_mid", "ss_foundational".
    """
    from agent.tools.models import Paper

    all_papers: list[Paper] = []
    for segment in config.ss_year_segments:
        label = segment["label"]
        max_results = getattr(config, f"ss_{label}_max_results", config.ss_max_results)
        result = ss_tool.execute({
            "query": query,
            "max_results": max_results,
            "year_start": segment["start"],
            "year_end": segment["end"],
            "min_citation_count": segment["min_citation_count"],
        })
        if result.success:
            for p_data in result.data.get("papers", []):
                paper = Paper.from_dict(p_data)
                paper.hit_channels.append(f"ss_{label}")
                paper.search_source_queries.append(query)
                all_papers.append(paper)

    return all_papers
```

### Pipeline Integration

Replace the single SS call in `_retrieve_papers`:
```python
# Old:
ss_result = ss_tool.execute({"query": q, "max_results": config.ss_max_results})
# New:
ss_papers = segmented_ss_search(ss_tool, q, config, topic)
all_papers.extend(ss_papers)
```

---

## 3. Relevance Filter Contribution Type Restructure

### Problem
The current 3-level relevance (strong/weak/irrelevant) cannot distinguish between "method extension" papers (high value for a survey) and "downstream application" papers (low value). Both are "weak" and treated identically.

### Solution
Replace `relevance` with `contribution_type` — a 4-level classification that captures the nature of the contribution, not just relevance strength.

### New Paper Model Field

```python
@dataclass
class Paper:
    # ... existing fields ...
    contribution_type: str = "weak_application"  # strong | weak_extension | weak_application | irrelevant
```

### New Prompt

```python
RELEVANCE_JUDGE_PROMPT = """\
You are a strict relevance judge for academic literature search.

TASK: For each paper, determine its contribution type relative to the
research topic: "{topic}"

CONTRIBUTION TYPES:
- strong: The paper's PRIMARY contribution is a core METHODOLOGICAL INNOVATION
  directly addressing the topic. The paper proposes, analyzes, or fundamentally
  improves the method ITSELF. Examples: a new attention mechanism variant,
  a novel position encoding scheme, a theoretical analysis of the method.
  → HIGH VALUE for survey — keep unconditionally.

- weak_extension: The paper's primary contribution is an EXTENSION or
  IMPROVEMENT of an existing method applied to a domain task. The method
  innovation is real but not the main claim. Examples: adapting a method
  to a new modality with architectural modifications, improving efficiency
  for a specific use case.
  → MODERATE VALUE for survey — keep.

- weak_application: The paper uses the target method primarily as a TOOL
  or COMPONENT within a larger system applied to a DOWNSTREAM TASK. The
  paper's contribution is in the application, not the method itself.
  Examples: "X for image classification", "X-based Y detection system",
  "applying X to Z problem".
  → LOW VALUE for survey — keep only if confidence is high.

- irrelevant: The paper does not address the topic or addresses it only
  in passing. Completely different field or topic.
  → REMOVE if confidence >= 0.6.

CONFIDENCE SCORE (0.0 to 1.0):
- 1.0: Absolutely certain
- 0.8-0.9: Very confident
- 0.6-0.7: Moderately confident
- 0.4-0.5: Weakly confident
- 0.0-0.3: Very uncertain

SPECIAL RULES:
- Papers WITHOUT an abstract: default to weak_application, confidence capped at 0.6.
- When in doubt between strong and weak_extension, prefer weak_extension.
- When in doubt between weak_extension and weak_application, prefer weak_extension.
- weak_application with confidence < 0.6: downgrade to irrelevant and remove.

OUTPUT FORMAT: Return a JSON object:
{{
  "judgments": [
    {{"index": 1, "title": "Exact title",
      "contribution_type": "strong|weak_extension|weak_application|irrelevant",
      "confidence": 0.95, "reason": "Short justification"}}
  ]
}}
"""
```

### Updated Filter Logic

```python
class RelevanceFilter:
    def filter(self, papers: list[Paper], topic: str) -> list[Paper]:
        # ... existing setup, prompt generation, LLM call, parse ...

        for p in papers:
            judgment = judgments.get(p.title.lower(), {})
            ct = judgment.get("contribution_type", "weak_application")
            conf = judgment.get("confidence", 0.0)
            reason = judgment.get("reason", "")

            p.contribution_type = ct
            p.relevance_confidence = conf
            p.relevance_reason = reason

            # No abstract → cap confidence at 0.6, force weak_application
            if not p.abstract:
                if conf > 0.6:
                    p.relevance_confidence = 0.6
                    conf = 0.6
                if ct in ("strong", "weak_extension"):
                    ct = "weak_application"
                    p.contribution_type = ct

            # Filtering rules
            if ct == "irrelevant" and conf >= self.config.relevance_confidence_min:
                logger.warning("Filtered out: '%s'", p.title)
                continue

            if ct == "weak_application" and conf < self.config.relevance_confidence_min:
                p.contribution_type = "weak_application"
                p.relevance_confidence = conf
                # Keep but mark as low-value (will be suppressed in ranking)

            kept.append(p)

        # Log distribution
        strong = sum(1 for p in kept if p.contribution_type == "strong")
        ext = sum(1 for p in kept if p.contribution_type == "weak_extension")
        app = sum(1 for p in kept if p.contribution_type == "weak_application")
        filtered = len(papers) - len(kept)
        logger.info("Contributions: strong=%d, extension=%d, application=%d, filtered=%d",
                     strong, ext, app, filtered)

        return kept
```

### Parse Update

The `_parse_judgments` method must also read the new `contribution_type` field:

```python
judgments[title] = {
    "contribution_type": j.get("contribution_type", "weak_application"),
    "confidence": float(j.get("confidence", 0.0)),
    "reason": j.get("reason", ""),
}
```

---

## 4. Composite Ranking Upgrade

### Problem
Current ranking `α·citation + β·relevance + γ·recency` gives equal weight to all "weak" papers and uses a linear recency clip that doesn't distinguish between 2025 and 2026 papers.

### Solution
Replace the relevance score with a contribution-type weight, and replace the linear recency with an exponential decay factor.

### New Config Fields

```python
@dataclass
class SearchConfig:
    # ... existing rank_alpha, rank_beta, rank_gamma ...
    # Contribution type weights
    rank_contribution_strong: float = 1.0
    rank_contribution_extension: float = 0.6
    rank_contribution_application: float = 0.2
    rank_contribution_default: float = 0.5

    # Time decay
    rank_decay_factor: float = 0.15  # lambda in exp(-lambda * age)
    rank_current_year: int = 2026
```

### Updated Ranking Formula

```python
def rank_papers(papers: list["Paper"], config: "SearchConfig") -> list["Paper"]:
    if not papers:
        return papers

    max_citations = max(p.citation_count for p in papers) or 1
    current_year = config.rank_current_year  # 2026

    for p in papers:
        # 1. Citation score (normalized)
        citation_score = p.citation_count / max_citations

        # 2. Contribution type weight
        ct = getattr(p, "contribution_type", "weak_application") or "weak_application"
        if ct == "strong":
            contrib_weight = config.rank_contribution_strong       # 1.0
        elif ct == "weak_extension":
            contrib_weight = config.rank_contribution_extension    # 0.6
        elif ct == "weak_application":
            contrib_weight = config.rank_contribution_application  # 0.2
        else:
            contrib_weight = config.rank_contribution_default      # 0.5

        # 3. Recency with exponential decay
        age = current_year - p.year if p.year > 0 else 10
        recency_score = math.exp(-config.rank_decay_factor * age)  # exp(-0.15 * age)

        p.composite_score = round(
            config.rank_alpha * citation_score
            + config.rank_beta * contrib_weight
            + config.rank_gamma * recency_score,
            4,
        )

    # RRF remains the same
    if config.rrf_enabled and len(papers) > 1:
        papers = _apply_rrf(papers, config)

    papers.sort(key=lambda p: p.composite_score, reverse=True)
    return papers
```

Exponential decay values for age=0..6 with λ=0.15:
- Age 0 (2026): 1.000
- Age 1 (2025): 0.861
- Age 2 (2024): 0.741
- Age 3 (2023): 0.637
- Age 4 (2022): 0.549
- Age 5 (2021): 0.472
- Age 6 (2020): 0.407

This gives a smooth, non-linear penalty that preserves some score for older papers while strongly favoring recent ones.

---

## 5. Year-Stratified Quota Balancing

### Problem
Even with improved ranking, the top-N papers by score can still cluster in one time period, especially if citation-heavy mid-term papers dominate.

### Solution
Post-ranking stratified sampling: allocate slots across three time periods, then fill from the top-ranked papers within each segment.

### New Config Fields

```python
@dataclass
class SearchConfig:
    # ... existing fields ...
    stratify_frontier_quota: float = 0.30   # 2025-2026
    stratify_mid_quota: float = 0.40        # 2022-2024
    stratify_classic_quota: float = 0.30    # < 2022
    stratify_frontier_start: int = 2025
    stratify_mid_start: int = 2022
```

### New Function

```python
def stratified_sample(
    papers: list["Paper"],
    config: "SearchConfig",
    max_papers: int,
) -> list["Paper"]:
    """Stratified sampling by year to ensure temporal coverage.

    Splits sorted papers into three time segments, allocates slots per
    quota, and fills from top-ranked within each segment.
    """
    if not papers:
        return papers

    current_year = config.rank_current_year

    frontier = [p for p in papers if p.year >= config.stratify_frontier_start]
    mid = [p for p in papers if config.stratify_mid_start <= p.year < config.stratify_frontier_start]
    classic = [p for p in papers if 0 < p.year < config.stratify_mid_start]

    segments = [
        (frontier, config.stratify_frontier_quota, "frontier"),
        (mid, config.stratify_mid_quota, "mid"),
        (classic, config.stratify_classic_quota, "classic"),
    ]

    result = []
    total_allocated = 0

    for seg_papers, quota, label in segments:
        # Each segment is already sorted by composite_score (descending)
        slot_count = min(len(seg_papers), max(1, round(max_papers * quota)))
        result.extend(seg_papers[:slot_count])
        total_allocated += slot_count
        logger.info("Stratify %s: %d/%d slots", label, slot_count, len(seg_papers))

    # If total < max_papers due to shortage in some segments,
    # fill remaining from the overall ranked list (excluding already selected)
    selected_titles = {p.title.lower().strip() for p in result}
    if total_allocated < max_papers:
        for p in papers:
            if p.title.lower().strip() not in selected_titles:
                result.append(p)
                selected_titles.add(p.title.lower().strip())
                total_allocated += 1
                if total_allocated >= max_papers:
                    break

    return result[:max_papers]
```

### Pipeline Integration

Insert after `rank_papers` and before the final `self._papers = [...]`:

```python
papers = rank_papers(papers, config)
# ... existing fallback phase6/7 ...
papers = stratified_sample(papers, config, self._task.max_papers)
```

---

## 6. Fallback Survey-Oriented Queries

### Problem
Phase 6 fallback uses `[topic] + keywords[:3]` as queries, which are the same terms already searched. This amplifies the same bias toward known terms.

### Solution
Add two new query types to the fallback query list:

1. **Survey reverse query**: `"survey {topic}" OR "review {topic}"` — finds survey papers that cite the core methods, then the pipeline's citation extraction can follow those references
2. **Methodology query**: `"{topic} method" OR "{topic} approach" OR "{topic} technique"` — broad method-level search that catches papers describing the method itself

### Updated Fallback

```python
def fallback_phase6(
    self,
    papers: list["Paper"],
    topic: str,
    keywords: list[str],
) -> list["Paper"]:
    """Phase 6 Fallback: adds survey-oriented and methodology queries."""

    queries = [topic] + keywords[:3]

    # Add survey reverse query
    survey_query = f'"survey {topic}" OR "review {topic}"'
    queries.append(survey_query)

    # Add methodology query
    method_query = f'"{topic} method" OR "{topic} approach" OR "{topic} technique"'
    queries.append(method_query)

    # ... rest of implementation unchanged (dual-channel arXiv for each query) ...
```

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `agent/tools/prompts.py` | Modify | Add `METHODOLOGY_QUERY_PROMPT`; update `RELEVANCE_JUDGE_PROMPT` with 4-level contribution types |
| `agent/core/config.py` | Modify | Add `ss_year_segments`, `ss_*_max_results`, `rank_contribution_*`, `rank_decay_factor`, `stratify_*_quota` |
| `agent/tools/models.py` | Modify | Add `contribution_type: str = "weak_application"` to Paper |
| `agent/tools/retrieval.py` | Modify | Add `segmented_ss_search()`; update `FallbackManager.fallback_phase6` with survey queries |
| `agent/tools/relevance.py` | Modify | Update filter logic for 4 contribution types; update `_parse_judgments` |
| `agent/tools/processing.py` | Modify | Update `rank_papers` with contribution weights + exponential decay; add `stratified_sample()` |
| `agent/core/pipeline.py` | Modify | Call `METHODOLOGY_QUERY_PROMPT` in Phase B; replace SS call with `segmented_ss_search`; add `stratified_sample` call |

---

## Testing Notes

- **Config tests**: verify new default values, verify year segment boundaries
- **Prompt tests**: verify methodology prompt avoids application terms, verify relevance prompt includes all 4 types
- **Model tests**: verify `contribution_type` field serialization in `to_dict`/`from_dict`
- **Retrieval tests**: verify `segmented_ss_search` calls SS with correct year/minCitation per segment; verify fallback survey queries are generated
- **Relevance tests**: verify `weak_application` filter logic (keep high conf, keep low conf but mark), verify `weak_extension` always kept, verify distribution logging
- **Processing tests**: verify contribution type weights, exponential decay values, stratified sampling quotas and edge cases (empty segment, shortage)
- **Integration tests**: verify full pipeline returns papers with `contribution_type` set, verify temporal distribution

## Spec Self-Review

- **Placeholder scan**: No TBDs, TODOs, or incomplete sections ✓
- **Internal consistency**: All config fields referenced in module sections match the Config section ✓
- **Scope**: Focused on the 6 specified improvements, no scope creep ✓
- **Ambiguity check**: Each contribution type has clear examples and filter rules; each configuration field has a default value ✓