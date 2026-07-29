import logging
import re
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_store import EvidenceStore
from agent.feedback.base import Validator, ValidationResult

logger = logging.getLogger(__name__)


class EvidenceChecker(Validator):
    """Two-level draft evidence checker for the VALIDATION stage.

    Level 1 — Rule-based comparison against EvidenceStore:
      Extracts candidate claims from the draft using regex patterns and
      compares them against verified claims in the store.  Detects:
        - Unsupported technical claims
        - Benchmark number inconsistency
        - Missing evidence references

    Level 2 — LLM semantic verification (only for suspicious claims):
      Sends only the flagged candidate claims (not the full paper) to the
      LLM for semantic verification.
    """

    name = "check_evidence"

    # Regex patterns for candidate claim extraction
    _CLAIM_PATTERNS = [
        # "X uses Y", "X employs Y", "X adopts Y"
        r'\b(\w+(?:[-/]\w+)*)\s+(?:uses|employs|adopts|introduces|proposes|applies)\s+(\w+(?:\s+\w+){0,5})',
        # "X achieves Y%", "X achieves Y accuracy"
        r'\b(\w+(?:[-/]\w+)*)\s+achieves?\s+(\d+\.?\d*\s*%[^,;.]*)',
        r'\b(\w+(?:[-/]\w+)*)\s+achieves?\s+(\d+\.?\d*\s*(?:accuracy|score|BLEU|ROUGE|F1)[^,;.]*)',
        # Benchmark numbers: "MMLU: 85.3%", "85.3% on MMLU"
        r'(\d+\.?\d*)\s*%\s*(?:on|in|for)\s+(\w+(?:\s+\w+){0,3})',
        r'(\w+(?:\s+\w+){0,3})\s*(?::|score[s]? of|accuracy of)\s*(\d+\.?\d*\s*%)',
        # "X outperforms Y"
        r'\b(\w+(?:[-/]\w+)*)\s+outperform[s]?\s+(\w+(?:[-/]\w+)*)',
    ]

    def __init__(
        self,
        evidence_store: EvidenceStore,
        llm: Optional[LLMBase] = None,
    ):
        self._evidence_store = evidence_store
        self._llm = llm

    # ------------------------------------------------------------------
    # Validator interface
    # ------------------------------------------------------------------
    def validate(self, context: dict) -> ValidationResult:
        """Run two-level evidence check on the draft.

        Context expects:
            "content": str — the draft paper text
        """
        content = context.get("content", "")

        if not content or not content.strip():
            return ValidationResult(
                validator_name=self.name,
                passed=True,
                score=1.0,
                issues=[],
                repair_instructions="",
            )

        # Level 1: Rule-based comparison
        candidates = self._extract_candidate_claims(content)
        level1_issues = self._check_against_store(candidates)

        if not level1_issues:
            return ValidationResult(
                validator_name=self.name,
                passed=True,
                score=1.0,
                issues=[],
                repair_instructions="",
            )

        # Level 2: LLM semantic verification for suspicious claims
        if self._llm and level1_issues:
            level2_issues = self._llm_verify(level1_issues, content)
            final_issues = level2_issues if level2_issues else level1_issues
        else:
            final_issues = level1_issues

        # Calculate score based on severity
        severity_weights = {
            "unsupported": 0.4,
            "benchmark_mismatch": 0.3,
            "missing_reference": 0.2,
            "architecture_mismatch": 0.4,
        }
        total_weight = sum(
            severity_weights.get(i.get("type", "unsupported"), 0.3)
            for i in final_issues
        )
        score = max(0.0, 1.0 - total_weight)

        issues_text = []
        for issue in final_issues:
            issues_text.append(
                f"[{issue.get('type', 'issue')}] {issue.get('claim', '')}"
                f"{' — ' + issue.get('detail', '') if issue.get('detail') else ''}"
            )

        repair_instructions = (
            "Review the following unsupported or inconsistent claims. "
            "Either add supporting evidence (verified citations) or remove them:\n"
            + "\n".join(f"- {t}" for t in issues_text)
        )

        return ValidationResult(
            validator_name=self.name,
            passed=score >= 0.7,
            score=score,
            issues=issues_text,
            repair_instructions=repair_instructions,
        )

    # ------------------------------------------------------------------
    # Level 1: Candidate extraction
    # ------------------------------------------------------------------
    def _extract_candidate_claims(self, content: str) -> list[dict]:
        """Extract candidate claims from the draft using regex patterns.

        Returns a list of dicts with keys: "claim", "type", "detail".
        """
        candidates = []
        seen = set()

        for pattern in self._CLAIM_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                claim_text = match.group(0).strip()
                key = claim_text.lower()
                if key in seen:
                    continue
                seen.add(key)

                candidate = {"claim": claim_text, "type": "unsupported", "detail": ""}

                # Classify the claim type
                if any(w in claim_text.lower() for w in ["%", "accuracy", "score", "bleu", "rouge", "f1"]):
                    if "achieves" in claim_text.lower() or ":" in claim_text:
                        candidate["type"] = "benchmark_mismatch"
                        candidate["detail"] = "benchmark number"
                    else:
                        candidate["type"] = "benchmark_mismatch"
                        candidate["detail"] = "benchmark number"
                elif any(w in claim_text.lower() for w in ["uses", "employs", "adopts", "introduces", "proposes"]):
                    candidate["type"] = "architecture_mismatch"
                    candidate["detail"] = "architecture description"
                elif "outperform" in claim_text.lower():
                    candidate["type"] = "comparison"
                    candidate["detail"] = "model comparison"

                candidates.append(candidate)

        return candidates

    # ------------------------------------------------------------------
    # Level 1: Store comparison
    # ------------------------------------------------------------------
    def _check_against_store(self, candidates: list[dict]) -> list[dict]:
        """Compare candidate claims against verified claims in the store.

        Returns a filtered list of issues (only those not supported by evidence).
        """
        verified = self._evidence_store.get_verified_claims()
        if not verified:
            # No verified claims available — flag all as potential issues
            return candidates

        verified_texts = [v.claim.lower() for v in verified]
        issues = []

        for candidate in candidates:
            claim_lower = candidate["claim"].lower()

            # Check if any verified claim supports this candidate
            supported = False
            for vtext in verified_texts:
                # Check for overlap: candidate claim contains verified text
                # or verified text contains candidate claim
                if (len(claim_lower) > 5 and claim_lower in vtext) or \
                   (len(vtext) > 5 and vtext in claim_lower):
                    supported = True
                    break

            if not supported:
                issues.append(candidate)

        return issues

    # ------------------------------------------------------------------
    # Level 2: LLM semantic verification
    # ------------------------------------------------------------------
    _LLM_VERIFY_SYSTEM_PROMPT = (
        "You are a claim verification assistant. "
        "Given a list of suspicious claims extracted from a survey paper draft, "
        "determine which claims are LIKELY FALSE or UNSUPPORTED. "
        "Return ONLY a JSON array of the claim texts that are problematic.\n"
        "Example: [\"Model X achieves 99.9% accuracy\"]\n"
        "No markdown, no explanation."
    )

    def _llm_verify(
        self,
        candidates: list[dict],
        content: str,
    ) -> list[dict]:
        """Use LLM to semantically verify suspicious claims.

        Sends only the suspicious claim texts (not the full paper) to the LLM.
        """
        if not self._llm:
            return candidates

        claim_texts = [c["claim"] for c in candidates]
        if not claim_texts:
            return []

        prompt = (
            "Verify the following claims extracted from a survey paper draft. "
            "Are any of them likely false, exaggerated, or unsupported?\n\n"
            + "\n".join(f"- {t}" for t in claim_texts)
        )

        try:
            resp = self._llm.generate(
                system_prompt=self._LLM_VERIFY_SYSTEM_PROMPT,
                user_message=prompt,
            )
            problematic = self._parse_llm_response(resp.text)
        except Exception as e:
            logger.warning("Level 2 LLM verification failed: %s", e)
            return candidates

        if not problematic:
            # LLM cleared all candidates
            return []

        # Return only the candidates flagged by the LLM
        problematic_lower = {p.strip().lower() for p in problematic}
        return [
            c for c in candidates
            if c["claim"].strip().lower() in problematic_lower
        ]

    @staticmethod
    def _parse_llm_response(text: str) -> list[str]:
        """Parse the LLM verification response."""
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

        # Fallback: line-by-line
        results = []
        for line in text.split("\n"):
            line = line.strip().strip('"').strip("'").strip("-").strip()
            if line and not line.startswith(("```", "json", "which", "the")):
                results.append(line)
        return results