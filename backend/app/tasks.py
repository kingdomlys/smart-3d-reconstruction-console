from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Set

from fastapi import WebSocket

from .db import update_task
from .storage import ensure_task_dirs


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


async def task_worker() -> None:
    while True:
        task_id = await TASK_QUEUE.queue.get()
        try:
            update_task(task_id, status="Running")
            await TASK_QUEUE.broadcast(task_id, {"status": "Running"})

            steps = ["Preparing", "Routing", "Processing", "Finalizing"]
            for idx, step in enumerate(steps, start=1):
                await asyncio.sleep(1)
                await TASK_QUEUE.broadcast(
                    task_id,
                    {"status": "Running", "step": step, "progress": idx / len(steps)},
                )

            dirs = ensure_task_dirs(task_id)
            output_path = Path(dirs["outputs_dir"]) / "placeholder.txt"
            output_path.write_text("Placeholder output", encoding="utf-8")

            update_task(task_id, status="Completed", output_path=str(output_path))
            await TASK_QUEUE.broadcast(
                task_id, {"status": "Completed", "output_path": str(output_path)}
            )
        except Exception as exc:
            update_task(task_id, status="Failed", error=str(exc))
            await TASK_QUEUE.broadcast(task_id, {"status": "Failed", "error": str(exc)})
        finally:
            TASK_QUEUE.queue.task_done()
