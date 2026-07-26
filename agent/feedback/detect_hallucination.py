import re
from agent.feedback.base import Validator, ValidationResult


class HallucinationDetector(Validator):
    name = "detect_hallucination"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        paper_ids = context.get("paper_ids", [])
        needs_citation = re.findall(r'\[citation-needed\]', content)
        if needs_citation:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=max(0.0, 1.0 - len(needs_citation) * 0.2),
                issues=[f"Found {len(needs_citation)} claims needing citation support"],
                repair_instructions="Retrieve supporting papers and add [@paper_id] citations for each claim",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )