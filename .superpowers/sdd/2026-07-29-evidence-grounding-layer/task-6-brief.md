# Task 6: Pipeline Integration — PipelineOrchestrator + Harness changes

## Context

Wire all the new components together into the pipeline. This is the final integration task.

## Dependencies

- All prior tasks must be complete
- `agent.core.pipeline` — PipelineOrchestrator
- `agent.core.harness` — Harness
- `agent.evidence.*` — All new modules
- `agent.evidence.checker` — Enhanced EvidenceChecker

## Files to Modify

### `agent/evidence/__init__.py` — Add new exports

Update to export all new classes:
```python
from agent.evidence.evidence_reference import EvidenceReference, KnowledgeField, DatasetReference
from agent.evidence.pdf_parser import PDFChunk, PDFParser, ChunkFilter
from agent.evidence.evidence_extractor import EvidenceExtractor, EvidenceReferenceValidator
from agent.evidence.benchmark_store import BenchmarkRecord, BenchmarkStore
from agent.evidence.benchmark_extractor import BenchmarkExtractor, BenchmarkVerifier
from agent.evidence.paper_knowledge import PaperKnowledge, ArchitectureKnowledge, TrainingKnowledge, PaperKnowledgeBase
from agent.evidence.paper_analyzer import PaperAnalyzer
from agent.evidence.context_retriever import EvidenceRanker, SimpleRanker, ContextRetriever, EvidenceContext, EvidenceContextBuilder
```

### `agent/core/pipeline.py` — PipelineOrchestrator changes

| Location | Change |
|---|---|
| `__init__()` | Add `_benchmark_store`, `_paper_knowledge_base`, `_benchmark_extractor`, `_paper_analyzer`, `_pdf_parser`, `_evidence_extractor`, `_pdf_chunks`, `_evidence_refs` |
| `run_pipeline()` | Call `clear()` on all three stores |
| `_retrieve_papers()` | After paper search, download PDFs, parse into chunks, extract evidence references |
| `_analyze_papers()` | Pass evidence references as context to LLM; after analysis, extract benchmarks and paper knowledge from evidence |
| `_write_survey()` | Use ContextRetriever + EvidenceContextBuilder instead of ClaimContextBuilder alone |

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

## Requirements

1. No new pipeline stages
2. No changes to AgentState, StateMachine
3. PDF download/parse happens in `_retrieve_papers()` context
4. Evidence extraction happens as part of RETRIEVAL stage
5. Benchmark extraction and paper knowledge extraction happen after analysis
6. ContextRetriever replaces ClaimContextBuilder in `_write_survey()`
7. All existing tests must pass
8. Error handling: PDF download failure → log warning, mark paper as evidence_unavailable
9. Error handling: empty stores → ContextRetriever returns empty context, writer proceeds without evidence

## Testing

Add to `tests/test_evidence.py`:
- `test_orchestrator_evidence_grounding_flow` — Full pipeline integration test