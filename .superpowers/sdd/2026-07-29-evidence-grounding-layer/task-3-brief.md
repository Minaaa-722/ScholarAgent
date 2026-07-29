# Task 3: Extractors — BenchmarkExtractor, BenchmarkVerifier, PaperAnalyzer

## Context

These extractors consume EvidenceReference objects from Task 1 and produce structured records for the stores from Task 2. They use LLM for extraction but do NOT create evidence — they organize and validate.

## Dependencies

- `agent.evidence.evidence_reference` — EvidenceReference
- `agent.evidence.benchmark_store` — BenchmarkRecord, BenchmarkStore
- `agent.evidence.paper_knowledge` — PaperKnowledge, PaperKnowledgeBase
- `agent.core.llm` — LLMBase, MockLLM

## Files to Create

### `agent/evidence/benchmark_extractor.py`

```python
class BenchmarkExtractor:
    """Extracts structured BenchmarkRecord from EvidenceReference objects.
    Takes already-extracted evidence references and identifies benchmark
    results within them. Uses LLM to parse benchmark numbers, metrics,
    and model names from evidence excerpts.
    """
    def __init__(self, llm: LLMBase)
    def extract(self, evidence_refs: list[EvidenceReference]) -> list[BenchmarkRecord]

class BenchmarkVerifier:
    """Verifies benchmark records against source evidence and paper metadata.
    A benchmark record is considered verified when:
    1. Its EvidenceReference passed validation (exists in source PDF)
    2. Semantic consistency: model_name, benchmark_name, and score/metric
       all appear in the evidence excerpt
    3. The score is internally consistent (no obviously impossible values)
    4. The model_name can be plausibly linked to the paper
    """
    def __init__(self, llm: LLMBase | None = None)
    def verify(self, records: list[BenchmarkRecord], papers: list[dict]) -> list[str]  # Returns record IDs that passed
    def verify_record(self, record: BenchmarkRecord, paper: dict | None = None) -> bool
```

### `agent/evidence/paper_analyzer.py`

```python
class PaperAnalyzer:
    """Extracts structured PaperKnowledge from EvidenceReference objects.
    Takes already-extracted evidence references and organizes them into
    structured per-paper knowledge. Each KnowledgeField gets its own
    evidence_refs for traceability.
    """
    def __init__(self, llm: LLMBase)
    def analyze(self, evidence_refs: list[EvidenceReference]) -> list[PaperKnowledge]
```

## Requirements

1. **BenchmarkExtractor** uses LLM with focused prompts to parse benchmark results from evidence excerpts
2. **BenchmarkVerifier** checks semantic consistency: model_name, benchmark_name, score all appear in source excerpt
3. **PaperAnalyzer** organizes evidence into structured PaperKnowledge with per-field evidence_refs
4. All extractors use LLM prompts that instruct the model to organize but NOT create evidence
5. Use MockLLM for testing

## Testing

Add to `tests/test_evidence.py`:
- `test_benchmark_extractor_extracts` — MockLLM returns structured records
- `test_benchmark_verifier` — Verifies records against paper metadata
- `test_benchmark_verifier_verification_lifecycle` — Unverified → verified transition
- `test_paper_analyzer_analyzes` — MockLLM returns structured knowledge