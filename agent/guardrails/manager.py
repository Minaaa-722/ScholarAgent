from typing import Any, Optional

from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict
from agent.guardrails.op_safety import OpSafety
from agent.guardrails.rate_limit import RateLimit
from agent.guardrails.source_filter import SourceFilter
from agent.guardrails.fact_binding import FactBinding
from agent.guardrails.output_std import OutputStandard


class GuardrailManager:
    """Unified manager for all guardrail checks.

    Wraps the 5 guardrail classes and provides a single check interface
    for the pipeline orchestrator.
    """

    def __init__(self, guardrails: Optional[list[Guardrail]] = None):
        if guardrails is None:
            self._guardrails = [
                OpSafety(),
                RateLimit(),
                SourceFilter(),
                FactBinding(),
                OutputStandard(),
            ]
        else:
            self._guardrails = guardrails

    def check_all(self, context: dict[str, Any]) -> list[GuardrailResult]:
        """Run all guardrails and return all results."""
        return [g.check(context) for g in self._guardrails]

    def check_tool_call(self, tool_name: str, params: dict[str, Any]) -> GuardrailResult:
        """Check a tool call against OpSafety and RateLimit.

        Returns the first non-PASS verdict, or PASS if all pass.
        """
        for g in self._guardrails:
            if isinstance(g, (OpSafety, RateLimit)):
                result = g.check({"action": tool_name, "params": params})
                if result.verdict != GuardrailVerdict.PASS:
                    return result
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name="tool_call",
        )

    def filter_papers(self, papers: list[dict]) -> list[dict]:
        """Filter papers through SourceFilter, returning only passing papers."""
        filtered = []
        for p in papers:
            result = self._check_source(p)
            if result.verdict == GuardrailVerdict.PASS:
                filtered.append(p)
        return filtered

    def _check_source(self, paper: dict) -> GuardrailResult:
        for g in self._guardrails:
            if isinstance(g, SourceFilter):
                return g.check({"paper": paper})
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name="source",
        )
