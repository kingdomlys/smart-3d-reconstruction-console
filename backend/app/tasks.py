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
from .storage import ensure_task_dirs, list_output_files

logger = logging.getLogger("control_plane")


class TaskQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers: Dict[str, Set[WebSocket]] = {}
        self.cancel_requested: Set[str] = set()
        self.running_processes: Dict[str, asyncio.subprocess.Process] = {}

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

    async def request_cancel(self, task_id: str) -> None:
        self.cancel_requested.add(task_id)
        process = self.running_processes.get(task_id)
        if process and process.returncode is None:
            process.terminate()

    def clear_cancel(self, task_id: str) -> None:
        self.cancel_requested.discard(task_id)

    def is_cancel_requested(self, task_id: str) -> bool:
        return task_id in self.cancel_requested

    def is_cancellation_in_progress(self, task_id: str) -> bool:
        return task_id in self.cancel_requested or task_id in self.running_processes

    def set_running_process(self, task_id: str, process: asyncio.subprocess.Process) -> None:
        self.running_processes[task_id] = process

    def clear_running_process(self, task_id: str, process: asyncio.subprocess.Process) -> None:
        if self.running_processes.get(task_id) is process:
            self.running_processes.pop(task_id, None)


TASK_QUEUE = TaskQueue()


class TaskCanceled(RuntimeError):
    pass


class PipelineProcessError(RuntimeError):
    def __init__(self, pipeline_id: str, return_code: int, summary: str) -> None:
        self.pipeline_id = pipeline_id
        self.return_code = return_code
        self.summary = summary
        super().__init__(summary)


class StreamTail:
    def __init__(self, max_lines: int = 12) -> None:
        self.max_lines = max_lines
        self.lines: list[str] = []

    def add(self, label: str, text: str) -> None:
        if not text:
            return
        self.lines.append(f"[{label}] {text}")
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]

    def summary(self, max_chars: int = 1800) -> str:
        text = "\n".join(self.lines).strip()
        if len(text) <= max_chars:
            return text
        return "[truncated]\n" + text[-max_chars:]


def _error_summary(message: str, max_chars: int = 1800) -> str:
    text = " ".join(message.split()) if "\n" not in message else message.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "... [truncated]"


def _raise_if_canceled(task_id: str) -> None:
    task = get_task(task_id)
    if TASK_QUEUE.is_cancel_requested(task_id) or (task and task["status"] == "Canceled"):
        raise TaskCanceled("Task canceled by user")


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


def _multi_image_pipeline() -> str:
    return os.getenv("MULTI_IMAGE_PIPELINE", "vggt").strip().lower() or "vggt"


def _task_pipeline_id(task: dict) -> str:
    pipeline_id = (task.get("pipeline_id") or "").strip().lower()
    if pipeline_id:
        return pipeline_id
    if task["image_count"] == 1:
        return "triposr"
    return _multi_image_pipeline()


def _task_output_payload(task_id: str, output_path: Path) -> dict:
    task = get_task(task_id) or {}
    outputs = list_output_files(task_id)
    output_types = sorted({item["type"] for item in outputs})
    return {
        "status": "Completed",
        "pipeline_id": task.get("pipeline_id"),
        "output_path": str(output_path),
        "outputs": outputs,
        "output_types": output_types,
    }


async def cancel_task(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        raise KeyError(task_id)
    if task["status"] not in {"Pending", "Running"}:
        raise ValueError("Task is not active")

    await TASK_QUEUE.request_cancel(task_id)
    update_task(task_id, status="Canceled", output_path=task.get("output_path"), error="Canceled by user")
    updated = get_task(task_id) or {}
    _append_log(task_id, "Task canceled by user")
    await TASK_QUEUE.broadcast(task_id, updated)
    return updated


async def _read_stream(
    stream: asyncio.StreamReader,
    task_id: str,
    label: str,
    tail: StreamTail,
    on_event: callable | None = None,
    parse_json: bool = False,
) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").rstrip()
        tail.add(label, text)
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
        limit=1024 * 1024,
    )
    assert process.stdout and process.stderr
    stream_tail = StreamTail()
    TASK_QUEUE.set_running_process(task_id, process)
    try:
        await asyncio.gather(
            _read_stream(process.stdout, task_id, f"{pipeline_id}:stdout", stream_tail, on_event, True),
            _read_stream(process.stderr, task_id, f"{pipeline_id}:stderr", stream_tail),
        )
        return_code = await process.wait()
    finally:
        TASK_QUEUE.clear_running_process(task_id, process)
    if TASK_QUEUE.is_cancel_requested(task_id):
        raise TaskCanceled("Task canceled by user")
    if return_code != 0:
        details = stream_tail.summary()
        message = f"{pipeline_id} pipeline failed with exit code {return_code}"
        if details:
            message = f"{message}\n{details}"
        raise PipelineProcessError(pipeline_id, return_code, _error_summary(message))


async def _run_tripo_worker(task_id: str, mode: str, on_event: callable) -> Path:
    _raise_if_canceled(task_id)
    await _run_pipeline_worker(task_id, "triposr", mode, on_event)
    _raise_if_canceled(task_id)
    output_path = Path(ensure_task_dirs(task_id)["outputs_dir"]) / "output.glb"
    if not output_path.exists():
        raise RuntimeError("TripoSR pipeline did not produce output.glb")
    return output_path


