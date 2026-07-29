# Task 2: Stores — BenchmarkRecord, BenchmarkStore, PaperKnowledge, ArchitectureKnowledge, TrainingKnowledge, PaperKnowledgeBase

## Context

This task implements the data stores for the evidence grounding system. These are pure data layer components with no LLM dependencies. They depend on the data types from Task 1.

## Files to Create

### `agent/evidence/benchmark_store.py`
```python
@dataclass
class BenchmarkRecord:
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

## Requirements

1. **BenchmarkRecord** uses `uuid.uuid4().hex[:12]` for id generation (if not provided)
2. **BenchmarkStore** is an in-memory store (list-based, like EvidenceStore)
3. `mark_verified` returns count of updated records
4. `lookup` searches by benchmark_name (and optionally model_name)
5. **PaperKnowledgeBase** stores PaperKnowledge objects keyed by paper_id
6. Ownership boundaries: KnowledgeField has its own evidence_refs, PaperKnowledge.evidence_refs is paper-level only

## Testing

Add to `tests/test_evidence.py`:
- `test_benchmark_record` — BenchmarkRecord creation and field defaults
- `test_benchmark_store_add_and_retrieve` — Add records, retrieve by model, lookup
- `test_benchmark_store_mark_verified` — Mark records as verified by ID
- `test_benchmark_store_clear` — Clear resets store
- `test_paper_knowledge` — PaperKnowledge creation with structured fields
- `test_paper_knowledge_base` — Add, get by paper_id, clear

## Key Pattern to Follow
- EvidenceStore is the pattern for BenchmarkStore (in-memory list-based store)
- Tests use class-based organization (TestBenchmarkStore, TestPaperKnowledgeBase, etc.)
- Import from `agent.evidence.evidence_reference import EvidenceReference, KnowledgeField, DatasetReference`