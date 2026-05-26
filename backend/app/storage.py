from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import UploadFile

BASE_DIR = Path(__file__).resolve().parents[2]
TASKS_ROOT = BASE_DIR / "data" / "tasks"


def ensure_task_dirs(task_id: str) -> dict:
    task_dir = TASKS_ROOT / task_id
    inputs_dir = task_dir / "inputs"
    interim_dir = task_dir / "interim"
    outputs_dir = task_dir / "outputs"
    for path in (inputs_dir, interim_dir, outputs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "task_dir": task_dir,
        "inputs_dir": inputs_dir,
        "interim_dir": interim_dir,
        "outputs_dir": outputs_dir,
    }


def save_uploads(files: List[UploadFile], inputs_dir: Path) -> List[Path]:
    saved_paths: List[Path] = []
    for upload in files:
        target = inputs_dir / upload.filename
        with target.open("wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        saved_paths.append(target)
    return saved_paths
