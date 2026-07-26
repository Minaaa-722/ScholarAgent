from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Tool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> ToolResult:
        ...