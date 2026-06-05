from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .db import create_task, get_task, init_db, list_tasks
from .settings import SETTINGS
from .storage import (
    UploadValidationError,
    ensure_task_dirs,
    ensure_tasks_root,
    get_tasks_root,
    save_uploads,
    validate_uploads,
)
from .tasks import TASK_QUEUE, task_worker

app = FastAPI(title="3D Reconstruction Control Plane")
logger = logging.getLogger("control_plane")
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    return {
        "status": "ok",
        "service": "control-plane",
        "message": "ready",
        "tasks_root": str(get_tasks_root()),
    }


@app.on_event("startup")
async def startup_event() -> None:
    ensure_tasks_root()
    init_db()
    asyncio.create_task(task_worker())


@app.get("/api/config")
async def get_config() -> dict:
    return {
        "tasks_root": str(SETTINGS.tasks_root),
        "max_upload_files": SETTINGS.max_upload_files,
        "max_image_pixels": SETTINGS.max_image_pixels,
        "max_image_long_edge": SETTINGS.max_image_long_edge,
    }


@app.post("/api/tasks")
async def create_task_endpoint(
    files: List[UploadFile] = File(...),
    mode: str = "fast",
) -> dict:
    if not files:
        raise HTTPException(
            status_code=400,
            detail={"error": "No files provided", "hint": "Upload at least one file"},
        )

    if mode not in {"fast", "hq"}:
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid mode", "allowed": ["fast", "hq"]},
        )

    if any(not file.filename for file in files):
        raise HTTPException(
            status_code=400,
            detail={"error": "Empty filename detected", "hint": "Check file names"},
        )

    try:
        validate_uploads(files)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc

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


@app.get("/api/tasks")
async def list_tasks_endpoint(limit: int = 20, offset: int = 0) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Invalid limit")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Invalid offset")
    return {"items": list_tasks(limit=limit, offset=offset)}


@app.get("/api/tasks/{task_id}/output")
async def get_task_output(task_id: str) -> FileResponse:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    output_path = task.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="Output not available")

    output_file = Path(output_path).resolve()
    task_dir = ensure_task_dirs(task_id)["task_dir"].resolve()
    if not output_file.exists() or not output_file.is_file():
        raise HTTPException(status_code=404, detail="Output file missing")
    if task_dir not in output_file.parents:
        raise HTTPException(status_code=400, detail="Invalid output path")

    return FileResponse(output_file, filename=output_file.name)


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
