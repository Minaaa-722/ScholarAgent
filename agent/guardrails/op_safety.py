import re
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


DANGEROUS_PATTERNS = [
    r'rm\s+[-]?rf',
    r'del\s+/[Ff]',
    r'format\s+',
    r'mkfs\.',
    r'dd\s+if=',
    r'>\s*/dev/sda',
    r'drop\s+table',
    r'delete\s+from\s+\w+\s+(where\s+)?1?=?\s*1',
]


class OpSafety(Guardrail):
    name = "op_safety"

    def check(self, context: dict) -> GuardrailResult:
        params = context.get("params", {})
        command = params.get("command", "")
        action = context.get("action", "")
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return GuardrailResult(
                    verdict=GuardrailVerdict.REQUIRE_APPROVAL,
                    message=f"Dangerous command detected: {command[:100]}",
                    guardrail_name=self.name,
                )
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )