from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO, List, Protocol

from .settings import SETTINGS

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
OUTPUT_EXTENSIONS = {".glb", ".ply", ".splat", ".zip", ".txt", ".json", ".bin", ".npz", ".png", ".db"}


class UploadFileLike(Protocol):
    filename: str | None
    file: BinaryIO


class UploadValidationError(ValueError):
    def __init__(self, detail: dict) -> None:
        super().__init__(detail.get("error", "Invalid upload"))
        self.detail = detail


def get_tasks_root() -> Path:
    return SETTINGS.tasks_root


def ensure_tasks_root() -> Path:
    tasks_root = get_tasks_root()
    tasks_root.mkdir(parents=True, exist_ok=True)
    if not tasks_root.is_dir():
        raise RuntimeError(f"TASKS_ROOT is not a directory: {tasks_root}")
    probe = tasks_root / ".write_test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)
    return tasks_root


def _safe_task_dir(task_id: str) -> Path:
    tasks_root = ensure_tasks_root().resolve()
    task_dir = (tasks_root / task_id).resolve()
    if tasks_root not in task_dir.parents:
        raise ValueError("Invalid task id path")
    return task_dir


def ensure_task_dirs(task_id: str) -> dict:
    task_dir = _safe_task_dir(task_id)
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


def read_task_log(task_id: str, max_bytes: int = 256_000) -> str:
    task_dir = _safe_task_dir(task_id)
    logs_path = task_dir / "logs.txt"
    if not logs_path.exists() or not logs_path.is_file():
        return ""

    size = logs_path.stat().st_size
    with logs_path.open("rb") as file:
        if size > max_bytes:
            file.seek(size - max_bytes)
            data = file.read()
            return "[truncated]\n" + data.decode("utf-8", errors="replace")
        return file.read().decode("utf-8", errors="replace")


def list_output_files(task_id: str) -> list[dict]:
    dirs = ensure_task_dirs(task_id)
    outputs_dir = Path(dirs["outputs_dir"]).resolve()
    if not outputs_dir.exists():
        return []

    files = []
    for output_file in sorted(path for path in outputs_dir.rglob("*") if path.is_file()):
        resolved = output_file.resolve()
        if outputs_dir not in resolved.parents:
            continue
        if resolved.suffix.lower() not in OUTPUT_EXTENSIONS:
            continue
        relative_path = resolved.relative_to(outputs_dir).as_posix()
        files.append(
            {
                "name": resolved.name,
                "relative_path": relative_path,
                "type": resolved.suffix.lower().lstrip(".") or "file",
                "size": resolved.stat().st_size,
                "download_url": f"/api/tasks/{task_id}/outputs/{relative_path}",
            }
        )
    return files


def resolve_output_file(task_id: str, relative_path: str) -> Path:
    dirs = ensure_task_dirs(task_id)
    outputs_dir = Path(dirs["outputs_dir"]).resolve()
    target = (outputs_dir / relative_path).resolve()
    if outputs_dir not in target.parents:
        raise FileNotFoundError("Invalid output path")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("Output file missing")
    return target


def _display_name(filename: str | None) -> str:
    if not filename:
        return ""
    return filename.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _safe_upload_name(filename: str | None, index: int) -> str:
    display_name = _display_name(filename)
    suffix = Path(display_name).suffix.lower()
    stem = Path(display_name).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    if not stem:
        stem = f"image_{index + 1}"
    return f"{index + 1:02d}_{stem}{suffix}"


def _validate_image_dimensions(upload: UploadFileLike) -> tuple[int, int]:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise UploadValidationError(
            {
                "error": "Image validation dependency missing",
                "hint": "Install Pillow from backend/requirements.txt",
            }
        ) from exc

    try:
        upload.file.seek(0)
        with Image.open(upload.file) as image:
            width, height = image.size
    except UnidentifiedImageError as exc:
        raise UploadValidationError(
            {
                "error": "Invalid image file",
                "filename": upload.filename,
                "hint": "Upload a readable PNG, JPG, JPEG, or WEBP image",
            }
        ) from exc
    finally:
        upload.file.seek(0)

    return width, height


def _upload_size(upload: UploadFileLike) -> int:
    upload.file.seek(0, 2)
    size = upload.file.tell()
    upload.file.seek(0)
    return size


def validate_uploads(files: List[UploadFileLike]) -> None:
    if len(files) > SETTINGS.max_upload_files:
        raise UploadValidationError(
            {
                "error": "Too many files",
                "max_files": SETTINGS.max_upload_files,
                "received": len(files),
            }
        )

    invalid_files = [
        file.filename
        for file in files
        if Path(_display_name(file.filename)).suffix.lower() not in ALLOWED_EXTENSIONS
    ]
    if invalid_files:
        raise UploadValidationError(
            {
                "error": "Unsupported file type",
                "allowed": sorted(ALLOWED_EXTENSIONS),
                "invalid_files": invalid_files,
            }
        )

    oversize_uploads = []
    for upload in files:
        size = _upload_size(upload)
        if size > SETTINGS.max_upload_bytes:
            oversize_uploads.append(
                {
                    "filename": upload.filename,
                    "size": size,
                }
            )

    if oversize_uploads:
        raise UploadValidationError(
            {
                "error": "Upload file exceeds size limit",
                "max_bytes": SETTINGS.max_upload_bytes,
                "files": oversize_uploads,
            }
        )

    oversize_files = []
    for upload in files:
        width, height = _validate_image_dimensions(upload)
        pixels = width * height
        if pixels > SETTINGS.max_image_pixels or max(width, height) > SETTINGS.max_image_long_edge:
            oversize_files.append(
                {
                    "filename": upload.filename,
                    "width": width,
                    "height": height,
                    "pixels": pixels,
                }
            )

    if oversize_files:
        raise UploadValidationError(
            {
                "error": "Image resolution exceeds 1080p limit",
                "max_pixels": SETTINGS.max_image_pixels,
                "max_long_edge": SETTINGS.max_image_long_edge,
                "files": oversize_files,
            }
        )


def save_uploads(files: List[UploadFileLike], inputs_dir: Path) -> List[Path]:
    saved_paths: List[Path] = []
    inputs_root = inputs_dir.resolve()
    for index, upload in enumerate(files):
        safe_name = _safe_upload_name(upload.filename, index)
        target = (inputs_root / safe_name).resolve()
        if inputs_root not in target.parents:
            raise UploadValidationError(
                {
                    "error": "Invalid upload filename",
                    "filename": upload.filename,
                }
            )
        upload.file.seek(0)
        with target.open("wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        saved_paths.append(target)
    return saved_paths
