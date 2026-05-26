from __future__ import annotations

import asyncio
import logging
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
    return str(Path(sys.executable))


def _run_tripo_worker(task_id: str) -> Path:
    dirs = ensure_task_dirs(task_id)
    inputs_dir = Path(dirs["inputs_dir"])
    outputs_dir = Path(dirs["outputs_dir"])
    worker_script = Path(__file__).resolve().parents[1] / "workers" / "worker_tripo.py"
    cmd = [
        _get_tripo_python(),
        str(worker_script),
        "--input-dir",
        str(inputs_dir),
        "--output-dir",
        str(outputs_dir),
    ]
    _append_log(task_id, f"[tripo] cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        _append_log(task_id, f"[tripo][stdout] {result.stdout.strip()}")
    if result.stderr:
        _append_log(task_id, f"[tripo][stderr] {result.stderr.strip()}")
    if result.returncode != 0:
        raise RuntimeError("TripoSR worker failed")
    output_path = outputs_dir / "output.glb"
    if not output_path.exists():
        raise RuntimeError("TripoSR worker did not produce output.glb")
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
                    task_id, {"status": "Running", "step": "TripoSR", "progress": 0.2}
                )
                output_path = _run_tripo_worker(task_id)
                update_task(task_id, status="Completed", output_path=str(output_path))
                await TASK_QUEUE.broadcast(
                    task_id,
                    {"status": "Completed", "output_path": str(output_path)},
                )
                _append_log(task_id, "Task completed")
                logger.info("Task completed", extra={"task_id": task_id})
            else:
                steps = ["Preparing", "Routing", "Processing", "Finalizing"]
                for idx, step in enumerate(steps, start=1):
                    await asyncio.sleep(1)
                    await TASK_QUEUE.broadcast(
                        task_id,
                        {"status": "Running", "step": step, "progress": idx / len(steps)},
                    )
                    logger.info(
                        "Task progress",
                        extra={"task_id": task_id, "step": step, "progress": idx / len(steps)},
                    )
                    _append_log(task_id, f"Progress: {step}")

                dirs = ensure_task_dirs(task_id)
                output_path = Path(dirs["outputs_dir"]) / "placeholder.txt"
                output_path.write_text("Placeholder output", encoding="utf-8")

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
