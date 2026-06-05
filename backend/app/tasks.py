from __future__ import annotations

import asyncio
import logging
import json
import os
import sys
from pathlib import Path
from typing import Dict, Set

from fastapi import WebSocket

from .db import get_task, update_task
from .storage import ensure_task_dirs

logger = logging.getLogger("control_plane")


class TaskQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers: Dict[str, Set[WebSocket]] = {}

    async def enqueue(self, task_id: str) -> None:
        await self.queue.put(task_id)

    async def add_subscriber(self, task_id: str, websocket: WebSocket) -> None:
        self.subscribers.setdefault(task_id, set()).add(websocket)

    async def remove_subscriber(self, task_id: str, websocket: WebSocket) -> None:
        if task_id in self.subscribers:
            self.subscribers[task_id].discard(websocket)
            if not self.subscribers[task_id]:
                self.subscribers.pop(task_id, None)

    async def broadcast(self, task_id: str, payload: dict) -> None:
        sockets = list(self.subscribers.get(task_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.remove_subscriber(task_id, ws)


TASK_QUEUE = TaskQueue()


def _append_log(task_id: str, message: str) -> None:
    dirs = ensure_task_dirs(task_id)
    log_path = Path(dirs["task_dir"]) / "logs.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def _get_tripo_python() -> str:
    override = os.getenv("TRIPOSR_PY")
    if override:
        return override
    return str(Path(sys.executable))


def _get_worker_python() -> str:
    return str(Path(sys.executable))


async def _read_stream(
    stream: asyncio.StreamReader,
    task_id: str,
    label: str,
    on_event: callable | None = None,
    parse_json: bool = False,
) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip()
        _append_log(task_id, f"[{label}] {text}")
        if parse_json and on_event:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            await on_event(payload)


async def _run_pipeline_worker(
    task_id: str,
    pipeline_id: str,
    mode: str,
    on_event: callable,
) -> None:
    dirs = ensure_task_dirs(task_id)
    inputs_dir = Path(dirs["inputs_dir"])
    interim_dir = Path(dirs["interim_dir"])
    outputs_dir = Path(dirs["outputs_dir"])
    logs_path = Path(dirs["task_dir"]) / "logs.txt"
    worker_script = Path(__file__).resolve().parents[1] / "workers" / "run_pipeline.py"
    cmd = [
        _get_tripo_python() if pipeline_id == "triposr" else _get_worker_python(),
        str(worker_script),
        "--pipeline",
        pipeline_id,
        "--task-id",
        task_id,
        "--mode",
        mode,
        "--input-dir",
        str(inputs_dir),
        "--interim-dir",
        str(interim_dir),
        "--output-dir",
        str(outputs_dir),
        "--logs-path",
        str(logs_path),
    ]
    _append_log(task_id, f"[{pipeline_id}] cmd: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout and process.stderr
    await asyncio.gather(
        _read_stream(process.stdout, task_id, f"{pipeline_id}:stdout", on_event, True),
        _read_stream(process.stderr, task_id, f"{pipeline_id}:stderr"),
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError(f"{pipeline_id} pipeline failed")


async def _run_tripo_worker(task_id: str, mode: str, on_event: callable) -> Path:
    await _run_pipeline_worker(task_id, "triposr", mode, on_event)
    output_path = Path(ensure_task_dirs(task_id)["outputs_dir"]) / "output.glb"
    if not output_path.exists():
        raise RuntimeError("TripoSR pipeline did not produce output.glb")
    return output_path


async def _run_colmap_worker(task_id: str, mode: str, on_event: callable) -> Path:
    await _run_pipeline_worker(task_id, "colmap", mode, on_event)
    sparse_dir = Path(ensure_task_dirs(task_id)["interim_dir"]) / "colmap" / "sparse"
    if not sparse_dir.exists():
        raise RuntimeError("COLMAP pipeline did not produce sparse output")
    return sparse_dir


async def _run_3dgs_worker(task_id: str, mode: str, on_event: callable) -> Path:
    await _run_pipeline_worker(task_id, "gaussian_splatting", mode, on_event)
    output_path = Path(ensure_task_dirs(task_id)["outputs_dir"]) / "point_cloud.ply"
    if not output_path.exists():
        raise RuntimeError("3DGS pipeline did not produce point_cloud.ply")
    return output_path


async def task_worker() -> None:
    while True:
        task_id = await TASK_QUEUE.queue.get()
        try:
            task = get_task(task_id)
            if not task:
                logger.error("Task not found", extra={"task_id": task_id})
                TASK_QUEUE.queue.task_done()
                continue
            logger.info("Task started", extra={"task_id": task_id})
            _append_log(task_id, "Task started")
            update_task(task_id, status="Running")
            await TASK_QUEUE.broadcast(task_id, {"status": "Running"})

            if task["image_count"] == 1:
                await TASK_QUEUE.broadcast(
                    task_id, {"status": "Running", "step": "TripoSR", "progress": 0.1}
                )

                async def on_event(payload: dict) -> None:
                    await TASK_QUEUE.broadcast(task_id, payload)

                output_path = await _run_tripo_worker(task_id, task["mode"], on_event)
                update_task(task_id, status="Completed", output_path=str(output_path))
                await TASK_QUEUE.broadcast(
                    task_id,
                    {"status": "Completed", "output_path": str(output_path)},
                )
                _append_log(task_id, "Task completed")
                logger.info("Task completed", extra={"task_id": task_id})
            else:
                await TASK_QUEUE.broadcast(
                    task_id, {"status": "Running", "step": "COLMAP", "progress": 0.1}
                )

                async def on_event(payload: dict) -> None:
                    await TASK_QUEUE.broadcast(task_id, payload)

                await _run_colmap_worker(task_id, task["mode"], on_event)
                await TASK_QUEUE.broadcast(
                    task_id, {"status": "Running", "step": "3DGS", "progress": 0.7}
                )
                output_path = await _run_3dgs_worker(task_id, task["mode"], on_event)
                update_task(task_id, status="Completed", output_path=str(output_path))
                await TASK_QUEUE.broadcast(
                    task_id, {"status": "Completed", "output_path": str(output_path)}
                )
                _append_log(task_id, "Task completed")
                logger.info("Task completed", extra={"task_id": task_id})
        except Exception as exc:
            update_task(task_id, status="Failed", error=str(exc))
            await TASK_QUEUE.broadcast(task_id, {"status": "Failed", "error": str(exc)})
            _append_log(task_id, f"Task failed: {exc}")
            logger.exception("Task failed", extra={"task_id": task_id})
        finally:
            TASK_QUEUE.queue.task_done()
