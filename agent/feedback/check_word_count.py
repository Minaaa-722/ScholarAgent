from agent.feedback.base import Validator, ValidationResult


class WordCountChecker(Validator):
    name = "check_word_count"

    def __init__(self, min_words: int = 100, max_words: int = 5000):
        self.min_words = min_words
        self.max_words = max_words

    def validate(self, context: dict) -> ValidationResult:
        content = context.get("content", "")
        word_count = len(content.split())
        issues = []
        if word_count < self.min_words:
            issues.append(f"Chapter too short: {word_count} words (min: {self.min_words})")
        if word_count > self.max_words:
            issues.append(f"Chapter too long: {word_count} words (max: {self.max_words})")
        passed = len(issues) == 0
        score = 1.0
        if word_count < self.min_words:
            score = max(0.0, word_count / self.min_words)
        elif word_count > self.max_words:
            score = max(0.0, 1.0 - (word_count - self.max_words) / self.max_words)
        repair = ""
        if issues:
            if word_count < self.min_words:
                repair = f"Expand the chapter to at least {self.min_words} words"
            else:
                repair = f"Trim the chapter to at most {self.max_words} words"
        return ValidationResult(
            validator_name=self.name,
            passed=passed,
            score=score,
            issues=issues,
            repair_instructions=repair,
        )
