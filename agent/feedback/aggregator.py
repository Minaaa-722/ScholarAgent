from dataclasses import dataclass, field
from agent.feedback.base import ValidationResult


@dataclass
class FeedbackReport:
    overall_passed: bool
    overall_score: float
    failed_validators: list[str] = field(default_factory=list)
    all_results: list[ValidationResult] = field(default_factory=list)


class FeedbackAggregator:
    def __init__(self, pass_threshold: float = 0.7):
        self.pass_threshold = pass_threshold

    def aggregate(self, results: list[ValidationResult]) -> FeedbackReport:
        if not results:
            return FeedbackReport(overall_passed=True, overall_score=1.0)
        scores = [r.score for r in results]
        overall_score = sum(scores) / len(scores)
        failed = [r.validator_name for r in results if not r.passed]
        return FeedbackReport(
            overall_passed=overall_score >= self.pass_threshold,
            overall_score=overall_score,
            failed_validators=failed,
            all_results=results,
        )
