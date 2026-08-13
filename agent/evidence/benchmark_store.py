"""Benchmark record and store for the evidence grounding layer.

Provides structured storage for benchmark evaluation records, supporting
verification workflows and lookup by model/benchmark name.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from agent.evidence.evidence_reference import EvidenceReference


@dataclass
class BenchmarkRecord:
    """A single benchmark evaluation result.

    Attributes:
        id: Unique identifier (auto-generated via uuid hex prefix if not provided).
        model_name: Name of the model being evaluated.
        benchmark_name: Name of the benchmark (e.g., "MMLU", "MathVista").
        metric: The specific metric name (e.g., "accuracy", "pass@1").
        score: Score value as a string (e.g., "85.3", "4.5/5", "83.2 (+2.4)").
        score_unit: Unit for the score (default "%").
        split: Dataset split (e.g., "test", "val", "zero-shot").
        source: EvidenceReference providing traceability to the source paper.
        verified: Whether this record has been cross-checked.
    """

    id: str = ""
    model_name: str = ""
    benchmark_name: str = ""
    metric: str = ""
    score: str = ""
    score_unit: str = "%"
    split: str = ""
    citation_key: str = ""
    source: EvidenceReference = field(default_factory=EvidenceReference)
    verified: bool = False

    def __post_init__(self) -> None:
        """Auto-generate a short id if not provided."""
        if not self.id:
            self.id = uuid.uuid4().hex[:12]


class BenchmarkStore:
    """In-memory store for BenchmarkRecord objects.

    Pipeline-scoped store that supports adding, retrieving, filtering,
    and verifying benchmark records.
    """

    def __init__(self) -> None:
        self._records: list[BenchmarkRecord] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_records(self, records: list[BenchmarkRecord]) -> None:
        """Batch insert new benchmark records."""
        self._records.extend(records)

    def mark_verified(self, record_ids: list[str]) -> int:
        """Mark records whose id matches any entry in record_ids as verified.

        Returns the number of records updated.
        """
        targets = set(record_ids)
        count = 0
        for r in self._records:
            if r.id in targets and not r.verified:
                r.verified = True
                count += 1
        return count

    def clear(self) -> None:
        """Reset the store (remove all records)."""
        self._records.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self) -> list[BenchmarkRecord]:
        """Get all benchmark records."""
        return list(self._records)

    def get_verified(self, benchmark_name: Optional[str] = None) -> list[BenchmarkRecord]:
        """Get verified records, optionally filtered by benchmark name."""
        result = [r for r in self._records if r.verified]
        if benchmark_name:
            result = [r for r in result if r.benchmark_name == benchmark_name]
        return result

    def get_by_model(self, model_name: str) -> list[BenchmarkRecord]:
        """Get all records for a specific model."""
        return [r for r in self._records if r.model_name == model_name]

    def lookup(
        self, benchmark_name: str, model_name: Optional[str] = None
    ) -> list[BenchmarkRecord]:
        """Lookup records by benchmark name, optionally filtered by model name."""
        result = [r for r in self._records if r.benchmark_name == benchmark_name]
        if model_name:
            result = [r for r in result if r.model_name == model_name]
        return result

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def record_count(self) -> int:
        """Total number of records in the store."""
        return len(self._records)

    def verified_count(self) -> int:
        """Number of verified records."""
        return sum(1 for r in self._records if r.verified)
