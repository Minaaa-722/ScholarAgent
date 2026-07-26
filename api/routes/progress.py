import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from agent.core.state import AgentState

router = APIRouter()


@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    from api.main import _harness

    await websocket.accept()
    try:
        while True:
            info = _harness.get_task_info()
            info["task_id"] = task_id
            await websocket.send_text(json.dumps(info))
            if not _harness._pipeline_running and _harness.state.current_state != AgentState.ERROR:
                # Send one final update and stop
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass