# Phase 2: Citation Integrity Layer — Design Spec

## Overview

Build a deterministic citation pipeline on top of the completed Evidence Grounding
Layer (Phase 1).  The LLM generates prose with citation *markers*; all LaTeX
citation formatting, BibTeX generation, benchmark table assembly, and citation
validation are handled programmatically.

**Core principle:** LLM must never generate raw `\cite{}`.

## Problem Analysis

The current writer generates LaTeX citations directly, causing:

| Problem | Root Cause | Phase 2 Solution |
|---------|------------|------------------|
| Invalid BibTeX keys | LLM never sees actual BibTeX keys | CitationStore provides key → entry mapping |
| Missing references | LLM guesses key from paper title | [CITE:key] markers validated against CitationStore |
| Unsupported benchmark citations | No link between BenchmarkRecord and citation | BenchmarkRecord binds `citation_key` field |
| Evidence-citation mismatch | Claim has `paper_id` but no `citation_key` | CitationAnchorStore bridges Claim → Evidence → Paper → Citation |

## Design Principles

1. **LLM must never generate raw `\cite{}`** — use `[CITE:key]` markers instead
2. **Citation identifiers must come from CitationStore** — single source of truth
3. **Evidence and Citation must have explicit mapping** — CitationAnchorStore bridges them
4. **High-risk content must have deterministic citation injection** — benchmark tables, architecture claims
5. **Do not use LLM for citation validation** — rule-based checks only

## Architecture

```
RETRIEVAL
    │
    ├── 检索论文 (existing)
    ├── 下载/解析 PDF (existing)
    └── 填充 CitationStore (NEW)
         │  paper_id → citation_key
         │  citation_key → BibTeX entry
         │  model_name → paper_id (alias index)
         │  generate_references_bib() → str

ANALYSIS
    │
    ├── LLM分析 (existing)
    ├── ClaimExtractor (existing) → EvidenceStore (existing)
    ├── ClaimVerifier (existing)
    └── 构建 CitationAnchorStore (NEW)
         │  Claim → EvidenceReference → Paper → CitationKey
         │  从 EvidenceStore + CitationStore 构建

WRITING
    │
    ├── 构建增强 EvidenceContext (modified)
    │   └── 包含 citation_key 锚点信息
    │
    ├── LLM 生成 Prose + 标记
    │   ├── [CITE:key] — 引用标记
    │   ├── [TABLE:benchmark_MMLU] — benchmark 表格占位
    │   └── [TABLE:model_taxonomy] — 模型对比表格占位
    │
    └── Deterministic Post-processing
        ├── CitationInjector (NEW) — [CITE:key] → \cite{key}
        ├── TableGenerator (NEW) — 从 BenchmarkStore 生成 LaTeX 表格
        └── FormatRepair (existing)

VALIDATION
    │
    ├── EvidenceChecker (existing, 无改动)
    ├── CitationChecker (enhanced) — 新增规则
    │   ├── 无效 citation key
    │   ├── 缺失 BibTeX 条目
    │   ├── benchmark 无引用
    │   └── 无证据支持的技术主张
    └── 其他 Validator (existing, 无改动)
```

## Module Specifications

### 1. CitationStore

File: `agent/evidence/citation_store.py`

Single source of truth for all citation-related data.

```
@dataclass
class CitationEntry:
    citation_key: str           # "qwen2024"
    paper_id: str               # "qwen2024" (matches EvidenceReference.paper_id)
    bibtex_entry: str           # "@article{qwen2024, ...}"
    title: str
    authors: list[str]
    year: int
    venue: str = ""
    model_names: list[str] = field(default_factory=list)  # alias index

class CitationStore:
    """paper_id ↔ citation_key ↔ BibTeX, with model alias resolution."""

    def register(self, paper: dict, model_names: list[str] | None = None) -> str
        """Register a paper dict from RETRIEVAL stage.
        Returns the generated citation_key.
        """
        # Key generation: firstAuthorYearKeyword
        # 1. Extract first author surname (lowercase, ASCII-safe)
        # 2. Extract year
        # 3. Extract first keyword from title (lowercase, alphanumeric)
        # 4. Handle collision: append a/b/c suffix
        # 5. Store model_names from PaperKnowledgeBase (optional)
        # 6. Store alias: model_name → paper_id

    def lookup_by_key(self, key: str) -> CitationEntry | None
    def lookup_by_paper_id(self, paper_id: str) -> CitationEntry | None
    def lookup_by_model(self, model_name: str) -> list[CitationEntry]
        """Resolve model alias → paper_id → CitationEntry.
        Returns list (one model may be in multiple papers).
        """

    def get_all_keys(self) -> list[str]
        """For validation: all valid citation keys."""

    def generate_references_bib(self) -> str
        """Generate complete references.bib content.
        Returns a single string of all BibTeX entries sorted by citation_key.
        """
```

**Key generation algorithm:**

```
input: paper dict {title, authors, year}
1.  first_author = authors[0].split()[-1]       # surname
    first_author = re.sub(r'[^a-zA-Z]', '', first_author).lower()
2.  year_str = str(year)
3.  keyword = extract_first_keyword(title)        # first significant word
    keyword = re.sub(r'[^a-zA-Z0-9]', '', keyword).lower()
4.  candidate = f"{first_author}{year_str}{keyword}"
5.  if candidate exists: append 'a', 'b', ... until unique
6.  return candidate
```

**Model alias resolution (two sources):**
1. Primary: `PaperKnowledgeBase.architecture` fields (vision_encoder, language_model, etc.)
2. Fallback: Paper title prefix (e.g., "Qwen2-VL: ..." → model_name = "Qwen2-VL")
3. Stored in `CitationEntry.model_names` as `list[str]`

### 2. CitationAnchorStore

File: `agent/evidence/citation_anchor_store.py`

Explicit mapping chain: Claim → Evidence → Paper → CitationKey.

```
@dataclass
class CitationAnchor:
    """A single claim-to-citation linkage."""
    claim_text: str
    category: str                    # architecture, benchmark, dataset, comparison
    paper_id: str
    citation_key: str                # resolved from CitationStore
    confidence: float
    evidence_excerpt: str = ""       # from EvidenceReference or Claim.source_excerpt


class CitationAnchorStore:
    """Maintains Claim → Evidence → Paper → Citation mapping."""

    def build(
        self,
        claims: list[Claim],
        citation_store: CitationStore,
        paper_knowledge_base: PaperKnowledgeBase,
    ) -> None
        """Build anchors from verified claims and CitationStore.
        For each claim:
          1. Get paper_id from Claim.paper_id
          2. Resolve paper_id → citation_key via CitationStore
          3. Optionally enrich with model_name from PaperKnowledgeBase
          4. Create CitationAnchor
        """

    def get_anchors(self) -> list[CitationAnchor]
    def get_anchors_by_category(self, category: str) -> list[CitationAnchor]
    def get_evidence_map(self) -> dict[str, list[str]]
        """claim_text → [citation_key, ...]  for EvidenceContextBuilder."""

    def get_anchor_for_claim(self, claim_text: str) -> CitationAnchor | None
```

### 3. CitationInjector

File: `agent/evidence/citation_injector.py`

Deterministic post-processing: replaces markers with LaTeX `\cite{}`.

```
class CitationInjector:
    """Post-process prose: [CITE:key] → \cite{key} with validation.

    Input:  "Qwen2-VL [CITE:qwen2024] achieves 85.3% on MMLU."
    Output: "Qwen2-VL~\cite{qwen2024} achieves 85.3\% on MMLU."
    """

    def __init__(self, citation_store: CitationStore):
        self._store = citation_store

    def inject(self, draft: str) -> str
        """Replace all [CITE:key] markers with \cite{key}.

        Steps:
          1. Extract all [CITE:key] markers from draft
          2. Validate each key exists in CitationStore
          3. Replace: [CITE:key] → ~\cite{key} (before period)
          4. Log warnings for invalid keys (keep marker as-is for visibility)
          5. Return cleaned draft

        Returns:
            str with \cite{} commands inserted.
        """

    def validate_all(self, draft: str) -> list[str]
        """Extract and validate all citation keys in draft.
        Returns list of invalid keys (empty if all valid).
        """
```

**Replacement rules:**
- `[CITE:key]` → `~\cite{key}` (prefer non-breaking space before cite)
- Multiple markers: `[CITE:key1][CITE:key2]` → `~\cite{key1,key2}`
- Invalid keys: keep `[CITE:INVALID_KEY]` untouched, log warning

### 4. BenchmarkTableGenerator

File: `agent/evidence/table_generator.py`

Generates CVPR-format LaTeX tables from verified benchmark records.

```
class BenchmarkTableGenerator:
    """Generate LaTeX tables from verified BenchmarkRecord.

    Mode 1 — Benchmark-specific table (default):
      One table per benchmark_name, sorted by score descending.
      Triggered by marker: [TABLE:benchmark_MMLU], [TABLE:benchmark_MathVista], etc.

    Mode 2 — Summary comparison table (optional):
      Architecture/training comparison from PaperKnowledgeBase.
      Triggered by marker: [TABLE:model_taxonomy]
    """

    def __init__(
        self,
        benchmark_store: BenchmarkStore,
        citation_store: CitationStore,
    ):
        ...

    def generate_benchmark_table(self, benchmark_name: str) -> str
        """Generate one LaTeX table for a specific benchmark.

        Steps:
          1. Get verified records for benchmark_name from BenchmarkStore
          2. Sort by score descending
          3. Generate CVPR three-line table format
          4. Each row: model_name | score | \cite{citation_key}

        Returns:
            LaTeX table string, or empty string if no data.
        """

    def generate_summary_table(self, knowledge_base: PaperKnowledgeBase) -> str
        """Generate architecture/training comparison table.

        Rows: models
        Columns: architecture fields (vision_encoder, language_model, connector, resolution_strategy)
        Each cell: field value from PaperKnowledgeBase

        Optional — only generated if [TABLE:model_taxonomy] marker appears.
        """

    def replace_tables(self, draft: str, knowledge_base: PaperKnowledgeBase) -> str
        """Replace all [TABLE:...] markers in draft with generated tables.

        Supported markers:
          [TABLE:benchmark_<NAME>] → benchmark-specific table
          [TABLE:model_taxonomy]   → summary comparison table
        Unknown markers: leave as-is, log warning.
        """
```

**Table format (CVPR three-line style):**

```latex
\begin{table}[htbp]
\centering
\caption{Performance comparison on MMLU.}
\begin{tabular}{lcc}
\toprule
Model & MMLU & Source \\
\midrule
Qwen2-VL & 85.3\% & \cite{qwen2024} \\
LLaVA-NeXT & 82.1\% & \cite{liu2023llava} \\
\bottomrule
\end{tabular}
\end{table}
```

### 5. CitationChecker Enhancement

File: `agent/feedback/check_citations.py` (modified)

Enhanced to check structural citation integrity only (no semantic checks).

```
class CitationChecker(Validator):
    name = "check_citations"

    def __init__(self, citation_store: CitationStore | None = None):
        self._store = citation_store

    def validate(self, context: dict) -> ValidationResult:
        """Check structural citation integrity.

        Rules:
          1. Invalid citation keys: \cite{key} where key not in CitationStore
          2. Missing BibTeX: citation key exists but no BibTeX entry
          3. Benchmark without citation: benchmark number in text but no [CITE:key] nearby
          4. Unsupported technical claim: strong claim with no [CITE:key] marker
          5. Injected markers still present: [CITE:key] not replaced (post-processing failure)
          6. Stale table markers: [TABLE:...] not replaced (post-processing failure)

        Repair instructions:
          - Invalid keys → suggest correct key from CitationStore.lookup_by_model()
          - Missing citations → suggest adding [CITE:key] based on context
          - Stale markers → re-run CitationInjector

        Returns:
          passed: score >= 0.7
          score: weighted by severity
        """
```

**NOT checked (explicitly excluded):**
- Semantic correctness of citation (does this paper actually support this claim?)
- Sentence-level citation coverage (every sentence must have a citation)
- Citation density (too many/few citations per paragraph)

## Pipeline Integration

### PipelineOrchestrator changes

| Location | Change |
|----------|--------|
| `__init__()` | Add `_citation_store`, `_citation_anchor_store`, `_citation_injector`, `_table_generator` |
| `run_pipeline()` | Call `clear()` on new stores |
| `_retrieve_papers()` | After paper search, register each paper in `CitationStore` |
| `_analyze_papers()` | After claim extraction/verification, build `CitationAnchorStore` |
| `_write_survey()` | Inject enhanced evidence context (with citation anchors); use `[CITE:key]` in prompt; post-process with injector + table generator |

### Harness changes

| Location | Change |
|----------|--------|
| `__init__()` | Create `CitationStore`; pass to `CitationChecker` |
| `validators` | Update `CitationChecker` with `CitationStore` |

### Prompt change (writing stage)

**Old prompt instruction:**
```
Use \cite{ref} for citations.
All \cite{} keys must use BibTeX-style keys (e.g., author2023title).
```

**New prompt instruction:**
```
Use [CITE:key] markers for citations (e.g., [CITE:qwen2024]).
NEVER write \cite{} directly — the system will convert markers automatically.
Use [TABLE:benchmark_MMLU] for benchmark results (the system will insert the table).
The planner defines which sections require which table markers.
Available citation keys are listed in the Citation Context below.
```

## File List

### New files

| File | Purpose |
|------|---------|
| `agent/evidence/citation_store.py` | CitationStore, CitationEntry |
| `agent/evidence/citation_anchor_store.py` | CitationAnchorStore, CitationAnchor |
| `agent/evidence/citation_injector.py` | CitationInjector |
| `agent/evidence/table_generator.py` | BenchmarkTableGenerator |

### Modified files

