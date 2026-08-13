import re
from agent.feedback.base import Validator, ValidationResult


INFORMAL_PATTERNS = [
    (r'\bsuper\b', 'informal intensifier "super"'),
    (r'\bawesome\b', 'informal word "awesome"'),
    (r'\bcool\b', 'informal word "cool"'),
    (r'\bamazing\b', 'informal word "amazing"'),
    (r'\bbasically\b', 'informal filler "basically"'),
    (r'\bkinda\b', 'informal word "kinda"'),
    (r'\bsorta\b', 'informal word "sorta"'),
    (r'\bstuff\b', 'vague term "stuff"'),
    (r'\ba lot\b', 'informal phrase "a lot"'),
    (r'\breally\b', 'informal intensifier "really"'),
    (r'\bvery\b', 'weak intensifier "very"'),
    (r'\bthings?\b', 'vague term "thing/things"'),
]


class LanguagePolisher(Validator):
    name = "polish_language"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        lower = content.lower()
        issues = []
        for pattern, desc in INFORMAL_PATTERNS:
            if re.search(pattern, lower):
                issues.append(f"Replace {desc} with formal academic language")
        if issues:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, 1.0 - len(issues) * 0.15),
                issues=issues[:5],
                repair_instructions=(
                    "Replace informal expressions with academic language "
                    "suitable for IEEEtran conference"
                ),
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )
