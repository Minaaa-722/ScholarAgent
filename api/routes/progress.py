import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    from api.main import _harness

    # 必须先 accept() 再 close()，否则客户端会收到 403/upgrade denied
    await websocket.accept()

    if not _harness.task_started_at:
        await websocket.send_json({"status": "no_task", "message": "No task started"})
        await websocket.close(code=1000, reason="No task started")
        return

    try:
        while True:
            info = _harness.get_task_info()
            info["task_id"] = task_id
            await websocket.send_text(json.dumps(info))
            if not _harness._pipeline_running:
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
