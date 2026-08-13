from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    arxiv_ti_max_results: int = 20
    arxiv_abs_max_results: int = 20
    ss_max_results: int = 20

    rrf_enabled: bool = True
    rrf_k: int = 60

    rank_alpha: float = 0.5
    rank_beta: float = 0.3
    rank_gamma: float = 0.2

    domain_cat_map: dict = field(default_factory=lambda: {
        "image": "cs.CV", "vision": "cs.CV", "visual": "cs.CV",
        "object detection": "cs.CV", "segmentation": "cs.CV",
        "face": "cs.CV", "video": "cs.CV", "pose": "cs.CV",
        "language": "cs.CL", "text": "cs.CL", "translation": "cs.CL",
        "sentence": "cs.CL", "word": "cs.CL",
        "token": "cs.CL", "bert": "cs.CL", "gpt": "cs.CL",
        "llm": "cs.CL",
    })
    domain_fallback_cat: str = "cs.AI"

    relevance_confidence_min: float = 0.6
    abstract_missing_max_confidence: float = 0.6

    fallback_phase6_min_papers: int = 10
    fallback_phase7_min_papers: int = 5
    fallback_phase7_max_results: int = 20

    # Year-segmented SS search
    ss_year_segments: list[dict] = field(default_factory=lambda: [
        {"start": 2025, "end": 2026, "min_citation_count": 0, "label": "frontier"},
        {"start": 2022, "end": 2024, "min_citation_count": 3, "label": "mid"},
        {"start": 0,    "end": 2021, "min_citation_count": 5, "label": "foundational"},
    ])
    ss_frontier_max_results: int = 30
    ss_mid_max_results: int = 20
    ss_foundational_max_results: int = 15

    # Contribution type weights
    rank_contribution_strong: float = 1.0
    rank_contribution_extension: float = 0.6
    rank_contribution_application: float = 0.2
    rank_contribution_default: float = 0.5

    # Time decay
    rank_decay_factor: float = 0.15
    rank_current_year: int = 2026

    # Stratified sampling quotas
    stratify_frontier_quota: float = 0.30
    stratify_mid_quota: float = 0.40
    stratify_classic_quota: float = 0.30
    stratify_frontier_start: int = 2025
    stratify_mid_start: int = 2022