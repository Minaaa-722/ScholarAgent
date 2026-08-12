"""Benchmark table generator for deterministic LaTeX table insertion.

Generates IEEEtran-format (three-line) LaTeX tables from verified benchmark
records and summary comparison tables from PaperKnowledgeBase.

Triggered by ``[TABLE:benchmark_<NAME>]`` and ``[TABLE:model_taxonomy]``
markers placed by the LLM during the writing stage.
"""

import logging
from typing import Optional

from agent.evidence.benchmark_store import BenchmarkRecord, BenchmarkStore
from agent.evidence.citation_store import CitationStore
from agent.evidence.paper_knowledge import PaperKnowledgeBase

logger = logging.getLogger(__name__)

# Regex to match [TABLE:...] markers
_TABLE_PATTERN = __import__("re").compile(r"\[TABLE:([^\]]+)\]")


class BenchmarkTableGenerator:
    """Generate LaTeX tables from verified benchmark records.

    Mode 1 — Benchmark-specific table (default):
        One table per ``benchmark_name``, sorted by score descending.
        Triggered by ``[TABLE:benchmark_MMLU]``, ``[TABLE:benchmark_MathVista]``, etc.

    Mode 2 — Summary comparison table (optional):
        Architecture/training comparison from ``PaperKnowledgeBase``.
        Triggered by ``[TABLE:model_taxonomy]``.

    Typical usage::

        generator = BenchmarkTableGenerator(benchmark_store, citation_store)
        draft = generator.replace_tables(draft, knowledge_base)
    """

    def __init__(
        self,
        benchmark_store: BenchmarkStore,
        citation_store: CitationStore,
    ) -> None:
        self._benchmark_store = benchmark_store
        self._citation_store = citation_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replace_tables(
        self,
        draft: str,
        knowledge_base: Optional[PaperKnowledgeBase] = None,
    ) -> str:
        """Replace all ``[TABLE:...]`` markers in the draft with generated tables.

        Supported markers:
          ``[TABLE:benchmark_<NAME>]`` — benchmark-specific table.
          ``[TABLE:model_taxonomy]`` — summary comparison table.

        Unknown markers are left as-is and a warning is logged.

        Args:
            draft: Draft text containing ``[TABLE:...]`` markers.
            knowledge_base: Required for ``[TABLE:model_taxonomy]``.

        Returns:
            Draft with table markers replaced by LaTeX table strings.
        """
        if not draft:
            return draft

        def _replacer(match: __import__("re").Match) -> str:
            marker = match.group(1).strip()

            # Benchmark-specific table
            if marker.startswith("benchmark_"):
                benchmark_name = marker[len("benchmark_"):]
                table = self.generate_benchmark_table(benchmark_name)
                if table:
                    return table
                logger.warning(
                    "No data for [TABLE:benchmark_%s] — keeping marker", benchmark_name
                )
                return match.group(0)

            # Summary comparison table
            if marker == "model_taxonomy":
                if not knowledge_base:
                    logger.warning(
                        "[TABLE:model_taxonomy] requires knowledge_base — keeping marker"
                    )
                    return match.group(0)
                table = self.generate_summary_table(knowledge_base)
                if table:
                    return table
                logger.warning(
                    "No data for [TABLE:model_taxonomy] — keeping marker"
                )
                return match.group(0)

            # Unknown marker
            logger.warning("Unknown table marker '[TABLE:%s]' — keeping as-is", marker)
            return match.group(0)

        return _TABLE_PATTERN.sub(_replacer, draft)

    # ------------------------------------------------------------------
    # Benchmark-specific table
    # ------------------------------------------------------------------

    def generate_benchmark_table(self, benchmark_name: str) -> str:
        """Generate one IEEEtran three-line LaTeX table for a specific benchmark.

        Steps:
          1. Get verified records for ``benchmark_name`` from ``BenchmarkStore``.
          2. Sort by score descending.
          3. Generate IEEEtran three-line table format.
          4. Each row: ``model_name | score | \\cite{citation_key}``.

        Args:
            benchmark_name: The benchmark name (e.g., ``"MMLU"``).

        Returns:
            LaTeX table string, or empty string if no data.
        """
        records = self._benchmark_store.get_verified(benchmark_name=benchmark_name)
        if not records:
            return ""

        # Sort by score descending (numeric comparison)
        sorted_records = sorted(
            records,
            key=lambda r: _parse_score(r.score),
            reverse=True,
        )

        # Build table
        lines: list[str] = []
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(
            r"\caption{Performance comparison on " + benchmark_name + ".}"
        )

        num_cols = "lcc" if any(r.citation_key for r in sorted_records) else "lc"
        lines.append(r"\begin{tabular}{" + num_cols + "}")
        lines.append(r"\toprule")

        if num_cols == "lcc":
            lines.append(f"Model & {benchmark_name} & Source \\\\")
        else:
            lines.append(f"Model & {benchmark_name} \\\\")

        lines.append(r"\midrule")

        for record in sorted_records:
            score_str = f"{record.score}{record.score_unit}" if record.score_unit else record.score
            if record.citation_key:
                lines.append(
                    f"{record.model_name} & {score_str} & \\cite{{{record.citation_key}}} \\\\"
                )
            else:
                lines.append(f"{record.model_name} & {score_str} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Summary comparison table
    # ------------------------------------------------------------------

    def generate_summary_table(self, knowledge_base: PaperKnowledgeBase) -> str:
        """Generate an architecture/training comparison table.

        Rows: models.
        Columns: architecture fields (``vision_encoder``, ``language_model``,
                  ``connector``, ``resolution_strategy``).

        Args:
            knowledge_base: Populated ``PaperKnowledgeBase``.

        Returns:
            LaTeX table string, or empty string if no data.
        """
        papers = knowledge_base.get_all()
        if not papers:
            return ""

        # Collect rows that have at least one architecture field
        rows: list[dict] = []
        for pk in papers:
            arch = pk.architecture
            if not arch:
                continue
            row = {
                "model": pk.title.split(":")[0].strip() if ":" in pk.title else pk.title,
                "vision_encoder": arch.vision_encoder.value if arch.vision_encoder else "",
                "language_model": arch.language_model.value if arch.language_model else "",
                "connector": arch.connector.value if arch.connector else "",
                "resolution_strategy": arch.resolution_strategy.value if arch.resolution_strategy else "",
            }
            if any(row.values()):
                rows.append(row)

        if not rows:
            return ""

        # Determine columns (only include non-empty columns)
        columns = ["model"]
        for col in ("vision_encoder", "language_model", "connector", "resolution_strategy"):
            if any(r.get(col, "") for r in rows):
                columns.append(col)

        # Column display names
        col_display = {
            "model": "Model",
            "vision_encoder": "Vision Encoder",
            "language_model": "Language Model",
            "connector": "Connector",
            "resolution_strategy": "Resolution",
        }

        # Build table
        lines: list[str] = []
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(r"\caption{Model architecture comparison.}")
        lines.append(r"\begin{tabular}{" + "l" + "c" * (len(columns) - 1) + "}")
        lines.append(r"\toprule")
        lines.append(" & ".join(col_display.get(c, c) for c in columns) + r" \\")
        lines.append(r"\midrule")

        for row in rows:
            cells = [row.get(c, "") for c in columns]
            lines.append(" & ".join(cells) + r" \\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def get_stale_markers(self, draft: str) -> list[str]:
        """Find all ``[TABLE:...]`` markers that couldn't be replaced.

        Returns:
            List of marker names (e.g., ``["benchmark_MMLU"]``).
        """
        stale: list[str] = []
        for match in _TABLE_PATTERN.finditer(draft):
            stale.append(match.group(1).strip())
        return stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_score(score_str: str) -> float:
    """Parse a score string to float for sorting.

    Handles simple numeric strings, ranges (``"83.2 (+2.4)"``), and
    fractional scores (``"4.5/5"``).
    """
    try:
        return float(score_str)
    except ValueError:
        pass
    # Try extracting the first number
    import re
    m = re.search(r"(\d+\.?\d*)", score_str)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0