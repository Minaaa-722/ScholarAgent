from fastapi import APIRouter, Depends, HTTPException
from api.models import FeedbackRequest
from agent.core.harness import Harness
from api.routes.survey import get_harness

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(req: FeedbackRequest, harness: Harness = Depends(get_harness)):
    if not harness._pipeline_running:
        raise HTTPException(status_code=400, detail="Pipeline is not running")
    feedback = harness.submit_human_feedback(req.category, req.content)
    return {"status": "queued", "feedback": feedback}


@router.get("/pending")
async def get_pending_feedback(harness: Harness = Depends(get_harness)):
    return {
        "queue": harness.feedback_queue,
        "history": harness.feedback_history,
    }
