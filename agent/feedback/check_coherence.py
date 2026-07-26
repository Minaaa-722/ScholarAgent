import re
from agent.feedback.base import Validator, ValidationResult


TRANSITION_MARKERS = [
    r'\bfirst(ly)?\b', r'\bsecond(ly)?\b', r'\bthird(ly)?\b',
    r'\bnext\b', r'\bthen\b', r'\bsubsequently\b', r'\bafter\b',
    r'\bfurthermore\b', r'\bmoreover\b', r'\bin addition\b',
    r'\bhowever\b', r'\bnevertheless\b', r'\bon the other hand\b',
    r'\bin contrast\b', r'\bconversely\b', r'\btherefore\b',
    r'\bthus\b', r'\bconsequently\b', r'\bas a result\b',
    r'\bfinally\b', r'\bin summary\b', r'\bto conclude\b',
    r'\bfor example\b', r'\bfor instance\b', r'\bspecifically\b',
]


class CoherenceChecker(Validator):
    name = "check_coherence"

    def __init__(self, min_markers: int = 3):
        self.min_markers = min_markers

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        lower = content.lower()
        found = []
        for pattern in TRANSITION_MARKERS:
            matches = re.findall(pattern, lower)
            found.extend(matches)
        total = len(found)
        if total < self.min_markers:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, total / self.min_markers),
                issues=[
                    f"Only {total} transition markers found "
                    f"(need at least {self.min_markers})"
                ],
                repair_instructions=(
                    "Add transition words (however, furthermore, therefore, etc.) "
                    "between paragraphs and sections"
                ),
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=min(1.0, total / (self.min_markers * 2)),
            issues=[],
            repair_instructions="",
        )
