from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json

router = APIRouter()


@router.websocket("/ws/stream/{task_id}")
async def stream_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            status_data = {"status": "running", "task_id": task_id}
            await websocket.send_text(json.dumps(status_data))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass