# Task 4: Retriever — EvidenceRanker, SimpleRanker, ContextRetriever, EvidenceContext, EvidenceContextBuilder

## Context

The ContextRetriever selects relevant evidence for the writing stage from all three stores. The EvidenceContextBuilder formats it into a text block.

## Dependencies

- `agent.evidence.evidence_store` — EvidenceStore, Claim
- `agent.evidence.benchmark_store` — BenchmarkStore, BenchmarkRecord
- `agent.evidence.paper_knowledge` — PaperKnowledgeBase, PaperKnowledge
- `agent.evidence.evidence_reference` — EvidenceReference

## Files to Create

### `agent/evidence/context_retriever.py`

```python
class EvidenceRanker(ABC):
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
        return knowledge

@dataclass
class EvidenceContext:
    """Container for retrieved evidence (no formatting logic)."""
    claims: list[Claim] = field(default_factory=list)
    benchmarks: list[BenchmarkRecord] = field(default_factory=list)
    paper_knowledge: list[PaperKnowledge] = field(default_factory=list)

class ContextRetriever:
    """Selects relevant evidence for writing, controls top-k / token budget.
    Queries all three stores and selects evidence based on priority.
    Token budget enforcement:
    1. Rank: apply EvidenceRanker to sort evidence by priority
    2. Select: add evidence in priority order until max_context_tokens would be exceeded
    3. Preserve metadata: each selected item retains its paper_id, page_number, section, source_type
    4. Never truncate: if item exceeds remaining budget, skip it rather than truncating
    """
    def __init__(
        self,
        evidence_store: EvidenceStore,
        benchmark_store: BenchmarkStore,
        knowledge_base: PaperKnowledgeBase,
        max_context_tokens: int = 1000,
        ranker: EvidenceRanker | None = None,
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

## Requirements

1. **EvidenceRanker** is an abstract base class with ABC
2. **SimpleRanker** sorts verified claims first, then by confidence; verified benchmarks first
3. **ContextRetriever** queries all three stores, ranks, and selects within token budget
4. **EvidenceContextBuilder.format()** produces a human-readable text block with metadata
5. Token budget: approximate 1 token ≈ 4 characters for budget estimation
6. Never truncate item metadata to fit within budget — skip items that don't fit

## Testing

Add to `tests/test_evidence.py`:
- `test_evidence_ranker_simple` — SimpleRanker sorts verified first
- `test_context_retriever_empty` — No stores → empty context
- `test_context_retriever_with_data` — Retrieves from all three stores
- `test_evidence_context_builder_format` — Formats context with metadata