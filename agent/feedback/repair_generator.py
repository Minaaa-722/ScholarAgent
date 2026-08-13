from agent.feedback.base import ValidationResult


class RepairGenerator:
    def generate(self, results: list[ValidationResult]) -> str:
        instructions = []
        for r in results:
            if not r.passed and r.repair_instructions:
                instructions.append(f"[{r.validator_name}] {r.repair_instructions}")
        return "\n".join(instructions)
