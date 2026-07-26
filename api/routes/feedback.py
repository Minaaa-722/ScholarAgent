from fastapi import APIRouter, Depends
from api.models import FeedbackRequest
from agent.core.harness import Harness
from api.routes.survey import get_harness

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(req: FeedbackRequest, harness: Harness = Depends(get_harness)):
    feedback = {"category": req.category, "content": req.content, "type": "human", "resolved": False}
    return {"status": "received", "feedback": feedback}