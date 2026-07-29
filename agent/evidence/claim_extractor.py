import json
import logging
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_store import Claim

logger = logging.getLogger(__name__)


class ClaimExtractor:
    """Extracts structured technical claims from paper analysis text.

    Uses the existing LLMBase to analyse the analysis text produced by the
    ANALYSIS stage and return structured Claim objects.
    """

    def __init__(self, llm: LLMBase):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(
        self,
        analysis_text: str,
        papers: Optional[list[dict]] = None,
    ) -> list[Claim]:
        """Extract structured claims from analysis text.

        Args:
            analysis_text: The raw analysis text from _analyze_papers().
            papers: Optional list of paper dicts (used to resolve paper_id
                    from titles mentioned in claims).

        Returns:
            A list of extracted Claim objects.  Empty if extraction fails
            or the analysis text is empty.
        """
        if not analysis_text or not analysis_text.strip():
            logger.warning("Empty analysis text — skipping claim extraction")
            return []

        prompt = self._build_prompt(analysis_text)
        try:
            resp = self._llm.generate(
                system_prompt=self._SYSTEM_PROMPT,
                user_message=prompt,
            )
            claims = self._parse_response(resp.text, papers)
            logger.info("Extracted %d claims from analysis", len(claims))
            return claims
        except Exception as e:
            logger.warning("Claim extraction failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    _SYSTEM_PROMPT = (
        "You are a claim extraction assistant. "
        "Extract technical claims from the given paper analysis. "
        "Return ONLY a JSON array of objects, each with:\n"
        '  "claim": short technical claim text,\n'
        '  "category": one of "architecture", "dataset", "benchmark", "comparison",\n'
        '  "paper_title": the paper title (or "unknown" if not clear),\n'
        '  "confidence": a float 0.0–1.0.\n\n'
        "Example:\n"
        '[\n'
        '  {"claim": "Qwen2-VL uses dynamic resolution", '
        '"category": "architecture", "paper_title": "Qwen2-VL", "confidence": 0.9},\n'
        '  {"claim": "MMLU score: 85.3%", '
        '"category": "benchmark", "paper_title": "Qwen2-VL", "confidence": 0.8}\n'
        "]\n\n"
        "Return ONLY the JSON array. No markdown, no explanation."
    )

    def _build_prompt(self, analysis_text: str) -> str:
        return (
            f"Extract technical claims from the following paper analysis:\n\n"
            f"{analysis_text[:8000]}"
        )

    def _parse_response(
        self,
        text: str,
        papers: Optional[list[dict]],
    ) -> list[Claim]:
        """Parse LLM response into Claim objects."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse claim extraction JSON")
            return []

        if not isinstance(data, list):
            logger.warning("Claim extraction response is not a list")
            return []

        # Build paper-title → paper_id lookup
        title_to_id: dict[str, str] = {}
        if papers:
            for p in papers:
                t = (p.get("title") or "").strip().lower()
                pid = p.get("paper_id") or p.get("arxiv_id", "")
                if t and pid:
                    title_to_id[t] = pid

        claims: list[Claim] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            claim_text = (item.get("claim") or "").strip()
            if not claim_text:
                continue

            category = (item.get("category") or "architecture").strip().lower()
            paper_title = (item.get("paper_title") or "").strip()
            confidence = float(item.get("confidence", 0.5))

            # Resolve paper_id from paper_title
            paper_id = title_to_id.get(paper_title.lower(), "")

            try:
                claim = Claim(
                    claim=claim_text,
                    category=category,
                    paper_id=paper_id,
                    confidence=confidence,
                    verified=False,
                )
                claims.append(claim)
            except ValueError:
                # Skip invalid category claims
                continue

        return claims