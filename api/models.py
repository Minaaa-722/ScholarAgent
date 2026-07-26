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


class FeedbackRequest(BaseModel):
    category: str = "literature"
    content: str


class MemoryUpdate(BaseModel):
    key: str
    value: str