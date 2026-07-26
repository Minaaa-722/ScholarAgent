from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class SourceFilter(Guardrail):
    name = "source_filter"

    def __init__(self, blacklist: list[str] | None = None):
        self.blacklist = blacklist or []

    def check(self, context: dict) -> GuardrailResult:
        paper = context.get("paper", {})
        journal = (paper.get("journal") or "").lower()
        source = (paper.get("source") or "").lower()
        for banned in self.blacklist:
            if banned.lower() in journal or banned.lower() in source:
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    message=f"Source '{journal or source}' is blacklisted",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )