from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Any


class GuardrailVerdict(Enum):
    PASS = "pass"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class GuardrailResult:
    verdict: GuardrailVerdict
    message: str = ""
    guardrail_name: str = ""


class Guardrail(ABC):
    name: str = ""

    @abstractmethod
    def check(self, context: dict[str, Any]) -> GuardrailResult:
        ...
