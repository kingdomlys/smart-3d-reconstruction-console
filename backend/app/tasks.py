from __future__ import annotations

import asyncio
import logging
import json
import os
import subprocess
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


async def _run_tripo_worker(task_id: str, on_event: callable) -> Path:
    dirs = ensure_task_dirs(task_id)
    inputs_dir = Path(dirs["inputs_dir"])
    interim_dir = Path(dirs["interim_dir"])
    outputs_dir = Path(dirs["outputs_dir"])
    worker_script = Path(__file__).resolve().parents[1] / "workers" / "worker_tripo.py"
    cmd = [
        _get_tripo_python(),
        str(worker_script),
        "--input-dir",
        str(inputs_dir),
        "--interim-dir",
        str(interim_dir),
        "--output-dir",
        str(outputs_dir),
    ]
    _append_log(task_id, f"[tripo] cmd: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout and process.stderr

    await asyncio.gather(
        _read_stream(process.stdout, task_id, "tripo:stdout", on_event, True),
        _read_stream(process.stderr, task_id, "tripo:stderr"),
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError("TripoSR worker failed")
    output_path = outputs_dir / "output.glb"
    if not output_path.exists():
        raise RuntimeError("TripoSR worker did not produce output.glb")
    return output_path


async def _run_colmap_worker(task_id: str, on_event: callable) -> Path:
    dirs = ensure_task_dirs(task_id)
    inputs_dir = Path(dirs["inputs_dir"])
    interim_dir = Path(dirs["interim_dir"])
    worker_script = Path(__file__).resolve().parents[1] / "workers" / "worker_colmap.py"
    cmd = [
        _get_worker_python(),
        str(worker_script),
        "--input-dir",
        str(inputs_dir),
        "--interim-dir",
        str(interim_dir),
    ]
    _append_log(task_id, f"[colmap] cmd: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout and process.stderr
    await asyncio.gather(
        _read_stream(process.stdout, task_id, "colmap:stdout", on_event, True),
        _read_stream(process.stderr, task_id, "colmap:stderr"),
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError("COLMAP worker failed")
    sparse_dir = interim_dir / "colmap" / "sparse"
    if not sparse_dir.exists():
        raise RuntimeError("COLMAP worker did not produce sparse output")
    return sparse_dir


async def _run_3dgs_worker(task_id: str, on_event: callable) -> Path:
    dirs = ensure_task_dirs(task_id)
    interim_dir = Path(dirs["interim_dir"])
    outputs_dir = Path(dirs["outputs_dir"])
    worker_script = Path(__file__).resolve().parents[1] / "workers" / "worker_3dgs.py"
    cmd = [
        _get_worker_python(),
        str(worker_script),
        "--interim-dir",
        str(interim_dir),
        "--output-dir",
        str(outputs_dir),
        "--iterations",
        "1000",
    ]
    _append_log(task_id, f"[3dgs] cmd: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout and process.stderr
    await asyncio.gather(
        _read_stream(process.stdout, task_id, "3dgs:stdout", on_event, True),
        _read_stream(process.stderr, task_id, "3dgs:stderr"),
    )
    return_code = await process.wait()
    if return_code != 0:
        raise RuntimeError("3DGS worker failed")
    output_path = outputs_dir / "point_cloud.ply"
    if not output_path.exists():
        raise RuntimeError("3DGS worker did not produce point_cloud.ply")
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

                output_path = await _run_tripo_worker(task_id, on_event)
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

                await _run_colmap_worker(task_id, on_event)
                await TASK_QUEUE.broadcast(
                    task_id, {"status": "Running", "step": "3DGS", "progress": 0.7}
                )
                output_path = await _run_3dgs_worker(task_id, on_event)
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
