from __future__ import annotations

import asyncio
import logging
from typing import List
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from .db import create_task, get_task, init_db
from .storage import ensure_task_dirs, save_uploads
from .tasks import TASK_QUEUE, task_worker

app = FastAPI(title="3D Reconstruction Control Plane")
logger = logging.getLogger("control_plane")
logging.basicConfig(level=logging.INFO)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": "control-plane"}


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    asyncio.create_task(task_worker())


@app.post("/api/tasks")
async def create_task_endpoint(
    files: List[UploadFile] = File(...),
    mode: str = "fast",
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if mode not in {"fast", "hq"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if any(not file.filename for file in files):
        raise HTTPException(status_code=400, detail="Empty filename detected")

    task_id = str(uuid4())
    dirs = ensure_task_dirs(task_id)
    save_uploads(files, dirs["inputs_dir"])

    task = create_task(task_id=task_id, mode=mode, image_count=len(files))
    await TASK_QUEUE.enqueue(task_id)
    logger.info("Task queued", extra={"task_id": task_id, "mode": mode})

    return task


@app.get("/api/tasks/{task_id}")
async def get_task_endpoint(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.websocket("/ws/tasks/{task_id}")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    await TASK_QUEUE.add_subscriber(task_id, websocket)
    task = get_task(task_id)
    if task:
        await websocket.send_json(task)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await TASK_QUEUE.remove_subscriber(task_id, websocket)
