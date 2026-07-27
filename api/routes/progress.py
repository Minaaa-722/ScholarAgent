import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    from api.main import _harness

    # If no task has ever been started, close immediately
    if not _harness.task_started_at:
        await websocket.close(code=1000, reason="No task started")
        return

    await websocket.accept()
    try:
        while True:
            info = _harness.get_task_info()
            info["task_id"] = task_id
            await websocket.send_text(json.dumps(info))
            if not _harness._pipeline_running:
                # Pipeline finished (complete, error, or interrupted) — stop streaming
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass