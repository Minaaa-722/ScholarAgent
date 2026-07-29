"""Paper validation data types for the evidence grounding layer.

Provides enums and dataclasses for paper availability, evidence level,
claim type constraints, and evidence source tracking.
"""

from dataclasses import dataclass, field
from enum import Enum


class PaperStatus(Enum):
    """Status of a paper after validation."""
    AVAILABLE = "AVAILABLE"
    PDF_AVAILABLE = "PDF_AVAILABLE"
    PDF_UNAVAILABLE = "PDF_UNAVAILABLE"
    WITHDRAWN = "WITHDRAWN"
    RETRACTED = "RETRACTED"
    UNKNOWN = "UNKNOWN"


class EvidenceLevel(Enum):
    """Level of evidence available for a paper or claim.

    Ordered from lowest (NONE) to highest (FULL_TEXT).
    Comparison operators enable >= checks.
    """
    NONE = 0
    METADATA = 1
    ABSTRACT = 2
    HTML = 3
    FULL_TEXT = 4

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented


class ClaimType(Enum):
    """Type of claim extracted from evidence.

    Each type has a minimum evidence level requirement
    (see MIN_EVIDENCE_LEVEL).
    """
    PAPER_DESCRIPTION = "paper_description"
    ARCHITECTURE = "architecture"
    TRAINING_DETAIL = "training_detail"
    BENCHMARK_RESULT = "benchmark_result"
    LIMITATION = "limitation"


# Minimum evidence level required per claim type.
# Claims below this level are removed before writing.
MIN_EVIDENCE_LEVEL: dict[ClaimType, EvidenceLevel] = {
    ClaimType.PAPER_DESCRIPTION: EvidenceLevel.ABSTRACT,
    ClaimType.ARCHITECTURE: EvidenceLevel.HTML,
    ClaimType.TRAINING_DETAIL: EvidenceLevel.FULL_TEXT,
    ClaimType.BENCHMARK_RESULT: EvidenceLevel.FULL_TEXT,
    ClaimType.LIMITATION: EvidenceLevel.ABSTRACT,
}


@dataclass
class PaperAvailability:
    """Validation result for a single paper.

    Attributes:
        paper_id: Unique paper identifier.
        metadata_available: Whether paper metadata was found.
        abstract_available: Whether the abstract is accessible.
        fulltext_available: Whether full text (PDF) is accessible.
        status: PaperStatus enum value.
        reason: Human-readable reason for the status.
        evidence_level: Computed evidence level based on availability.
    """
    paper_id: str = ""
    metadata_available: bool = False
    abstract_available: bool = False
    fulltext_available: bool = False
    status: PaperStatus = PaperStatus.UNKNOWN
    reason: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.NONE


@dataclass
class EvidenceSource:
    """Result of evidence acquisition for a single paper.

    Attributes:
        paper_id: Unique paper identifier.
        source_type: Source type ("PDF", "HTML", "ABSTRACT", "METADATA", "NONE").
        content: The acquired content (full text, abstract, or empty).
        evidence_level: Evidence level of the acquired source.
    """
    paper_id: str = ""
    source_type: str = ""
    content: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.NONE