async def _run_colmap_worker(task_id: str, mode: str, on_event: callable) -> Path:
    _raise_if_canceled(task_id)
    await _run_pipeline_worker(task_id, "colmap", mode, on_event)
    _raise_if_canceled(task_id)
    output_path = Path(ensure_task_dirs(task_id)["outputs_dir"]) / "colmap" / "sparse.ply"
    if not output_path.exists():
        raise RuntimeError("COLMAP pipeline did not produce colmap/sparse.ply")
    return output_path


async def _run_3dgs_worker(task_id: str, mode: str, on_event: callable) -> Path:
    _raise_if_canceled(task_id)
    await _run_pipeline_worker(task_id, "gaussian_splatting", mode, on_event)
    _raise_if_canceled(task_id)
    output_path = Path(ensure_task_dirs(task_id)["outputs_dir"]) / "point_cloud.ply"
    if not output_path.exists():
        raise RuntimeError("3DGS pipeline did not produce point_cloud.ply")
    return output_path


async def _run_vggt_worker(task_id: str, mode: str, on_event: callable) -> Path:
    _raise_if_canceled(task_id)
    await _run_pipeline_worker(task_id, "vggt", mode, on_event)
    _raise_if_canceled(task_id)
    outputs_dir = Path(ensure_task_dirs(task_id)["outputs_dir"])
    ply_outputs = sorted(outputs_dir.glob("*.ply"))
    if not ply_outputs:
        raise RuntimeError("VGGT pipeline did not produce a PLY point cloud")
    return ply_outputs[0]


async def task_worker() -> None:
    while True:
        task_id = await TASK_QUEUE.queue.get()
        try:
            task = get_task(task_id)
            if not task:
                logger.error("Task not found", extra={"task_id": task_id})
                TASK_QUEUE.queue.task_done()
                continue
            if task["status"] == "Canceled" or TASK_QUEUE.is_cancel_requested(task_id):
                _append_log(task_id, "Canceled task skipped")
                await TASK_QUEUE.broadcast(task_id, get_task(task_id) or {"status": "Canceled"})
                continue
            logger.info("Task started", extra={"task_id": task_id})
            _append_log(task_id, "Task started")
            selected_pipeline = _task_pipeline_id(task)
            update_task(task_id, status="Running")
            await TASK_QUEUE.broadcast(task_id, {"status": "Running", "pipeline_id": selected_pipeline})

            if selected_pipeline == "triposr":
                await TASK_QUEUE.broadcast(
                    task_id,
                    {
                        "status": "Running",
                        "pipeline_id": selected_pipeline,
                        "step": "TripoSR",
                        "progress": 0.1,
                    },
                )

                async def on_event(payload: dict) -> None:
                    await TASK_QUEUE.broadcast(task_id, payload)

                output_path = await _run_tripo_worker(task_id, task["mode"], on_event)
                _raise_if_canceled(task_id)
                update_task(task_id, status="Completed", output_path=str(output_path))
                await TASK_QUEUE.broadcast(task_id, _task_output_payload(task_id, output_path))
                _append_log(task_id, "Task completed")
                logger.info("Task completed", extra={"task_id": task_id})
            else:
                async def on_event(payload: dict) -> None:
                    await TASK_QUEUE.broadcast(task_id, payload)

                if selected_pipeline == "vggt":
                    await TASK_QUEUE.broadcast(
                        task_id,
                        {
                            "status": "Running",
                            "pipeline_id": selected_pipeline,
                            "step": "VGGT",
                            "progress": 0.1,
                        },
                    )
                    output_path = await _run_vggt_worker(task_id, task["mode"], on_event)
                elif selected_pipeline == "colmap":
                    await TASK_QUEUE.broadcast(
                        task_id,
                        {
                            "status": "Running",
                            "pipeline_id": selected_pipeline,
                            "step": "COLMAP",
                            "progress": 0.1,
                        },
                    )
                    output_path = await _run_colmap_worker(task_id, task["mode"], on_event)
                    if not output_path.exists():
                        raise RuntimeError("COLMAP pipeline did not produce a previewable PLY")
                else:
                    raise ValueError(f"Unsupported pipeline: {selected_pipeline}")
                _raise_if_canceled(task_id)
                update_task(task_id, status="Completed", output_path=str(output_path))
                await TASK_QUEUE.broadcast(task_id, _task_output_payload(task_id, output_path))
                _append_log(task_id, "Task completed")
                logger.info("Task completed", extra={"task_id": task_id})
        except TaskCanceled as exc:
            update_task(task_id, status="Canceled", output_path=None, error=str(exc))
            updated = get_task(task_id) or {"status": "Canceled", "error": str(exc)}
            await TASK_QUEUE.broadcast(task_id, updated)
            _append_log(task_id, f"Task canceled: {exc}")
            logger.info("Task canceled", extra={"task_id": task_id})
        except Exception as exc:
            error = _error_summary(str(exc))
            update_task(task_id, status="Failed", error=error)
            updated = get_task(task_id) or {"status": "Failed", "error": error}
            await TASK_QUEUE.broadcast(task_id, updated)
            _append_log(task_id, f"Task failed: {error}")
            logger.exception("Task failed", extra={"task_id": task_id})
        finally:
            TASK_QUEUE.clear_cancel(task_id)
            TASK_QUEUE.queue.task_done()
