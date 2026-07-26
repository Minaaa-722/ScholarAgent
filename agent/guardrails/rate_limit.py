import time
from collections import defaultdict
from agent.guardrails.base import Guardrail, GuardrailResult, GuardrailVerdict


class RateLimit(Guardrail):
    name = "rate_limit"

    def __init__(self, max_calls: int = 30, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, context: dict) -> GuardrailResult:
        action = context.get("action", "default")
        now = time.time()
        window_start = now - self.window_seconds
        self._call_timestamps[action] = [
            t for t in self._call_timestamps[action] if t > window_start
        ]
        if len(self._call_timestamps[action]) >= self.max_calls:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                message=f"Rate limit exceeded for '{action}': {self.max_calls} calls per {self.window_seconds}s",
                guardrail_name=self.name,
            )
        self._call_timestamps[action].append(now)
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            guardrail_name=self.name,
        )