"""Relevance filter tool — filters papers by LLM-judged relevance to the research topic."""
import logging

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class RelevanceFilter(Tool):
    name = "relevance_filter"
    description = "Filter papers by LLM-judged relevance to the research topic"

    def execute(self, params: dict) -> ToolResult:
        papers = params.get("papers", [])
        llm_response = params.get("llm_response", "")
        threshold = float(params.get("threshold", 3.0))

        if not papers:
            return ToolResult(success=True, data={"papers": []})

        if not llm_response:
            # No LLM response — keep all papers with neutral score
            for p in papers:
                p["_relevance_score"] = 3.0
                p["_relevance_note"] = "no_judgment"
            return ToolResult(success=True, data={"papers": papers})

        # Parse LLM response: "TITLE | SCORE | NOTE"
        score_map = {}  # title.lower() -> (score, note)
        for line in llm_response.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue
            title = parts[0].lower().strip()
            try:
                score = float(parts[1])
            except (ValueError, IndexError):
                score = 3.0
            note = parts[2] if len(parts) >= 3 else ""
            score_map[title] = (score, note)

        kept = []
        for p in papers:
            title = (p.get("title") or "").lower().strip()
            if title in score_map:
                score, note = score_map[title]
                p["_relevance_score"] = score
                p["_relevance_note"] = note
                if score >= threshold:
                    kept.append(p)
                else:
                    logger.debug("Filtered out (score=%.1f): %s", score, p.get("title"))
            else:
                # Title not found in LLM response — keep with default score
                p["_relevance_score"] = 3.0
                p["_relevance_note"] = "not_judged"
                kept.append(p)

        return ToolResult(success=True, data={
            "papers": kept,
            "total_before": len(papers),
            "total_after": len(kept),
            "filtered_out": len(papers) - len(kept),
        })