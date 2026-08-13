from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Paper:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0

    arxiv_id: str = ""
    source: str = ""
    url: str = ""
    venue: str = ""

    citation_count: int = 0
    doi: str = ""
    paper_id: str = ""
    categories: list[str] = field(default_factory=list)

    hit_channels: list[str] = field(default_factory=list)

    relevance: str = "weak"
    relevance_confidence: float = 0.0
    relevance_reason: str = ""

    composite_score: float = 0.0

    search_source_queries: list[str] = field(default_factory=list)

    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Paper":
        return Paper(
            **{k: v for k, v in data.items() if k in Paper.__dataclass_fields__}
        )