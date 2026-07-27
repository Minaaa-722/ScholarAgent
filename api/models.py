from pydantic import BaseModel


class SurveyRequest(BaseModel):
    topic: str
    keywords: str = ""
    goal: str = ""
    max_papers: int = 20


class SurveyResponse(BaseModel):
    topic: str = ""
    status: str
    keywords: list[str] = []
    goal: str = ""
    max_papers: int = 20
    pipeline_running: bool = False
    current_stage: str = ""
    current_message: str = ""
    retry_count: int = 0
    has_warnings: bool = False
    task_started_at: str = ""
    error: str = ""
    pipeline_retry_count: int = 0
    last_failed_stage: str = ""


class FeedbackRequest(BaseModel):
    category: str = "literature"
    content: str


class MemoryUpdate(BaseModel):
    key: str
    value: str


class PaperItem(BaseModel):
    title: str
    authors: str
    year: str = ""
    citations: int = 0
    source: str = ""
    paper_index: int = 0


class PaperListResponse(BaseModel):
    papers: list[PaperItem]
    total: int


class GraphNode(BaseModel):
    id: int
    label: str
    group: str
    size: int


class GraphLink(BaseModel):
    source: int
    target: int
    weight: int = 1


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    links: list[GraphLink]


class HistoryItem(BaseModel):
    """Summary of a completed task for the history list."""
    id: str
    topic: str
    keywords: list[str] = []
    goal: str = ""
    status: str = ""
    timestamp: str = ""
    paper_count: int = 0
    has_warnings: bool = False
    rounds: int = 0


class HistoryDetail(HistoryItem):
    """Full detail of a completed task, including papers and final paper."""
    papers: list[PaperItem] = []
    final_paper: str = ""