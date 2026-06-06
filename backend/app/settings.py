from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = BASE_DIR / "backend"
ENV_PATH = BACKEND_DIR / ".env"


def _load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_path(name: str, default: Path) -> Path:
    raw_value = os.getenv(name)
    if not raw_value:
        return default.resolve()

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


_load_env_file()


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    tasks_root: Path
    max_upload_files: int
    max_upload_bytes: int
    max_image_pixels: int
    max_image_long_edge: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_env_int("APP_PORT", 8000),
            tasks_root=_env_path("TASKS_ROOT", BASE_DIR / "data" / "tasks"),
            max_upload_files=_env_int("MAX_UPLOAD_FILES", 16),
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            max_image_pixels=_env_int("MAX_IMAGE_PIXELS", 1920 * 1080),
            max_image_long_edge=_env_int("MAX_IMAGE_LONG_EDGE", 1920),
        )


SETTINGS = Settings.from_env()
