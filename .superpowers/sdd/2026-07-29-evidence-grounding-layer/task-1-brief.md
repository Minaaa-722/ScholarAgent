# Task 1: PDF Layer — EvidenceReference, KnowledgeField, DatasetReference, PDFChunk, PDFParser, ChunkFilter, EvidenceReferenceValidator, EvidenceExtractor

## Context

This is the foundation layer for the evidence grounding system. All other modules depend on these data types and parsers. Implement in `agent/evidence/`.

## Files to Create

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
    def parse(self, paper_id: str, pdf_path: str) -> list[PDFChunk]

class ChunkFilter:
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

### `agent/evidence/evidence_extractor.py`
```python
class EvidenceReferenceValidator:
    def validate(self, ref: EvidenceReference, chunks: list[PDFChunk]) -> bool
    def validate_all(self, refs: list[EvidenceReference], chunks: list[PDFChunk]) -> list[EvidenceReference]

class EvidenceExtractor:
    def __init__(self, llm: LLMBase, chunk_filter: ChunkFilter | None = None)
    def extract(self, chunks: list[PDFChunk]) -> list[EvidenceReference]
```

## Requirements

1. **EvidenceReferenceValidator rules:**
   - Excerpt match (multi-chunk): extracted excerpt must be a substring of at least one source chunk (whitespace-normalized)
   - Page range: page_number must be valid for the paper. Accept -1 for unknown page numbers.
   - Source type consistency: "table" type requires a non-empty table_id; "figure" type requires a non-empty table_id

2. **EvidenceExtractor** uses LLM to extract evidence from PDF chunks. Uses ChunkFilter to pre-filter chunks before LLM extraction. Evidence categories: architecture, benchmark, dataset, training, limitation.

3. **PDFParser** uses existing PdfDownload/PdfParse tools, splits by page boundaries, attempts section heading detection via heuristics.

4. **ChunkFilter** filters PDF chunks by evidence category using keyword heuristics.

## Testing

Add to `tests/test_evidence.py`:
- `test_evidence_reference` — EvidenceReference creation
- `test_evidence_reference_validator` — Validates excerpt against source chunk
- `test_evidence_reference_validator_rejects_fabricated` — Rejects excerpt not in source
- `test_knowledge_field` — KnowledgeField with evidence_refs
- `test_pdf_chunk` — PDFChunk creation
- `test_chunk_filter` — ChunkFilter filters by category keywords
- `test_evidence_extractor_empty` — No chunks → empty evidence
- `test_evidence_extractor_extracts` — MockLLM returns structured evidence

## Constraints

- No changes to existing `Claim`, `EvidenceStore`, `ClaimExtractor`, `ClaimVerifier` remain unchanged
- Use `from agent.core.llm import LLMBase, MockLLM` for LLM interactions
- All existing tests must pass
- UUID-based evidence_id generation