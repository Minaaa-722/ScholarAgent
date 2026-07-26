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


def _dedup_by_title(papers: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate papers by title (case-insensitive)."""
    seen = set()
    unique = []
    for p in papers:
        key = p.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return unique, len(papers) - len(unique)
