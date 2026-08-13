"""Citation anchor store for the evidence grounding layer.

Explicit mapping chain: Claim → Evidence → Paper → CitationKey.
Bridges the EvidenceStore and CitationStore so that the writing stage
can associate each claim with the correct BibTeX citation key.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from agent.evidence.citation_store import CitationStore
from agent.evidence.evidence_store import Claim
from agent.evidence.paper_knowledge import PaperKnowledgeBase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CitationAnchor
# ---------------------------------------------------------------------------

@dataclass
class CitationAnchor:
    """A single claim-to-citation linkage.

    Attributes:
        claim_text: The claim text (e.g., "Qwen2-VL uses dynamic resolution").
        category: One of "architecture", "benchmark", "dataset", "comparison".
        paper_id: Paper identifier (matches ``EvidenceReference.paper_id``).
        citation_key: Resolved BibTeX citation key from ``CitationStore``.
        confidence: 0.0–1.0 confidence in the claim extraction.
        evidence_excerpt: Brief supporting excerpt from the source paper.
    """

    claim_text: str
    category: str
    paper_id: str
    citation_key: str
    confidence: float = 0.0
    evidence_excerpt: str = ""


# ---------------------------------------------------------------------------
# CitationAnchorStore
# ---------------------------------------------------------------------------

class CitationAnchorStore:
    """Maintains the mapping chain: Claim → Evidence → Paper → CitationKey.

    Built from verified claims in ``EvidenceStore`` and the ``CitationStore``
    lookup tables.  Provides category-based queries and an evidence map for
    the ``EvidenceContextBuilder`` to include citation anchor information.

    Typical usage::

        store = CitationAnchorStore()
        store.build(verified_claims, citation_store, knowledge_base)
        anchors = store.get_anchors()
        anchor = store.get_anchor_for_claim("Qwen2-VL uses dynamic resolution")
        evidence_map = store.get_evidence_map()
    """

    def __init__(self) -> None:
        self._anchors: list[CitationAnchor] = []
        # claim_text_lower → list of citation keys
        self._evidence_map: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        claims: list[Claim],
        citation_store: CitationStore,
        paper_knowledge_base: Optional[PaperKnowledgeBase] = None,
    ) -> None:
        """Build anchors from verified claims and the CitationStore.

        For each claim:
          1. Get ``paper_id`` from ``Claim.paper_id``.
          2. Resolve ``paper_id → citation_key`` via ``CitationStore``.
          3. Optionally enrich with model name from ``PaperKnowledgeBase``.
          4. Create a ``CitationAnchor``.

        Args:
            claims: Verified claims from ``EvidenceStore.get_verified_claims()``.
            citation_store: Populated ``CitationStore`` instance.
            paper_knowledge_base: Optional ``PaperKnowledgeBase`` for enrichment.
        """
        self._anchors.clear()
        self._evidence_map.clear()

        for claim in claims:
            paper_id = claim.paper_id
            if not paper_id:
                logger.debug(
                    "Skipping claim '%s' — no paper_id", claim.claim[:60]
                )
                continue

            # Resolve paper_id → citation_key
            entry = citation_store.lookup_by_paper_id(paper_id)
            if not entry:
                # Try resolving via model alias as fallback
                model_name = self._guess_model_name(claim, paper_knowledge_base)
                if model_name:
                    entries = citation_store.lookup_by_model(model_name)
                    if entries:
                        entry = entries[0]

            if not entry:
                logger.warning(
                    "No citation entry found for paper_id '%s' (claim: %s)",
                    paper_id, claim.claim[:60],
                )
                continue

            citation_key = entry.citation_key

            # Build anchor
            anchor = CitationAnchor(
                claim_text=claim.claim,
                category=claim.category,
                paper_id=paper_id,
                citation_key=citation_key,
                confidence=claim.confidence,
                evidence_excerpt=claim.source_excerpt[:200] if claim.source_excerpt else "",
            )
            self._anchors.append(anchor)

            # Update evidence map
            key = claim.claim.strip().lower()
            if key not in self._evidence_map:
                self._evidence_map[key] = []
            if citation_key not in self._evidence_map[key]:
                self._evidence_map[key].append(citation_key)

        logger.info(
            "Built %d citation anchors from %d claims",
            len(self._anchors), len(claims),
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_anchors(self) -> list[CitationAnchor]:
        """Return all citation anchors."""
        return list(self._anchors)

    def get_anchors_by_category(self, category: str) -> list[CitationAnchor]:
        """Return anchors filtered by category.

        Args:
            category: One of ``"architecture"``, ``"benchmark"``,
                      ``"dataset"``, ``"comparison"``.

        Returns:
            Matching anchors (empty list if none match).
        """
        return [a for a in self._anchors if a.category == category]

    def get_evidence_map(self) -> dict[str, list[str]]:
        """Return the claim_text → [citation_key, ...] mapping.

        Used by ``EvidenceContextBuilder`` to include citation anchor
        information in the context sent to the writer.
        """
        return dict(self._evidence_map)

    def get_anchor_for_claim(self, claim_text: str) -> Optional[CitationAnchor]:
        """Look up a single anchor by claim text (case-insensitive).

        Args:
            claim_text: The claim text to search for.

        Returns:
            The matching ``CitationAnchor``, or ``None``.
        """
        target = claim_text.strip().lower()
        for anchor in self._anchors:
            if anchor.claim_text.strip().lower() == target:
                return anchor
        return None

    def anchor_count(self) -> int:
        """Return the number of anchors."""
        return len(self._anchors)

    def clear(self) -> None:
        """Reset the store."""
        self._anchors.clear()
        self._evidence_map.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guess_model_name(
        claim: Claim,
        knowledge_base: Optional[PaperKnowledgeBase],
    ) -> str:
        """Try to guess a model name from the claim or knowledge base.

        Returns an empty string if no model name can be guessed.
        """
        if not knowledge_base:
            return ""

        pk = knowledge_base.get(claim.paper_id)
        if not pk:
            return ""

        # Try the title prefix (e.g., "Qwen2-VL: ...")
        if ":" in pk.title:
            prefix = pk.title.split(":", 1)[0].strip()
            if prefix and len(prefix) >= 2:
                return prefix

        # Try architecture fields
        if pk.architecture:
            for field_name in ("vision_encoder", "language_model"):
                val = getattr(pk.architecture, field_name, None)
                if val and val.value and len(val.value) >= 2:
                    return val.value

        return ""
