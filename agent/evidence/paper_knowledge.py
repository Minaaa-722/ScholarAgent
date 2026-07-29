"""Paper knowledge types and store for the evidence grounding layer.

Provides structured knowledge containers for paper-level information
about architecture, training, datasets, and benchmarks, with per-field
evidence traceability.
"""

from dataclasses import dataclass, field
from typing import Optional

from agent.evidence.evidence_reference import EvidenceReference, KnowledgeField, DatasetReference


@dataclass
class ArchitectureKnowledge:
    """Structured knowledge about a paper's model architecture.

    Each field carries its own evidence trail (KnowledgeField).
    """

    vision_encoder: KnowledgeField = field(default_factory=KnowledgeField)
    language_model: KnowledgeField = field(default_factory=KnowledgeField)
    connector: KnowledgeField = field(default_factory=KnowledgeField)
    fusion_method: KnowledgeField = field(default_factory=KnowledgeField)
    resolution_strategy: KnowledgeField = field(default_factory=KnowledgeField)


@dataclass
class TrainingKnowledge:
    """Structured knowledge about a paper's training setup.

    Each field carries its own evidence trail (KnowledgeField).
    """

    pretraining_dataset: KnowledgeField = field(default_factory=KnowledgeField)
    instruction_dataset: KnowledgeField = field(default_factory=KnowledgeField)
    optimization_method: KnowledgeField = field(default_factory=KnowledgeField)
    loss_function: KnowledgeField = field(default_factory=KnowledgeField)
    training_stage: KnowledgeField = field(default_factory=KnowledgeField)


@dataclass
class PaperKnowledge:
    """Aggregated knowledge extracted from a single paper.

    Combines high-level metadata (title, problem, motivation, contributions)
    with structured sub-objects for architecture and training knowledge,
    dataset references, benchmark links, and paper-level evidence references.

    Ownership boundaries:
    - KnowledgeField sub-objects (ArchitectureKnowledge, TrainingKnowledge)
      have their own evidence_refs at the field level.
    - PaperKnowledge.evidence_refs captures paper-level evidence only.
    """

    paper_id: str
    title: str = ""
    problem_definition: str = ""
    motivation: str = ""
    main_contribution: str = ""
    architecture: Optional[ArchitectureKnowledge] = None
    training: Optional[TrainingKnowledge] = None
    datasets: list[DatasetReference] = field(default_factory=list)
    benchmark_references: list[str] = field(default_factory=list)
    limitations: str = ""
    evidence_refs: list[EvidenceReference] = field(default_factory=list)


class PaperKnowledgeBase:
    """In-memory store for PaperKnowledge objects keyed by paper_id.

    Provides add, get, get_all, and clear operations.
    """

    def __init__(self) -> None:
        self._knowledge: dict[str, PaperKnowledge] = {}

    def add(self, knowledge: PaperKnowledge) -> None:
        """Add or replace a PaperKnowledge object keyed by paper_id."""
        self._knowledge[knowledge.paper_id] = knowledge

    def get(self, paper_id: str) -> Optional[PaperKnowledge]:
        """Retrieve a PaperKnowledge object by paper_id, or None."""
        return self._knowledge.get(paper_id)

    def get_all(self) -> list[PaperKnowledge]:
        """Get all stored PaperKnowledge objects."""
        return list(self._knowledge.values())

    def clear(self) -> None:
        """Reset the store (remove all knowledge entries)."""
        self._knowledge.clear()