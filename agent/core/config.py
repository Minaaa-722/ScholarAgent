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