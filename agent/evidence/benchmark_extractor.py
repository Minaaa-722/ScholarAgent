"""Benchmark extractor and verifier for the evidence grounding layer.

Extracts structured BenchmarkRecord objects from EvidenceReference objects
using LLM prompts, and verifies them against source evidence and paper
metadata.
"""

import json
import logging

from agent.core.llm import LLMBase
from agent.evidence.evidence_reference import EvidenceReference
from agent.evidence.benchmark_store import BenchmarkRecord

logger = logging.getLogger(__name__)


class BenchmarkExtractor:
    """Extracts structured BenchmarkRecord from EvidenceReference objects.

    Takes already-extracted evidence references and identifies benchmark
    results within them. Uses LLM to parse benchmark numbers, metrics,
    and model names from evidence excerpts.
    """

    def __init__(self, llm: LLMBase):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(
        self,
        evidence_refs: list[EvidenceReference],
    ) -> list[BenchmarkRecord]:
        """Extract benchmark records from evidence references.

        Args:
            evidence_refs: List of EvidenceReference objects containing
                           excerpts that may describe benchmark results.

        Returns:
            A list of extracted BenchmarkRecord objects. Empty if
            extraction fails or no benchmark results are found.
        """
        if not evidence_refs:
            logger.warning("Empty evidence_refs — skipping benchmark extraction")
            return []

        prompt = self._build_prompt(evidence_refs)
        try:
            resp = self._llm.generate(
                system_prompt=self._SYSTEM_PROMPT,
                user_message=prompt,
            )
            records = self._parse_response(resp.text, evidence_refs)
            logger.info("Extracted %d benchmark records", len(records))
            return records
        except Exception as e:
            logger.warning("Benchmark extraction failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    _SYSTEM_PROMPT = (
        "You are a benchmark extraction assistant. "
        "Extract benchmark evaluation results from the given evidence excerpts. "
        "Each excerpt is from a research paper and may contain benchmark scores.\n\n"
        "Return ONLY a JSON array of objects, each with:\n"
        '  "excerpt_index": integer index into the evidence list (0-based),\n'
        '  "model_name": the model name being evaluated (or "unknown" if not clear),\n'
        '  "benchmark_name": the benchmark name (e.g., "MMLU", "MathVista"),\n'
        '  "metric": the specific metric (e.g., "accuracy", "pass@1"),\n'
        '  "score": the score value as a string (e.g., "85.3", "4.5/5"),\n'
        '  "score_unit": the unit for the score (default "%"),\n'
        '  "split": the dataset split if mentioned (e.g., "test", "val", "zero-shot"),\n\n'
        "IMPORTANT: Only extract information that is explicitly present in the evidence "
        "excerpt. Do NOT fabricate benchmark results. Do NOT generate new facts. "
        "If no benchmark results are found, return an empty array [].\n\n"
        "Example:\n"
        '[\n'
        '  {"excerpt_index": 0, "model_name": "Qwen2-VL", '
        '"benchmark_name": "MMLU", "metric": "accuracy", "score": "85.3", '
        '"score_unit": "%", "split": "test"}\n'
        "]\n\n"
        "Return ONLY the JSON array. No markdown, no explanation."
    )

    def _build_prompt(self, evidence_refs: list[EvidenceReference]) -> str:
        lines = []
        for i, ref in enumerate(evidence_refs):
            lines.append(
                f"[{i}] paper_id={ref.paper_id} | section={ref.section} | "
                f"source_type={ref.source_type} | page={ref.page_number}\n"
                f"    excerpt: {ref.excerpt[:1000]}"
            )
        excerpts_text = "\n\n".join(lines)

        return (
            f"Extract benchmark evaluation results from the following "
            f"evidence excerpts ({len(evidence_refs)} total):\n\n"
            f"{excerpts_text}"
        )

    def _parse_response(
        self,
        text: str,
        evidence_refs: list[EvidenceReference],
    ) -> list[BenchmarkRecord]:
        """Parse LLM response into BenchmarkRecord objects."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse benchmark extraction JSON")
            return []

        if not isinstance(data, list):
            logger.warning("Benchmark extraction response is not a list")
            return []

        records: list[BenchmarkRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            excerpt_index = item.get("excerpt_index", -1)
            if not isinstance(excerpt_index, int) or excerpt_index < 0:
                continue
            if excerpt_index >= len(evidence_refs):
                logger.warning(
                    "excerpt_index %d out of range (max %d)",
                    excerpt_index, len(evidence_refs) - 1,
                )
                continue

            source = evidence_refs[excerpt_index]
            model_name = (item.get("model_name") or "").strip()
            benchmark_name = (item.get("benchmark_name") or "").strip()
            metric = (item.get("metric") or "").strip()
            score = (item.get("score") or "").strip()

            if not benchmark_name or not score:
                continue

            score_unit = (item.get("score_unit") or "%").strip()
            split = (item.get("split") or "").strip()

            try:
                record = BenchmarkRecord(
                    model_name=model_name or "unknown",
                    benchmark_name=benchmark_name,
                    metric=metric,
                    score=score,
                    score_unit=score_unit,
                    split=split,
                    source=source,
                    verified=False,
                )
                records.append(record)
            except ValueError:
                continue

        return records


class BenchmarkVerifier:
    """Verifies benchmark records against source evidence and paper metadata.

    A benchmark record is considered verified when:
    1. Its EvidenceReference passed validation (exists in source PDF)
    2. Semantic consistency: model_name, benchmark_name, and score/metric
       all appear in the evidence excerpt
    3. The score is internally consistent (no obviously impossible values)
    4. The model_name can be plausibly linked to the paper
    """

    def __init__(self, llm: LLMBase | None = None):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def verify(
        self,
        records: list[BenchmarkRecord],
        papers: list[dict],
    ) -> list[str]:
        """Verify a list of benchmark records against paper metadata.

        Returns a list of record IDs that passed verification.
        """
        if not records:
            return []

        passed: list[str] = []
        for record in records:
            # Find the paper this record belongs to
            paper = self._find_paper(record, papers)
            if self.verify_record(record, paper):
                passed.append(record.id)

        logger.info(
            "Benchmark verification: %d/%d records passed",
            len(passed), len(records),
        )
        return passed

    def verify_record(
        self,
        record: BenchmarkRecord,
        paper: dict | None = None,
    ) -> bool:
        """Verify a single benchmark record against its source evidence.

        Checks:
        1. EvidenceReference has a non-empty excerpt
        2. Semantic consistency: model_name, benchmark_name, and score
           appear in the evidence excerpt
        3. Score is not obviously impossible
        4. Model name is plausibly linked to the paper (if paper provided)

        Returns True if the record passes all checks.
        """
        # Check 1: EvidenceReference has a non-empty excerpt
        excerpt = (record.source.excerpt or "").strip()
        if not excerpt:
            logger.debug("Record %s: empty excerpt", record.id)
            return False

        # Check 2: Semantic consistency
        excerpt_lower = excerpt.lower()
        checks_ok = True

        if record.model_name and record.model_name.lower() != "unknown":
            if record.model_name.lower() not in excerpt_lower:
                checks_ok = False

        if record.benchmark_name:
            if record.benchmark_name.lower() not in excerpt_lower:
                checks_ok = False

        if record.score:
            score_clean = record.score.lower().strip()
            if score_clean not in excerpt_lower:
                checks_ok = False

        if not checks_ok:
            logger.debug(
                "Record %s: semantic consistency check failed "
                "(model='%s', benchmark='%s', score='%s' not all in excerpt)",
                record.id, record.model_name, record.benchmark_name, record.score,
            )
            return False

        # Check 3: Score is internally consistent
        if not self._check_score_plausible(record.score):
            logger.debug("Record %s: implausible score '%s'", record.id, record.score)
            return False

        # Check 4: Model name plausibly linked to paper (if paper provided)
        if paper is not None and record.model_name.lower() != "unknown":
            if not self._check_model_paper_link(record.model_name, paper):
                logger.debug(
                    "Record %s: model '%s' not linked to paper '%s'",
                    record.id, record.model_name, paper.get("title", ""),
                )
                return False

        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _find_paper(
        self,
        record: BenchmarkRecord,
        papers: list[dict],
    ) -> dict | None:
        """Find the paper that matches this record's source evidence."""
        paper_id = record.source.paper_id
        if not paper_id:
            return None
        for p in papers:
            pid = p.get("paper_id") or p.get("arxiv_id", "")
            if pid == paper_id:
                return p
        return None

    @staticmethod
    def _check_score_plausible(score: str) -> bool:
        """Check that a score is not obviously impossible.

        Accepts scores like "85.3", "4.5/5", "83.2 (+2.4)", "92.1%".
        Rejects obviously impossible values like empty, negative numbers
        (outside of valid range contexts), or non-numeric.
        """
        score = score.strip().lower()
        if not score:
            return False

        # Remove common suffixes and parenthetical modifiers
        cleaned = score.replace("%", "").replace(" ", "")
        # Handle "x/y" format
        if "/" in cleaned:
            parts = cleaned.split("/")
            try:
                num = float(parts[0])
                den = float(parts[1])
                return 0.0 <= num <= den
            except (ValueError, IndexError):
                return False

        # Handle "x (+y)" or "x (-y)" format
        if "(" in cleaned:
            cleaned = cleaned.split("(")[0].strip()

        # Remove trailing +/- modifiers
        for suffix in ["+", "-"]:
            if suffix in cleaned:
                cleaned = cleaned.split(suffix)[0].strip()

        try:
            val = float(cleaned)
        except ValueError:
            return False

        # Scores should be reasonable (0 to 100 for percentage, or known ranges)
        return 0.0 <= val <= 100.0

    @staticmethod
    def _check_model_paper_link(model_name: str, paper: dict) -> bool:
        """Check if model_name is plausibly linked to the paper.

        Performs a simple substring match against paper title and abstract.
        """
        model_lower = model_name.lower()
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()

        return model_lower in title or model_lower in abstract
