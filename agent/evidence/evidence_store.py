from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Claim:
    """A single technical claim extracted from paper analysis.

    Attributes:
        claim: The technical claim text (e.g., "Qwen2-VL uses dynamic resolution").
        category: One of "architecture", "dataset", "benchmark", "comparison".
        paper_id: Paper identifier (e.g., "qwen2024").
        confidence: 0.0–1.0 confidence in the extraction.
        verified: Whether this claim has been cross-checked against paper source.
        source_excerpt: Brief supporting excerpt from the paper.
    """
    claim: str
    category: str = "architecture"
    paper_id: str = ""
    confidence: float = 0.0
    verified: bool = False
    source_excerpt: str = ""

    VALID_CATEGORIES = frozenset({"architecture", "dataset", "benchmark", "comparison"})

    def __post_init__(self):
        if self.category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_CATEGORIES))}"
            )
        self.confidence = max(0.0, min(1.0, self.confidence))


class EvidenceStore:
    """Pipeline-scoped store for extracted and verified claims.

    Owned by PipelineOrchestrator as a member variable.  Provides read/write
    access for the extraction, verification, and validation stages.
    """

    def __init__(self):
        self._claims: list[Claim] = []

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def add_claims(self, claims: list[Claim]) -> None:
        """Batch insert new claims."""
        self._claims.extend(claims)

    def mark_verified(self, claim_texts: list[str]) -> int:
        """Mark claims whose claim text matches any entry as verified.

        Returns the number of claims updated.
        """
        count = 0
        targets = {t.strip().lower() for t in claim_texts}
        for c in self._claims:
            if c.claim.strip().lower() in targets and not c.verified:
                c.verified = True
                count += 1
        return count

    def clear(self) -> None:
        """Reset the store (called at pipeline start)."""
        self._claims.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_all_claims(self) -> list[Claim]:
        """Get all claims."""
        return list(self._claims)

    def get_verified_claims(self, category: Optional[str] = None) -> list[Claim]:
        """Get verified claims, optionally filtered by category."""
        result = [c for c in self._claims if c.verified]
        if category:
            result = [c for c in result if c.category == category]
        return result

    def get_unverified_claims(self) -> list[Claim]:
        """Get claims not yet verified."""
        return [c for c in self._claims if not c.verified]

    def get_claims_by_category(self) -> dict[str, list[Claim]]:
        """Group all claims by category."""
        groups: dict[str, list[Claim]] = {}
        for c in self._claims:
            groups.setdefault(c.category, []).append(c)
        return groups

    def get_claims_for_paper(self, paper_id: str) -> list[Claim]:
        """Get claims linked to a specific paper."""
        return [c for c in self._claims if c.paper_id == paper_id]

    def claim_count(self) -> int:
        """Total number of claims in the store."""
        return len(self._claims)

    def verified_count(self) -> int:
        """Number of verified claims."""
        return sum(1 for c in self._claims if c.verified)


class ClaimContextBuilder:
    """Builds a compressed, section-relevant evidence context for the WRITING stage.

    Retrieves verified claims from EvidenceStore and formats them as a
    token-efficient text block (~300 tokens max) for injection into the
    user prompt of _write_survey().
    """

    # Maximum characters for the compressed context (roughly 300 tokens)
    _MAX_CONTEXT_CHARS = 1200

    @classmethod
    def build(cls, store: EvidenceStore) -> str:
        """Build a compressed evidence context string from verified claims.

        Returns an empty string if no verified claims are available.
        """
        claims = store.get_verified_claims()
        if not claims:
            return ""

        lines: list[str] = []
        lines.append("=== Evidence Context ===")

        # Group by category for readability
        by_category: dict[str, list[str]] = {}
        for c in claims:
            by_category.setdefault(c.category, []).append(c.claim)

        char_budget = cls._MAX_CONTEXT_CHARS - len("=== Evidence Context ===") - len("=== End Evidence Context ===")

        for cat in ["architecture", "dataset", "benchmark", "comparison"]:
            if cat not in by_category:
                continue
            cat_lines = by_category[cat]
            # Limit per category to avoid one category dominating
            max_per_cat = max(3, char_budget // (len(by_category) * 80))
            for claim_text in cat_lines[:max_per_cat]:
                line = f"[{cat.capitalize()}] {claim_text}"
                if len("\n".join(lines)) + len(line) + 3 > cls._MAX_CONTEXT_CHARS:
                    break
                lines.append(line)

        if len(lines) == 1:  # Only the header
            return ""

        lines.append("=== End Evidence Context ===")
        return "\n".join(lines)