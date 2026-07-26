import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


INFORMAL_PATTERNS = [
    r'\bsuper\b', r'\bawesome\b', r'\bcool\b', r'\bamazing\b',
    r'\bguess\b', r'\bbasically\b', r'\bkinda\b', r'\bsorta\b',
    r'\blike\b', r'\bthings?\b', r'\bstuff\b', r'\ba lot\b',
]


class OutputStandard(Guardrail):
    name = "output_standard"

    def check(self, context: dict) -> GuardrailResult:
        text = context.get("text", "").lower()
        for pattern in INFORMAL_PATTERNS:
            if re.search(pattern, text):
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    message="Informal language detected in output",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )
