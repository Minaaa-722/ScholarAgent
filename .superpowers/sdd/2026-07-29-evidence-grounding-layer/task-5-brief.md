# Task 5: Enhanced EvidenceChecker — 3-store Validation

## Context

Enhance the existing EvidenceChecker to read from all three stores (EvidenceStore, BenchmarkStore, PaperKnowledgeBase) for multi-dimensional validation.

## Dependencies

- `agent.evidence.evidence_store` — EvidenceStore, Claim
- `agent.evidence.benchmark_store` — BenchmarkStore, BenchmarkRecord
- `agent.evidence.paper_knowledge` — PaperKnowledgeBase, PaperKnowledge
- `agent.evidence.checker` — Existing EvidenceChecker

## File to Modify

### `agent/evidence/checker.py` — Enhanced EvidenceChecker

Current constructor:
```python
class EvidenceChecker(Validator):
    def __init__(
        self,
        evidence_store: EvidenceStore,
        llm: Optional[LLMBase] = None,
    )
```

New constructor:
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

## New Checks

| Check | Source | Detection |
|---|---|---|
| Unsupported claim | EvidenceStore | Claim not in verified claims |
| Benchmark mismatch | BenchmarkStore | Benchmark number in draft ≠ stored record |
| Missing benchmark | BenchmarkStore | Benchmark name in draft but no record |
| Model inconsistency | PaperKnowledgeBase | Architecture/training details contradict stored knowledge |
| Missing evidence | All stores | Strong technical claim with no evidence reference |

## Requirements

1. Constructor takes `benchmark_store` and `knowledge_base` as new required params
2. `validate()` method checks all three stores
3. Benchmark mismatch detection: extract benchmark numbers from draft, compare against verified records
4. Model inconsistency detection: extract architecture claims, compare against PaperKnowledgeBase
5. Missing evidence detection: flag strong claims with no evidence reference
6. All existing checker tests must pass with the new constructor signature
7. Backward compatibility: update all callers (harness.py, pipeline.py)

## Testing

Add to `tests/test_evidence.py`:
- `test_evidence_checker_benchmark_mismatch` — Detects benchmark number inconsistency
- `test_evidence_checker_model_inconsistency` — Detects architecture description mismatch
- `test_evidence_checker_missing_evidence` — Detects strong claim with no evidence
- `test_evidence_checker_all_three_stores` — Full checker flow with all stores

Modify existing tests:
- Update `EvidenceChecker` instantiation to pass `benchmark_store=BenchmarkStore()`, `knowledge_base=PaperKnowledgeBase()`