from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    validator_name: str
    passed: bool
    score: float = 0.0
    issues: list[str] = field(default_factory=list)
    repair_instructions: str = ""


class Validator(ABC):
    name: str = ""

    @abstractmethod
    def validate(self, context: dict[str, Any]) -> ValidationResult:
        ...