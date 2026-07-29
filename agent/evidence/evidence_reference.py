"""Evidence reference data types for the evidence grounding layer.

Provides unified source traceability objects for linking extracted
evidence back to specific PDF pages, sections, and source types.
"""

import uuid
from dataclasses import dataclass, field

from agent.evidence.paper_types import EvidenceLevel


@dataclass
class EvidenceReference:
    """Unified source traceability object.

    Links an evidence excerpt back to its source paper, page, section,
    and source type (text, table, figure).
    """

    evidence_id: str = ""
    paper_id: str = ""
    page_number: int = -1
    section: str = ""
    source_type: str = ""  # "text", "table", "figure"
    table_id: str = ""
    excerpt: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.NONE

    def __post_init__(self) -> None:
        """Auto-generate evidence_id if not provided."""
        if not self.evidence_id:
            self.evidence_id = uuid.uuid4().hex[:12]


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