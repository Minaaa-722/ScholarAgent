import re
from agent.feedback.base import Validator, ValidationResult


class CitationChecker(Validator):
    name = "check_citations"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        paper_ids = context.get("paper_ids", [])
        citations = re.findall(r'\[@(\w+)\]', content)
        if not citations:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=0.0,
                issues=["No citations found in the chapter"],
                repair_instructions="Add citations to support claims using [@paper_id] format",
            )
        missing = [c for c in citations if c not in paper_ids]
        if missing:
            score = max(0.0, 1.0 - len(missing) / len(citations))
            return ValidationResult(
                validator_name=self.name,
                passed=score >= 0.7,
                score=score,
                issues=[f"Missing paper references: {', '.join(missing)}"],
                repair_instructions=f"Add the following papers to the reference list: {', '.join(missing)}",
            )
        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )
