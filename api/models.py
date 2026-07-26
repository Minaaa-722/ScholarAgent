from pydantic import BaseModel
from typing import Optional


class SurveyRequest(BaseModel):
    topic: str
    keywords: str = ""
    goal: str = ""
    max_papers: int = 20


class SurveyResponse(BaseModel):
    topic: str
    status: str
    keywords: list[str] = []
    goal: str = ""
    max_papers: int = 20
    retry_count: int = 0
    has_warnings: bool = False


class FeedbackRequest(BaseModel):
    category: str = "literature"
    content: str


class MemoryUpdate(BaseModel):
    key: str
    value: str