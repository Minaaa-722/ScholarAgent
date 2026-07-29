# Phase 1: Evidence Grounding Layer — Design Spec

## Overview

Improve ScholarAgent's factual reliability by grounding the writing stage in
structured, verified evidence extracted from paper PDFs. The LLM can organize
and summarize evidence but cannot create or fabricate technical facts.

**Core principle:** LLM organizes evidence, but does not create evidence.

## Architecture

```
PLANNING → RETRIEVAL (extended) → ANALYSIS → WRITING → VALIDATION → FEEDBACK
                │                      │          │           │
                ▼                      ▼          ▼           ▼
          PDF download           LLM analysis  Context     Evidence
          PDFParser              with evidence Retriever   Checker
          EvidenceExtractor      references    → Builder   (3 stores)
```

No new pipeline stages. No changes to AgentState or StateMachine.

## EvidenceReference Validation

LLM-extracted evidence must be verified against original PDFChunk content
before storage in any store. The validation flow:

```
PDFChunk ──→ EvidenceExtractor (LLM) ──→ raw EvidenceReference
                                              │
                                              ▼
                                    EvidenceReferenceValidator
                                    (cross-check excerpt against
                                     original PDFChunk content)
                                              │
                                              ▼
                                    verified EvidenceReference
                                              │
                                              ▼
                                    BenchmarkStore / PaperKnowledgeBase
```

**EvidenceReferenceValidator** — cross-references the LLM-extracted excerpt
against the original source chunks:

```python
class EvidenceReferenceValidator:
    """Validates extracted evidence against original PDFChunk content.
    
    Because evidence may span pages or sections, validation supports
    checking against multiple chunks simultaneously.
    
    Checks:
    - excerpt substring match: the extracted excerpt should appear in at
      least one of the source chunks (exact or near-exact match after
      whitespace normalization)
    - page_number range: page number must be within the paper's page range
      (if multiple chunks, any matching chunk's page is acceptable)
    - source_type consistency: "table" evidence should reference a table_id
    """
    def validate(
        self, ref: EvidenceReference, chunks: list[PDFChunk]
    ) -> bool
    def validate_all(
        self, refs: list[EvidenceReference], chunks: list[PDFChunk]
    ) -> list[EvidenceReference]  # returns only valid refs
```

Rules:
1. **Excerpt match** (multi-chunk): extracted excerpt must be a substring of
   *at least one* source chunk (whitespace-normalized).  A single piece of
   evidence may reference text that spans a page boundary — the validator
   searches across all chunks for the paper.
2. **Page range**: page_number must be valid for the paper.  Accept -1 for
   unknown page numbers.
3. **Source type consistency**: "table" type requires a non-empty table_id;
   "figure" type requires a non-empty table_id (used for figure references).

Rejected references are logged and discarded.  The pipeline continues
without them.

## BenchmarkRecord Verification Lifecycle

Benchmark records follow a strict lifecycle:

```
BenchmarkExtractor
    │
    ▼
unverified BenchmarkRecord    (verified = False)
    │
    ▼
BenchmarkVerifier
    │  ├─ checks EvidenceReference exists and is valid
    │  ├─ checks benchmark number is plausible (non-negative, etc.)
    │  └─ cross-references model_name against paper metadata
    │
    ▼
verified BenchmarkRecord      (verified = True)
    │
    ▼
BenchmarkStore.get_verified()
```

The `BenchmarkVerifier` is a new module:

```python
class BenchmarkVerifier:
    """Verifies benchmark records against source evidence and paper metadata.
    
    A benchmark record is considered verified when:
    1. Its EvidenceReference passed validation (exists in source PDF)
    2. Semantic consistency: model_name, benchmark_name, and score/metric
       all appear in the evidence excerpt
    3. The score is internally consistent (no obviously impossible values)
    4. The model_name can be plausibly linked to the paper
    
    Semantic consistency checks prevent the LLM from fabricating benchmark
    numbers that reference a real paper but have no basis in the evidence:
      - model_name appears in source excerpt (case-insensitive)
      - benchmark_name appears in source excerpt (case-insensitive)
      - score or metric appears in source excerpt
    If any of these are missing from the excerpt, the record is rejected.
    """
    def __init__(self, llm: LLMBase | None = None)
    def verify(
        self, records: list[BenchmarkRecord], papers: list[dict]
    ) -> list[str]  # Returns record IDs that passed verification
    def verify_record(
        self, record: BenchmarkRecord, paper: dict | None = None
    ) -> bool  # Single-record verification
```

Only verified records (verified=True) are returned by `get_verified()` and
used in the writing context.  Unverified records remain in the store for
auditing but are excluded from evidence grounding.

## PaperKnowledge Evidence Ownership

Clear ownership boundaries:

- **KnowledgeField** (field-level): owns its own evidence trail.
  Each field (e.g., `vision_encoder`) stores its `evidence_refs` directly,
  pointing to the specific EvidenceReference objects that support that field.

- **PaperKnowledge.evidence_refs** (paper-level): stores only evidence that
  applies to the paper as a whole — motivation, problem definition, main
  contribution, and limitations.  These are NOT duplicated at the field level.

- **ArchitectureKnowledge / TrainingKnowledge**: composed of KnowledgeField
  instances.  Each field is independently traceable.  No cross-contamination
  between field-level and paper-level evidence.

```
PaperKnowledge
├── evidence_refs          ← paper-level only (motivation, contribution, etc.)
├── architecture
│   ├── vision_encoder     ← KnowledgeField with own evidence_refs
│   ├── language_model     ← KnowledgeField with own evidence_refs
│   └── ...                ← each field independently traceable
├── training
│   ├── pretraining_dataset ← KnowledgeField with own evidence_refs
│   └── ...
└── datasets               ← DatasetReference with own evidence_refs
```

## EvidenceRanker Interface

The ContextRetriever uses an optional `EvidenceRanker` interface for
evidence selection.  Phase 1 uses a simple default ranking, but the
interface is designed for future extension.

```python
class EvidenceRanker(ABC):
    """Ranks evidence for selection in ContextRetriever.
    
    Implementations can use different strategies:
    - SimpleRanker (Phase 1): verified > unverified, benchmarks > claims
    - RelevanceRanker (future): section-title similarity scoring
    - ConfidenceRanker (future): evidence confidence + citation count
    - DiversityRanker (future): maximize paper diversity in top-k
    """
    @abstractmethod
    def rank_claims(self, claims: list[Claim]) -> list[Claim]
    @abstractmethod
    def rank_benchmarks(self, records: list[BenchmarkRecord]) -> list[BenchmarkRecord]
    @abstractmethod
    def rank_knowledge(self, knowledge: list[PaperKnowledge]) -> list[PaperKnowledge]


class SimpleRanker(EvidenceRanker):
    """Phase 1 default: verified first, then by confidence."""
    def rank_claims(self, claims: list[Claim]) -> list[Claim]:
        return sorted(claims, key=lambda c: (c.verified, c.confidence), reverse=True)
    def rank_benchmarks(self, records: list[BenchmarkRecord]) -> list[BenchmarkRecord]:
        return sorted(records, key=lambda r: r.verified, reverse=True)
    def rank_knowledge(self, knowledge: list[PaperKnowledge]) -> list[PaperKnowledge]:
        return knowledge  # No ranking needed for Phase 1
```

## PDFParser Dependency Priority

Reuse existing PDF infrastructure before adding new dependencies:

1. **Try existing `PdfDownload` + `PdfParse` tools** (already registered in
   ToolRegistry) — these handle PDF download from arXiv URLs and basic text
   extraction.
2. **Fall back to direct PDF download** (`requests.get` from `arxiv.org/pdf/`)
   if the tool-based approach fails.
3. **No new PDF libraries** for Phase 1.  The existing `PdfParse` tool uses
   `PyMuPDF` (fitz) which is already installed.  Chunking is done via simple
   page boundary splitting and section heading heuristics (regex-based).
4. **Fallback to abstract** if PDF download/parsing fails entirely — log a
   warning and treat the paper's abstract as the sole evidence source.

## Implementation Order

Implement Phase 1 incrementally, in this order:

