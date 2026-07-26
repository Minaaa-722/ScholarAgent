from fastapi import APIRouter, Depends
from api.models import SurveyRequest, SurveyResponse
from agent.core.harness import Harness

router = APIRouter(prefix="/api/survey", tags=["survey"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


@router.post("", response_model=SurveyResponse)
async def create_survey(req: SurveyRequest, harness: Harness = Depends(get_harness)):
    harness.start(topic=req.topic, keywords=req.keywords, goal=req.goal)
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.get("/status", response_model=SurveyResponse)
async def get_status(harness: Harness = Depends(get_harness)):
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/interrupt", response_model=SurveyResponse)
async def interrupt_survey(harness: Harness = Depends(get_harness)):
    harness.interrupt()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.post("/resume", response_model=SurveyResponse)
async def resume_survey(harness: Harness = Depends(get_harness)):
    harness.resume()
    info = harness.get_task_info()
    return SurveyResponse(**info)