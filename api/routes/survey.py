from fastapi import APIRouter, Depends
from api.models import SurveyRequest, SurveyResponse
from agent.core.harness import Harness

router = APIRouter(prefix="/api/survey", tags=["survey"])


def get_harness() -> Harness:
    from api.main import _harness
    return _harness


@router.post("", response_model=SurveyResponse)
async def create_survey(req: SurveyRequest, harness: Harness = Depends(get_harness)):
    harness.run_async(topic=req.topic, keywords=req.keywords, goal=req.goal)
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


@router.post("/restart", response_model=SurveyResponse)
async def restart_survey(harness: Harness = Depends(get_harness)):
    harness.restart()
    info = harness.get_task_info()
    return SurveyResponse(**info)


@router.get("/paper")
async def get_paper(harness: Harness = Depends(get_harness)):
    return harness.get_paper()


@router.get("/log")
async def get_execution_log(harness: Harness = Depends(get_harness)):
    return {"execution_log": harness.get_execution_log()}