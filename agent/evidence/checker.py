import logging
import re
from typing import Optional

from agent.core.llm import LLMBase
from agent.evidence.evidence_store import EvidenceStore
from agent.evidence.benchmark_store import BenchmarkStore
from agent.evidence.paper_knowledge import PaperKnowledgeBase
from agent.evidence.paper_types import (
    EvidenceLevel,
    ClaimType,
    MIN_EVIDENCE_LEVEL,
    PaperAvailability,
    PaperStatus,
    EvidenceSource,
)
from agent.feedback.base import Validator, ValidationResult

logger = logging.getLogger(__name__)


class EvidenceChecker(Validator):
    """Multi-store evidence checker for the VALIDATION stage.

    Validates draft paper claims against three stores:
      - EvidenceStore: verified claims (existing)
      - BenchmarkStore: verified benchmark records
      - PaperKnowledgeBase: structured paper knowledge (architecture, training, etc.)

    Level 1 — Rule-based comparison against all three stores:
      - Unsupported claims (not in EvidenceStore)
      - Benchmark mismatch / missing benchmark (BenchmarkStore)
      - Model inconsistency (PaperKnowledgeBase)
      - Missing evidence (no reference in any store)

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
        benchmark_store: BenchmarkStore,
        knowledge_base: PaperKnowledgeBase,
        llm: Optional[LLMBase] = None,
    ):
        self._evidence_store = evidence_store
        self._benchmark_store = benchmark_store
        self._knowledge_base = knowledge_base
        self._llm = llm

    # ------------------------------------------------------------------
    # Validator interface
    # ------------------------------------------------------------------
    def validate(self, context: dict) -> ValidationResult:
        """Run multi-store evidence check on the draft.

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

        # Level 1: Rule-based comparison against all three stores
        candidates = self._extract_candidate_claims(content)

        evidence_issues = self._check_against_store(candidates)
        benchmark_issues = self._check_benchmarks(candidates)
        model_issues = self._check_model_consistency(candidates)
        missing_evidence_issues = self._check_missing_evidence(candidates)

        all_issues = evidence_issues + benchmark_issues + model_issues + missing_evidence_issues

        # Enhanced checks: evidence level constraints
        if self._evidence_store.claim_count() == 0:
            logger.warning("EvidenceChecker: EvidenceStore is empty — no claims to verify against")
            all_issues.append({
                "claim": "(entire draft)",
                "type": "missing_evidence",
                "detail": "EvidenceStore is empty. No verified claims available for comparison.",
            })

        level_issues = self._check_evidence_levels(candidates)
        all_issues.extend(level_issues)

        if not all_issues:
            return ValidationResult(
                validator_name=self.name,
                passed=True,
                score=1.0,
                issues=[],
                repair_instructions="",
            )

        # Level 2: LLM semantic verification for suspicious claims
        if self._llm and all_issues:
            level2_issues = self._llm_verify(all_issues, content)
            final_issues = level2_issues if level2_issues else all_issues
        else:
            final_issues = all_issues

        # Calculate score based on severity
        severity_weights = {
            "unsupported": 0.4,
            "benchmark_mismatch": 0.3,
            "missing_benchmark": 0.3,
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
                f"{' -- ' + issue.get('detail', '') if issue.get('detail') else ''}"
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
    # Level 1: EvidenceStore comparison
    # ------------------------------------------------------------------
    def _check_against_store(self, candidates: list[dict]) -> list[dict]:
        """Compare candidate claims against verified claims in EvidenceStore.

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
    # Level 1: BenchmarkStore comparison
    # ------------------------------------------------------------------
    def _check_benchmarks(self, candidates: list[dict]) -> list[dict]:
        """Check benchmark claims against BenchmarkStore.

        Detects:
        - Benchmark mismatch: benchmark name in draft but score differs from stored record
        - Missing benchmark: benchmark name in draft but no matching record
        """
        issues = []
        benchmark_candidates = [
            c for c in candidates
            if c.get("type") == "benchmark_mismatch"
        ]

        for candidate in benchmark_candidates:
            claim_text = candidate["claim"]
            benchmark_name = self._extract_benchmark_name(claim_text)
            draft_score = self._extract_score(claim_text)

            if not benchmark_name:
                continue

            # Look up in BenchmarkStore
            records = self._benchmark_store.lookup(benchmark_name)

            if not records:
                # Missing benchmark — no record at all
                issues.append({
                    "claim": claim_text,
                    "type": "missing_benchmark",
                    "detail": f"No benchmark record found for '{benchmark_name}'",
                })
            else:
                # Check if draft score matches any verified record
                verified_records = [r for r in records if r.verified]
                if verified_records and draft_score:
                    matched = False
                    for record in verified_records:
                        if record.score == draft_score:
                            matched = True
                            break
                    if not matched:
                        stored_scores = ", ".join(
                            f"{r.benchmark_name}: {r.score}{r.score_unit}"
                            for r in verified_records
                        )
                        issues.append({
                            "claim": claim_text,
                            "type": "benchmark_mismatch",
                            "detail": (
                                f"Benchmark '{benchmark_name}' score {draft_score}% "
                                f"differs from stored: {stored_scores}"
                            ),
                        })

        return issues

    # ------------------------------------------------------------------
    # Level 1: PaperKnowledgeBase model consistency
    # ------------------------------------------------------------------
    def _check_model_consistency(self, candidates: list[dict]) -> list[dict]:
        """Check architecture claims against PaperKnowledgeBase.

        Detects model inconsistency: architecture/training details in the
        draft contradict stored knowledge.
        """
        issues = []
        arch_candidates = [
            c for c in candidates
            if c.get("type") == "architecture_mismatch"
        ]

        if not arch_candidates or not self._knowledge_base.get_all():
            return issues

        for candidate in arch_candidates:
            claim_text = candidate["claim"]
            model_name = self._extract_model_name(claim_text)

            if not model_name:
                continue

            # Look up model in knowledge base
            for pk in self._knowledge_base.get_all():
                is_match = (
                    model_name.lower() in pk.title.lower()
                    or model_name.lower() in pk.paper_id.lower()
                    or (pk.main_contribution.lower() and model_name.lower() in pk.main_contribution.lower())
                )
                if not is_match:
                    continue

                # Check architecture details
                if pk.architecture:
                    arch = pk.architecture
                    for field_name, field_value in [
                        ("vision_encoder", arch.vision_encoder.value),
                        ("language_model", arch.language_model.value),
                        ("connector", arch.connector.value),
                        ("resolution_strategy", arch.resolution_strategy.value),
                    ]:
                        if field_value and field_value.lower() not in claim_text.lower():
                            issues.append({
                                "claim": claim_text,
                                "type": "architecture_mismatch",
                                "detail": (
                                    f"Model '{model_name}' has {field_name}="
                                    f"'{field_value}' in knowledge base, "
                                    f"but draft claims '{claim_text}'"
                                ),
                            })

                # Check training details
                if pk.training:
                    training = pk.training
                    for field_name, field_value in [
                        ("pretraining_dataset", training.pretraining_dataset.value),
                        ("optimization_method", training.optimization_method.value),
                    ]:
                        if field_value and field_value.lower() not in claim_text.lower():
                            issues.append({
                                "claim": claim_text,
                                "type": "architecture_mismatch",
                                "detail": (
                                    f"Model '{model_name}' has {field_name}="
                                    f"'{field_value}' in knowledge base, "
                                    f"but draft claims '{claim_text}'"
                                ),
                            })

        return issues

    # ------------------------------------------------------------------
    # Level 1: Missing evidence across all stores
    # ------------------------------------------------------------------
    def _check_missing_evidence(self, candidates: list[dict]) -> list[dict]:
        """Check for strong technical claims with no evidence in any store.

        Flags candidates that are not supported by any verified claim in
        EvidenceStore, BenchmarkStore, or PaperKnowledgeBase.
        """
        issues = []

        # Gather all evidence texts from all three stores
        evidence_texts = set()

        for claim in self._evidence_store.get_verified_claims():
            evidence_texts.add(claim.claim.lower())

        for record in self._benchmark_store.get_verified():
            evidence_texts.add(record.benchmark_name.lower())
            evidence_texts.add(f"{record.model_name} {record.benchmark_name}".lower())

        for pk in self._knowledge_base.get_all():
            evidence_texts.add(pk.title.lower())
            if pk.main_contribution:
                evidence_texts.add(pk.main_contribution.lower())

        if not evidence_texts:
            # No evidence available to compare against — skip
            return issues

        for candidate in candidates:
            claim_text = candidate["claim"].lower()

            found = False
            for etext in evidence_texts:
                if (len(claim_text) > 5 and claim_text in etext) or \
                   (len(etext) > 5 and etext in claim_text):
                    found = True
                    break

            if not found:
                issues.append({
                    "claim": candidate["claim"],
                    "type": "missing_reference",
                    "detail": "Strong technical claim with no evidence reference in any store",
                })

        return issues

    # ------------------------------------------------------------------
    # Enhanced: Evidence level checks
    # ------------------------------------------------------------------

    def _check_evidence_levels(self, candidates: list[dict]) -> list[dict]:
        """Check that claims have sufficient evidence level.

        Rules:
          - Benchmark claims require FULL_TEXT evidence
          - Claims about withdrawn papers are flagged

        Returns a list of issue dicts for violations.
        """
        issues = []

        for candidate in candidates:
            claim_text = candidate["claim"]
            claim_type = candidate.get("type", "unsupported")

            # Benchmark claims need FULL_TEXT
            if claim_type == "benchmark_mismatch":
                benchmark_name = self._extract_benchmark_name(claim_text)
                if benchmark_name:
                    records = self._benchmark_store.lookup(benchmark_name)
                    has_full_text = False
                    for r in records:
                        if r.source and r.evidence_level >= EvidenceLevel.FULL_TEXT:
                            has_full_text = True
                            break
                    if not has_full_text:
                        issues.append({
                            "claim": claim_text,
                            "type": "insufficient_evidence",
                            "detail": (
                                f"Benchmark claim '{benchmark_name}' requires FULL_TEXT "
                                f"evidence but none available"
                            ),
                        })

        return issues

    # ------------------------------------------------------------------
    # Helpers: extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_benchmark_name(claim_text: str) -> str:
        """Extract benchmark name from a claim text.

        Handles patterns like:
        - "85.3% on MMLU" -> "MMLU"
        - "MMLU: 85.3%" -> "MMLU"
        - "Model achieves 90.0% on MMLU" -> "MMLU"
        """
        # Pattern: "85.3% on MMLU" or "85.3% accuracy on MMLU"
        m = re.search(r'%\s*(?:on|in|for)\s+(\w+(?:\s+\w+){0,3})', claim_text)
        if m:
            return m.group(1).strip()

        # Pattern: "MMLU: 85.3%" or "MMLU score: 85.3%"
        m = re.search(
            r'(\w+(?:\s+\w+){0,3})\s*(?::|score[s]?\s+of|accuracy\s+of)\s*\d',
            claim_text,
        )
        if m:
            return m.group(1).strip()

        return ""

    @staticmethod
    def _extract_score(claim_text: str) -> str:
        """Extract numeric score from a claim text."""
        m = re.search(r'(\d+\.?\d*)\s*%', claim_text)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _extract_model_name(claim_text: str) -> str:
        """Extract model name from a claim text.

        Handles patterns like:
        - "Qwen2-VL uses ..." -> "Qwen2-VL"
        - "Model X achieves ..." -> "Model X" (but only first word with hyphen/slash)
        """
        m = re.search(
            r'^(\w+(?:[-/]\w+)*)\s+(?:uses|employs|adopts|introduces|proposes|achieves)',
            claim_text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
        return ""

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