1. **PDF Layer** — `PDFChunk`, `PDFParser`, `ChunkFilter`, `EvidenceReference`,
   `EvidenceReferenceValidator`, `EvidenceExtractor`
   - Can be tested independently with mock PDF content
   - No dependencies on other new modules

2. **Stores** — `BenchmarkRecord`, `BenchmarkStore`, `PaperKnowledge`,
   `PaperKnowledgeBase`, `KnowledgeField`, `DatasetReference`
   - Pure data layer, no LLM dependencies
   - Full test coverage before adding extractors

3. **Extractors** — `BenchmarkExtractor`, `BenchmarkVerifier`, `PaperAnalyzer`
   - Consume EvidenceReference, produce structured records
   - Depend on stores being ready
   - Test with MockLLM

4. **Retriever** — `EvidenceRanker`, `SimpleRanker`, `ContextRetriever`,
   `EvidenceContext`, `EvidenceContextBuilder`
   - Depend on all three stores being populated
   - Test with pre-populated stores

5. **Checker** — Enhanced `EvidenceChecker`
   - Reads from all three stores
   - Depend on stores being ready
   - Regression: all existing checker tests must pass

6. **Pipeline Integration** — `PipelineOrchestrator` changes
   - Wire everything together
   - Integration test last

This order minimizes blocking dependencies and allows testing at each step.

### `agent/evidence/evidence_reference.py`

```python
@dataclass
class EvidenceReference:
    """Unified source traceability object."""
    evidence_id: str
    paper_id: str
    page_number: int = -1
    section: str = ""
    source_type: str = ""       # "text", "table", "figure"
    table_id: str = ""
    excerpt: str = ""

@dataclass
class KnowledgeField:
    """A single knowledge field with its own evidence trail."""
    value: str = ""
    evidence_refs: list[EvidenceReference] = field(default_factory=list)

@dataclass
class DatasetReference:
    """Dataset name with traceability."""
    name: str = ""
    evidence_refs: list[EvidenceReference] = field(default_factory=list)
```

### `agent/evidence/pdf_parser.py`

```python
@dataclass
class PDFChunk:
    paper_id: str
    chunk_id: str
    page_number: int
    section: str = ""
    content: str = ""

class PDFParser:
    """Parses PDF files into page/section/text chunks.
    
    - Uses existing PdfDownload / PdfParse tools
    - Splits by page boundaries
    - Attempts section heading detection via heuristics
    - Returns list of PDFChunk per paper
    """
    def parse(self, paper_id: str, pdf_path: str) -> list[PDFChunk]
```

### `agent/evidence/evidence_extractor.py`

```python
class EvidenceExtractor:
    """Extracts structured EvidenceReference objects from PDF chunks.
    
    Uses LLM with focused prompts per evidence category.  Chunks are
    pre-filtered by lightweight keyword heuristics before LLM extraction
    to keep token usage controlled.
    
    Evidence categories:
      - architecture
      - benchmark
      - dataset
      - training
      - limitation
    """
    def __init__(self, llm: LLMBase, chunk_filter: ChunkFilter | None = None)
    def extract(self, chunks: list[PDFChunk]) -> list[EvidenceReference]
```

**ChunkFilter** — lightweight keyword-based pre-filtering before LLM extraction:
```python
class ChunkFilter:
    """Filters PDF chunks by evidence category using keyword heuristics."""
    CATEGORY_KEYWORDS = {
        "architecture": ["architecture", "encoder", "decoder", "transformer",
                         "backbone", "layer", "block", "module", "attention"],
        "benchmark": ["benchmark", "accuracy", "score", "bleu", "rouge",
                      "f1", "state-of-the-art", "sota", "dataset"],
        "dataset": ["dataset", "corpus", "benchmark", "data collection"],
        "training": ["train", "learning rate", "optimizer", "loss",
                     "gradient", "epoch", "batch size"],
        "limitation": ["limitation", "drawback", "failure", "error",
                       "challenge", "future work", "limitation"],
    }
    def filter(self, chunks: list[PDFChunk], category: str) -> list[PDFChunk]
```

### `agent/evidence/benchmark_store.py`

```python
@dataclass
class BenchmarkRecord:
    """Structured, source-tracked benchmark result."""
    id: str                         # e.g., "mmlu_qwen2vl_accuracy"
    model_name: str
    benchmark_name: str
    metric: str
    score: str                      # "85.3", "4.5/5", "83.2 (+2.4)"
    score_unit: str = "%"
    split: str = ""
    source: EvidenceReference = field(default_factory=EvidenceReference)
    verified: bool = False

class BenchmarkStore:
    def add_records(self, records: list[BenchmarkRecord]) -> None
    def get_verified(self, benchmark_name: str | None = None) -> list[BenchmarkRecord]
    def get_all(self) -> list[BenchmarkRecord]
    def get_by_model(self, model_name: str) -> list[BenchmarkRecord]
    def lookup(self, benchmark_name: str, model_name: str | None = None) -> list[BenchmarkRecord]
    def mark_verified(self, record_ids: list[str]) -> int
    def clear() -> None
```

### `agent/evidence/paper_knowledge.py`

```python
@dataclass
class ArchitectureKnowledge:
    vision_encoder: KnowledgeField = field(default_factory=KnowledgeField)
    language_model: KnowledgeField = field(default_factory=KnowledgeField)
    connector: KnowledgeField = field(default_factory=KnowledgeField)
    fusion_method: KnowledgeField = field(default_factory=KnowledgeField)
    resolution_strategy: KnowledgeField = field(default_factory=KnowledgeField)

@dataclass
class TrainingKnowledge:
    pretraining_dataset: KnowledgeField = field(default_factory=KnowledgeField)
    instruction_dataset: KnowledgeField = field(default_factory=KnowledgeField)
    optimization_method: KnowledgeField = field(default_factory=KnowledgeField)
    loss_function: KnowledgeField = field(default_factory=KnowledgeField)
    training_stage: KnowledgeField = field(default_factory=KnowledgeField)

@dataclass
class PaperKnowledge:
    """Structured per-paper knowledge with evidence traceability."""
    paper_id: str
    title: str = ""
    problem_definition: str = ""
    motivation: str = ""
    main_contribution: str = ""
    architecture: ArchitectureKnowledge | None = None
    training: TrainingKnowledge | None = None
    datasets: list[DatasetReference] = field(default_factory=list)
    benchmark_references: list[str] = field(default_factory=list)
    limitations: str = ""
    evidence_refs: list[EvidenceReference] = field(default_factory=list)

class PaperKnowledgeBase:
    def add(self, knowledge: PaperKnowledge) -> None
    def get(self, paper_id: str) -> PaperKnowledge | None
    def get_all(self) -> list[PaperKnowledge]
    def clear() -> None
```

### `agent/evidence/benchmark_extractor.py`

```python
class BenchmarkExtractor:
    """Extracts structured BenchmarkRecord from EvidenceReference objects.
    
    Takes already-extracted evidence references and identifies benchmark
    results within them.  Uses LLM to parse benchmark numbers, metrics,
    and model names from evidence excerpts.
    """
    def __init__(self, llm: LLMBase)
    def extract(self, evidence_refs: list[EvidenceReference]) -> list[BenchmarkRecord]
```

### `agent/evidence/paper_analyzer.py`

```python
class PaperAnalyzer:
    """Extracts structured PaperKnowledge from EvidenceReference objects.
    
    Takes already-extracted evidence references and organizes them into
    structured per-paper knowledge.  Each KnowledgeField gets its own
    evidence_refs for traceability.
    """
    def __init__(self, llm: LLMBase)
    def analyze(self, evidence_refs: list[EvidenceReference]) -> list[PaperKnowledge]
```

### `agent/evidence/context_retriever.py`

```python
@dataclass
class EvidenceContext:
    """Container for retrieved evidence (no formatting logic)."""
    claims: list[Claim] = field(default_factory=list)
    benchmarks: list[BenchmarkRecord] = field(default_factory=list)
    paper_knowledge: list[PaperKnowledge] = field(default_factory=list)

class ContextRetriever:
    """Selects relevant evidence for writing, controls top-k / token budget.
    
    Queries all three stores and selects evidence based on:
    - relevance (future: section matching)
    - evidence confidence (future: ranking)
    - paper diversity (future: de-duplication)
    - citation importance (future: citation-aware selection)
    
    Token budget enforcement (active, not advisory):
    1. Rank: apply EvidenceRanker to sort evidence by priority
    2. Select: add evidence in priority order until max_context_tokens
       would be exceeded
    3. Preserve metadata: each selected item retains its paper_id,
       page_number, section, and source_type — never strip source info
       to fit within budget
    4. Never truncate: if an item exceeds the remaining budget, skip it
       rather than truncating its source information
    
    Currently uses a simple priority strategy:
    verified > unverified, benchmark over general claim.
    """
    def __init__(
        self,
        evidence_store: EvidenceStore,
        benchmark_store: BenchmarkStore,
        knowledge_base: PaperKnowledgeBase,
        max_context_tokens: int = 1000,
    )
    def retrieve_for_section(
        self,
        section_title: str = "",
        paper_ids: list[str] | None = None,
        category: str = "",
    ) -> EvidenceContext
    
class EvidenceContextBuilder:
    """Formats EvidenceContext into a text block for the writer.
    
    Preserves metadata (paper_id, page_number, section) in the output.
    No retrieval logic — only formatting.
    """
    @classmethod
    def format(cls, context: EvidenceContext) -> str
```

## Pipeline Integration

### `agent/core/pipeline.py` — PipelineOrchestrator changes

| Location | Change |
|---|---|
| `__init__()` | Add `_benchmark_store`, `_paper_knowledge_base`, `_benchmark_extractor`, `_paper_analyzer`, `_pdf_parser`, `_evidence_extractor`, `_pdf_chunks`, `_evidence_refs` |
| `run_pipeline()` | Call `clear()` on all three stores |
| `_retrieve_papers()` | After paper search, download PDFs, parse into chunks, extract evidence references |
| `_analyze_papers()` | Pass evidence references as context to LLM; after analysis, extract benchmarks and paper knowledge from evidence |
| `_write_survey()` | Use ContextRetriever + EvidenceContextBuilder instead of ClaimContextBuilder alone |

### `agent/evidence/checker.py` — EvidenceChecker changes

Enhanced to read from all three stores:

| Check | Source | Detection |
|---|---|---|
| Unsupported claim | EvidenceStore | Claim not in verified claims |
| Benchmark mismatch | BenchmarkStore | Benchmark number in draft ≠ stored record |
| Missing benchmark | BenchmarkStore | Benchmark name in draft but no record |
| Model inconsistency | PaperKnowledgeBase | Architecture/training details contradict stored knowledge |
| Missing evidence | All stores | Strong technical claim with no evidence reference |

Constructor updated:
```python
class EvidenceChecker(Validator):
    def __init__(
        self,
        evidence_store: EvidenceStore,
        benchmark_store: BenchmarkStore,       # NEW
        knowledge_base: PaperKnowledgeBase,     # NEW
        llm: Optional[LLMBase] = None,
    )
```

### `agent/core/harness.py` — Harness changes

```python
class Harness:
    def __init__(self, ...):
        # ... existing ...
        self._validators.append(
            EvidenceChecker(
                evidence_store=self._orchestrator._evidence_store,
                benchmark_store=self._orchestrator._benchmark_store,
                knowledge_base=self._orchestrator._paper_knowledge_base,
                llm=llm,
            )
        )
```

## Error Handling

- **PDF download failure**: Log warning, mark paper as "evidence_unavailable",
  skip paper, continue with remaining papers.  Do NOT silently treat missing
  evidence as verified evidence.
- **PDF parsing failure**: Log warning, mark paper as "evidence_unavailable",
  use abstract as fallback, continue.
- **Evidence extraction failure**: Log warning, continue with empty evidence
  for that paper.  Paper remains marked as "evidence_unavailable".
- **EvidenceReference validation rejection**: Log rejected reference with
  reason (e.g., "excerpt not found in source chunk"), discard reference,
  continue.  Rejected references are NOT stored in any store.
- **Empty stores**: ContextRetriever returns empty context, writer proceeds
  without evidence.
- **Checker with empty stores**: Falls back to basic plausibility check,
  produces warning.
- **Evidence-unavailable papers**: Tracked in a set `_evidence_unavailable`
  on the orchestrator.  These papers are excluded from evidence-based checks
  but can still appear in the reference list.

## File List

### New files
```
agent/evidence/evidence_reference.py   # EvidenceReference, KnowledgeField, DatasetReference
agent/evidence/pdf_parser.py           # PDFParser, PDFChunk, ChunkFilter
agent/evidence/evidence_extractor.py   # EvidenceExtractor, EvidenceReferenceValidator
agent/evidence/benchmark_store.py      # BenchmarkRecord, BenchmarkStore
agent/evidence/benchmark_extractor.py  # BenchmarkExtractor, BenchmarkVerifier
agent/evidence/paper_knowledge.py      # PaperKnowledge, ArchitectureKnowledge, TrainingKnowledge, PaperKnowledgeBase
agent/evidence/paper_analyzer.py       # PaperAnalyzer
agent/evidence/context_retriever.py    # EvidenceRanker, SimpleRanker, ContextRetriever, EvidenceContext, EvidenceContextBuilder
```

### Modified files
```
agent/evidence/__init__.py             # Add new exports
agent/evidence/checker.py              # Enhanced EvidenceChecker (3 stores)
agent/core/pipeline.py                 # Add stores, extractors, PDF parsing, context retriever
agent/core/harness.py                  # Pass new stores to EvidenceChecker
tests/test_evidence.py                 # Add tests for new modules
```

## Testing

### Unit tests (add to `tests/test_evidence.py`)

| Test | Description |
|---|---|
| `test_benchmark_record` | BenchmarkRecord creation and field defaults |
| `test_benchmark_store_add_and_retrieve` | Add records, retrieve by model, lookup |
| `test_benchmark_store_mark_verified` | Mark records as verified by ID |
| `test_benchmark_store_clear` | Clear resets store |
| `test_evidence_reference` | EvidenceReference creation |
| `test_evidence_reference_validator` | Validates excerpt against source chunk |
| `test_evidence_reference_validator_rejects_fabricated` | Rejects excerpt not in source |
| `test_knowledge_field` | KnowledgeField with evidence_refs |
| `test_paper_knowledge` | PaperKnowledge creation with structured fields |
| `test_paper_knowledge_base` | Add, get by paper_id, clear |
| `test_pdf_chunk` | PDFChunk creation |
| `test_chunk_filter` | ChunkFilter filters by category keywords |
| `test_evidence_extractor_empty` | No chunks → empty evidence |
| `test_benchmark_extractor_extracts` | MockLLM returns structured records |
| `test_benchmark_verifier` | Verifies records against paper metadata |
| `test_benchmark_verifier_verification_lifecycle` | Unverified → verified transition |
| `test_paper_analyzer_analyzes` | MockLLM returns structured knowledge |
| `test_evidence_ranker_simple` | SimpleRanker sorts verified first |
| `test_context_retriever_empty` | No stores → empty context |
| `test_context_retriever_with_data` | Retrieves from all three stores |
| `test_evidence_context_builder_format` | Formats context with metadata |
| `test_evidence_checker_benchmark_mismatch` | Detects benchmark number inconsistency |
| `test_evidence_checker_model_inconsistency` | Detects architecture description mismatch |
| `test_evidence_checker_missing_evidence` | Detects strong claim with no evidence |
| `test_evidence_checker_all_three_stores` | Full checker flow with all stores |

### Integration test

| Test | Description |
|---|---|
| `test_orchestrator_evidence_grounding_flow` | Full pipeline with PDF→evidence→stores→writing→validation |

## Constraints

- No changes to `AgentState`, `StateMachine`, `AgentState` enum
- No new pipeline stages
- No changes to `LLMBase`, `ToolRegistry` public API
- No changes to existing feedback validators (except EvidenceChecker)
- Existing `Claim`, `EvidenceStore`, `ClaimExtractor`, `ClaimVerifier` remain unchanged
- All existing tests must pass