| File | Change |
|------|--------|
| `agent/evidence/__init__.py` | Add new exports |
| `agent/evidence/benchmark_store.py` | BenchmarkRecord add `citation_key` field |
| `agent/evidence/evidence_store.py` | Claim add `citation_key` field |
| `agent/evidence/context_retriever.py` | EvidenceContextBuilder include citation anchor info |
| `agent/feedback/check_citations.py` | Enhanced CitationChecker |
| `agent/core/pipeline.py` | New stores, post-processing, prompt change |
| `agent/core/harness.py` | Pass CitationStore to CitationChecker |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| CitationStore empty | Writing proceeds without citation context (fallback to Phase 1 behavior) |
| Invalid [CITE:key] | CitationInjector keeps marker as-is, logs warning; CitationChecker flags it |
| Table generator: no data | [TABLE:...] marker stays in draft, CitationChecker flags it as stale |
| Collision in citation key | Append 'a', 'b', ... suffix; log warning |
| Model alias not found | Registration time: log warning, store empty model_names list |
| CitationAnchorStore: no match | EvidenceStore claim without citation_key → skip, log warning |

## What We Do NOT Build

| Feature | Reason |
|---------|--------|
| Semantic citation validation | Rule-based checks are sufficient; LLM validation costs don't justify the benefit |
| Sentence-level citation tracking | Only track at claim level and benchmark level |
| LLM-based citation repair | Deterministic replacement is more reliable |
| Cross-document citation consistency | Out of scope — only concerns survey's internal citations |
| Online BibTeX query per citation | Batch generate at retrieval time, use static mapping thereafter |
| Citation density analysis | Not actionable enough to warrant the complexity |

## Implementation Order

### Phase 2.1 — Foundation (no dependencies, independently testable)

```
Step 1: CitationStore
  - agent/evidence/citation_store.py
  - CitationEntry dataclass, CitationStore class
  - Key generation, lookup, model alias, BibTeX generation
  - Tests: mock paper data, verify key generation, lookup, collision handling

Step 2: CitationAnchorStore
  - agent/evidence/citation_anchor_store.py
  - CitationAnchor, CitationAnchorStore
  - Build from EvidenceStore + CitationStore
  - Tests: mock claims and citations, verify anchor creation and query
```

### Phase 2.2 — Data model changes (depend on Step 1)

```
Step 3: Modify Claim and BenchmarkRecord
  - Claim: add citation_key field (optional, default "")
  - BenchmarkRecord: add citation_key field (optional, default "")
  - Update __init__.py exports
  - Tests: verify new fields serialize/deserialize correctly
```

### Phase 2.3 — Post-processing modules (depend on Step 1-2)

```
Step 4: CitationInjector
  - agent/evidence/citation_injector.py
  - [CITE:key] → \cite{key} replacement
  - Key validation, invalid key logging
  - Tests: mock text with markers, verify replacement, edge cases

Step 5: BenchmarkTableGenerator
  - agent/evidence/table_generator.py
  - Benchmark-specific tables from verified records
  - Summary comparison table from PaperKnowledgeBase
  - Tests: mock benchmark data, verify LaTeX table output
```

### Phase 2.4 — Pipeline integration (depend on Step 1-3)

```
Step 6: PipelineOrchestrator changes
  - Initialize CitationStore, CitationAnchorStore, CitationInjector, TableGenerator
  - Call CitationStore.register() in _retrieve_papers() after paper search
  - Call CitationAnchorStore.build() in _analyze_papers() after claim verification
  - Modify _write_survey():
    - Enhanced EvidenceContextBuilder with citation anchors
    - New prompt using [CITE:key] markers
    - Post-processing: CitationInjector.inject() + TableGenerator
  - Tests: full pipeline integration test

Step 7: CitationChecker enhancement + Harness changes
  - Enhanced CitationChecker with CitationStore dependency
  - Pass CitationStore from Harness to CitationChecker
  - Tests: mock drafts with various citation issues
```

## Testing Strategy

### Unit tests

| Test | Module |
|------|--------|
| test_citation_entry_creation | CitationStore |
| test_citation_key_generation | CitationStore |
| test_citation_key_collision | CitationStore |
| test_lookup_by_key_paper_id_model | CitationStore |
| test_generate_references_bib | CitationStore |
| test_citation_anchor_creation | CitationAnchorStore |
| test_citation_anchor_no_claim | CitationAnchorStore |
| test_citation_injector_basic | CitationInjector |
| test_citation_injector_invalid_key | CitationInjector |
| test_citation_injector_multiple_keys | CitationInjector |
| test_benchmark_table_generator | TableGenerator |
| test_benchmark_table_empty | TableGenerator |
| test_summary_table_generator | TableGenerator |

### Integration tests

| Test | Scope |
|------|-------|
| test_orchestrator_citation_flow | Full pipeline: retrieval → citation → analysis → anchors → writing → injector → validation |
| test_citation_checker_enhanced | All new validation rules |

## Migration

No migration needed. Phase 2 modules are additive:
- Existing surveys continue to work (CitationStore empty → fallback to Phase 1 behavior)
- New Phase 2 components are only activated when data is available
- No changes to existing database or file formats