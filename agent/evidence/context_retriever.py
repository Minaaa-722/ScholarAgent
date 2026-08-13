"""Evidence retriever, ranker, and context builder for the evidence grounding layer.

Provides:
- EvidenceRanker (ABC) / SimpleRanker: prioritise evidence by quality.
- EvidenceContext (dataclass): container for retrieved evidence.
- ContextRetriever: queries all three stores, ranks, and selects within a token budget.
- EvidenceContextBuilder: formats EvidenceContext into a text block for the writer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from agent.evidence.benchmark_store import BenchmarkRecord, BenchmarkStore
from agent.evidence.evidence_store import Claim, EvidenceStore
from agent.evidence.paper_knowledge import PaperKnowledge, PaperKnowledgeBase


# ---------------------------------------------------------------------------
# Ranker
# ---------------------------------------------------------------------------

class EvidenceRanker(ABC):
    """Abstract base class for evidence ranking strategies."""

    @abstractmethod
    def rank_claims(self, claims: list[Claim]) -> list[Claim]:
        """Sort claims by priority (highest quality first)."""
        ...

    @abstractmethod
    def rank_benchmarks(self, records: list[BenchmarkRecord]) -> list[BenchmarkRecord]:
        """Sort benchmark records by priority."""
        ...

    @abstractmethod
    def rank_knowledge(self, knowledge: list[PaperKnowledge]) -> list[PaperKnowledge]:
        """Sort paper knowledge entries by priority."""
        ...


class SimpleRanker(EvidenceRanker):
    """Phase 1 default: verified first, then by confidence for claims.

    - Claims: verified ``True`` sorts before ``False``; within the same
      verification status, higher confidence comes first.
    - Benchmarks: verified records first.
    - Knowledge: returned as-is (no prioritisation).
    """

    def rank_claims(self, claims: list[Claim]) -> list[Claim]:
        return sorted(claims, key=lambda c: (c.verified, c.confidence), reverse=True)

    def rank_benchmarks(self, records: list[BenchmarkRecord]) -> list[BenchmarkRecord]:
        return sorted(records, key=lambda r: r.verified, reverse=True)

    def rank_knowledge(self, knowledge: list[PaperKnowledge]) -> list[PaperKnowledge]:
        return knowledge


# ---------------------------------------------------------------------------
# Context container
# ---------------------------------------------------------------------------

@dataclass
class EvidenceContext:
    """Container for retrieved evidence (no formatting logic).

    Attributes:
        claims: Selected claims in priority order.
        benchmarks: Selected benchmark records in priority order.
        paper_knowledge: Selected paper knowledge entries in priority order.
    """

    claims: list[Claim] = field(default_factory=list)
    benchmarks: list[BenchmarkRecord] = field(default_factory=list)
    paper_knowledge: list[PaperKnowledge] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4


class ContextRetriever:
    """Selects relevant evidence for writing, controlling top-k / token budget.

    Queries all three stores and selects evidence based on priority ranking.
    Token budget enforcement:
    1. **Rank** — apply the ``EvidenceRanker`` to sort evidence by priority.
    2. **Select** — add evidence in priority order until ``max_context_tokens``
       would be exceeded (approximate 1 token ≈ 4 characters).
    3. **Preserve metadata** — each selected item retains its ``paper_id``,
       ``page_number``, ``section``, ``source_type``.
    4. **Never truncate** — if an item exceeds the remaining budget, skip it
       rather than truncating its content.
    """

    def __init__(
        self,
        evidence_store: EvidenceStore,
        benchmark_store: BenchmarkStore,
        knowledge_base: PaperKnowledgeBase,
        max_context_tokens: int = 1000,
        ranker: Optional[EvidenceRanker] = None,
    ) -> None:
        self._evidence_store = evidence_store
        self._benchmark_store = benchmark_store
        self._knowledge_base = knowledge_base
        self._max_context_tokens = max_context_tokens
        self._ranker = ranker or SimpleRanker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_for_section(
        self,
        section_title: str = "",
        paper_ids: Optional[list[str]] = None,
        category: str = "",
    ) -> EvidenceContext:
        """Retrieve, rank, and select evidence within the token budget.

        Parameters
        ----------
        section_title:
            Section heading (reserved for future semantic filtering).
        paper_ids:
            If provided, only return evidence linked to these papers.
        category:
            If provided, only return claims matching this category.

        Returns
        -------
        EvidenceContext with lists capped by ``max_context_tokens``.
        """
        # 1. Query all three stores -------------------------------------------
        all_claims = self._evidence_store.get_all_claims()
        all_benchmarks = self._benchmark_store.get_all()
        all_knowledge = self._knowledge_base.get_all()

        # 2. Apply filters ----------------------------------------------------
        if paper_ids:
            pid_set = set(paper_ids)
            all_claims = [c for c in all_claims if c.paper_id in pid_set]

            # Benchmarks store model_name, not paper_id — filter via source
            all_benchmarks = [
                b for b in all_benchmarks
                if b.source and b.source.paper_id in pid_set
            ]

            all_knowledge = [k for k in all_knowledge if k.paper_id in pid_set]

        if category:
            all_claims = [c for c in all_claims if c.category == category]

        # 3. Rank -------------------------------------------------------------
        ranked_claims = self._ranker.rank_claims(all_claims)
        ranked_benchmarks = self._ranker.rank_benchmarks(all_benchmarks)
        ranked_knowledge = self._ranker.rank_knowledge(all_knowledge)

        # 4. Select within token budget ---------------------------------------
        char_budget = self._max_context_tokens * _CHARS_PER_TOKEN

        selected_claims = self._select_within_budget(
            ranked_claims, char_budget, _claim_char_count
        )
        selected_benchmarks = self._select_within_budget(
            ranked_benchmarks, char_budget, _benchmark_char_count
        )
        selected_knowledge = self._select_within_budget(
            ranked_knowledge, char_budget, _knowledge_char_count
        )

        return EvidenceContext(
            claims=selected_claims,
            benchmarks=selected_benchmarks,
            paper_knowledge=selected_knowledge,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _select_within_budget(
        items: list,
        char_budget: int,
        char_count_fn,
    ) -> list:
        """Select items in order until *char_budget* would be exceeded.

        Items whose character count exceeds the remaining budget are silently
        skipped (never truncated).
        """
        selected: list = []
        remaining = char_budget
        for item in items:
            needed = char_count_fn(item)
            if needed > remaining:
                continue  # skip — never truncate
            selected.append(item)
            remaining -= needed
        return selected


# ---------------------------------------------------------------------------
# Character-count helpers (used by ContextRetriever)
# ---------------------------------------------------------------------------

def _claim_char_count(claim: Claim) -> int:
    """Estimate the on-screen character length of a Claim."""
    return (
        len(claim.claim)
        + len(claim.category)
        + len(claim.paper_id)
        + len(claim.source_excerpt)
        + 30  # overhead for labels, brackets, newlines
    )


def _benchmark_char_count(record: BenchmarkRecord) -> int:
    """Estimate the on-screen character length of a BenchmarkRecord."""
    return (
        len(record.model_name)
        + len(record.benchmark_name)
        + len(record.metric)
        + len(record.score)
        + len(record.score_unit)
        + len(record.split)
        + (len(record.source.excerpt) if record.source else 0)
        + 40  # overhead for labels, brackets, newlines
    )


def _knowledge_char_count(knowledge: PaperKnowledge) -> int:
    """Estimate the on-screen character length of a PaperKnowledge entry."""
    total = (
        len(knowledge.paper_id)
        + len(knowledge.title)
        + len(knowledge.problem_definition)
        + len(knowledge.motivation)
        + len(knowledge.main_contribution)
        + len(knowledge.limitations)
        + 60  # overhead
    )
    # Add architecture fields
    if knowledge.architecture:
        for field_name in (
            "vision_encoder",
            "language_model",
            "connector",
            "fusion_method",
            "resolution_strategy",
        ):
            val = getattr(knowledge.architecture, field_name, None)
            if val and val.value:
                total += len(val.value)
    # Add training fields
    if knowledge.training:
        for field_name in (
            "pretraining_dataset",
            "instruction_dataset",
            "optimization_method",
            "loss_function",
            "training_stage",
        ):
            val = getattr(knowledge.training, field_name, None)
            if val and val.value:
                total += len(val.value)
    # Datasets
    for ds in knowledge.datasets:
        total += len(ds.name) + 10
    # Benchmark references
    for br in knowledge.benchmark_references:
        total += len(br) + 5
    return total


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

class EvidenceContextBuilder:
    """Formats ``EvidenceContext`` into a text block for the writer.

    Preserves metadata (``paper_id``, ``page_number``, ``section``) in the
    output.  No retrieval logic — only formatting.
    """

    @classmethod
    def format(cls, context: EvidenceContext) -> str:
        """Produce a human-readable text block from the evidence context.

        Returns an empty string if the context is empty.
        """
        if not context.claims and not context.benchmarks and not context.paper_knowledge:
            return ""

        parts: list[str] = []
        parts.append("=== Evidence Context ===")

        # -- Claims -----------------------------------------------------------
        if context.claims:
            parts.append("")
            parts.append("--- Claims ---")
            for c in context.claims:
                meta_parts = []
                if c.paper_id:
                    meta_parts.append(f"paper={c.paper_id}")
                meta_parts.append(f"category={c.category}")
                if c.verified:
                    meta_parts.append("verified")
                meta_parts.append(f"confidence={c.confidence:.2f}")
                meta_str = " | ".join(meta_parts)
                parts.append(f"  [{meta_str}] {c.claim}")
                if c.source_excerpt:
                    parts.append(f"    Source: {c.source_excerpt[:200]}")

        # -- Benchmarks -------------------------------------------------------
        if context.benchmarks:
            parts.append("")
            parts.append("--- Benchmark Results ---")
            for b in context.benchmarks:
                meta_parts = []
                if b.source and b.source.paper_id:
                    meta_parts.append(f"paper={b.source.paper_id}")
                if b.source and b.source.page_number >= 0:
                    meta_parts.append(f"page={b.source.page_number}")
                if b.source and b.source.section:
                    meta_parts.append(f"section={b.source.section}")
                if b.verified:
                    meta_parts.append("verified")
                meta_str = " | ".join(meta_parts)
                score_str = f"{b.score}{b.score_unit}" if b.score_unit else b.score
                parts.append(
                    f"  [{meta_str}] {b.model_name} | {b.benchmark_name} | "
                    f"{b.metric}: {score_str}"
                )
                if b.split:
                    parts.append(f"    Split: {b.split}")
                if b.source and b.source.excerpt:
                    parts.append(f"    Source: {b.source.excerpt[:200]}")

        # -- Paper Knowledge --------------------------------------------------
        if context.paper_knowledge:
            parts.append("")
            parts.append("--- Paper Knowledge ---")
            for pk in context.paper_knowledge:
                meta_parts = [f"paper={pk.paper_id}"]
                meta_str = " | ".join(meta_parts)
                parts.append(f"  [{meta_str}] {pk.title}")
                if pk.main_contribution:
                    parts.append(f"    Contribution: {pk.main_contribution}")
                if pk.problem_definition:
                    parts.append(f"    Problem: {pk.problem_definition}")
                if pk.motivation:
                    parts.append(f"    Motivation: {pk.motivation}")

                # Architecture
                if pk.architecture:
                    arch_fields = []
                    for field_name in (
                        "vision_encoder",
                        "language_model",
                        "connector",
                        "fusion_method",
                        "resolution_strategy",
                    ):
                        val = getattr(pk.architecture, field_name, None)
                        if val and val.value:
                            arch_fields.append(f"{field_name}: {val.value}")
                    if arch_fields:
                        parts.append(f"    Architecture: {', '.join(arch_fields)}")

                # Training
                if pk.training:
                    train_fields = []
                    for field_name in (
                        "pretraining_dataset",
                        "instruction_dataset",
                        "optimization_method",
                        "loss_function",
                        "training_stage",
                    ):
                        val = getattr(pk.training, field_name, None)
                        if val and val.value:
                            train_fields.append(f"{field_name}: {val.value}")
                    if train_fields:
                        parts.append(f"    Training: {', '.join(train_fields)}")

                # Datasets
                if pk.datasets:
                    ds_names = [ds.name for ds in pk.datasets if ds.name]
                    if ds_names:
                        parts.append(f"    Datasets: {', '.join(ds_names)}")

                # Benchmark references
                if pk.benchmark_references:
                    parts.append(
                        f"    Benchmarks: {', '.join(pk.benchmark_references)}"
                    )

                if pk.limitations:
                    parts.append(f"    Limitations: {pk.limitations}")

        parts.append("")
        parts.append("=== End Evidence Context ===")
        return "\n".join(parts)
