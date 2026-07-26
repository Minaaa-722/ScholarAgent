import re
from agent.feedback.base import Validator, ValidationResult


class CitationChecker(Validator):
    name = "check_citations"

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        paper_ids = context.get("paper_ids", [])

        # Support both [@paper_id] and \cite{ref} formats
        citations_markdown = re.findall(r'\[@(\w+)\]', content)
        citations_latex = re.findall(r'\\cite\{([^}]+)\}', content)
        # Expand \cite{ref1,ref2} into individual refs
        citations_latex_expanded = []
        for group in citations_latex:
            citations_latex_expanded.extend(ref.strip() for ref in group.split(","))

        all_citations = citations_markdown + citations_latex_expanded

        if not all_citations:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                score=0.0,
                issues=["No citations found in the chapter"],
                repair_instructions="Add citations to support claims using \\cite{ref} or [@paper_id] format",
            )

        # Check for citations referencing unknown paper IDs
        if paper_ids:
            missing = [c for c in all_citations if c not in paper_ids]
            if missing:
                score = max(0.0, 1.0 - len(missing) / len(all_citations))
                return ValidationResult(
                    validator_name=self.name,
                    passed=score >= 0.7,
                    score=score,
                    issues=[f"Missing paper references: {', '.join(missing[:5])}"],
                    repair_instructions=f"Add the following papers to the reference list: {', '.join(missing[:5])}",
                )

        return ValidationResult(
            validator_name=self.name,
            passed=True,
            score=1.0,
            issues=[],
            repair_instructions="",
        )