import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class FactBinding(Guardrail):
    name = "fact_binding"

    def check(self, context: dict) -> GuardrailResult:
        chapter = context.get("chapter", {})
        content = chapter.get("content", "")
        # Check for citation markers like [@id]
        citations = re.findall(r'\[@(\w+)\]', content)
        needs_citation = re.findall(r'\[citation-needed\]', content)
        if needs_citation:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                message=f"Found {len(needs_citation)} claims without citation support",
                guardrail_name=self.name,
            )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )