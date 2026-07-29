import logging
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_store import Claim, EvidenceStore

logger = logging.getLogger(__name__)


class ClaimVerifier:
    """Verifies extracted claims against paper source data.

    Cross-references each unverified claim with the paper's title, abstract,
    and metadata to determine whether the claim is supported by the source.
    Uses the existing LLMBase for semantic verification.
    """

    def __init__(self, llm: LLMBase):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def verify_all(self, store: EvidenceStore, papers: list[dict]) -> int:
        """Verify all unverified claims in the store against paper data.

        Args:
            store: The EvidenceStore containing claims.
            papers: The list of paper dicts from the RETRIEVAL stage.

        Returns:
            Number of claims newly verified.
        """
        unverified = store.get_unverified_claims()
        if not unverified:
            return 0

        # Build paper_id → paper data lookup
        paper_map: dict[str, dict] = {}
        for p in papers:
            pid = p.get("paper_id") or p.get("arxiv_id", "")
            if pid:
                paper_map[pid] = p

        # Group unverified claims by paper_id for batch verification
        by_paper: dict[str, list[Claim]] = {}
        no_paper_claims: list[Claim] = []
        for c in unverified:
            if c.paper_id and c.paper_id in paper_map:
                by_paper.setdefault(c.paper_id, []).append(c)
            else:
                no_paper_claims.append(c)

        newly_verified = 0

        # Verify claims with known paper references
        for paper_id, claims in by_paper.items():
            paper = paper_map[paper_id]
            verified_texts = self._verify_batch(claims, paper)
            if verified_texts:
                count = store.mark_verified(verified_texts)
                newly_verified += count

        # For claims without a paper_id, do a lightweight check
        if no_paper_claims:
            verified_texts = self._lightweight_verify(no_paper_claims)
            if verified_texts:
                count = store.mark_verified(verified_texts)
                newly_verified += count

        logger.info(
            "Claim verification: %d newly verified (%d unverified remain)",
            newly_verified, len(store.get_unverified_claims()),
        )
        return newly_verified

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    _VERIFY_SYSTEM_PROMPT = (
        "You are a claim verification assistant. "
        "Given a list of technical claims and a paper's abstract, "
        "determine which claims are supported by the paper. "
        "Return ONLY a JSON array of the claim texts that ARE supported. "
        "Example: [\"claim1\", \"claim3\"]\n"
        "No markdown, no explanation."
    )

    def _build_verify_prompt(
        self,
        claims: list[Claim],
        paper: dict,
    ) -> str:
        paper_title = paper.get("title", "Unknown")
        abstract = (paper.get("abstract") or "")[:1500]
        claims_text = "\n".join(f"- {c.claim}" for c in claims)

        return (
            f"Paper: {paper_title}\n"
            f"Abstract: {abstract}\n\n"
            f"Claims:\n{claims_text}\n\n"
            "Which of the above claims are supported by the paper's abstract? "
            "Return ONLY the claim texts that are supported."
        )

    def _verify_batch(
        self,
        claims: list[Claim],
        paper: dict,
    ) -> list[str]:
        """Verify a batch of claims for one paper.

        Returns a list of claim texts that are supported.
        """
        if not claims:
            return []

        try:
            resp = self._llm.generate(
                system_prompt=self._VERIFY_SYSTEM_PROMPT,
                user_message=self._build_verify_prompt(claims, paper),
            )
            return self._parse_verification_response(resp.text)
        except Exception as e:
            logger.warning("Batch claim verification failed: %s", e)
            return []

    def _lightweight_verify(self, claims: list[Claim]) -> list[str]:
        """Lightweight verification for claims without a paper_id.

        These claims come from general knowledge in the analysis.  We mark
        them as verified if they appear plausible (high confidence).
        """
        verified = []
        for c in claims:
            if c.confidence >= 0.7:
                verified.append(c.claim)
        return verified

    @staticmethod
    def _parse_verification_response(text: str) -> list[str]:
        """Parse the LLM verification response into a list of claim texts."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
            text = text.strip()

        import json
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if item]
        except json.JSONDecodeError:
            pass

        # Fallback: treat each line as a claim
        lines = []
        for line in text.split("\n"):
            line = line.strip().strip('"').strip("'").strip("-").strip()
            if line and not line.startswith(("```", "json", "which")):
                lines.append(line)
        return lines