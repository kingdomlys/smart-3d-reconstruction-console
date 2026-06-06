from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.pipelines.registry import list_pipelines

from .settings import BASE_DIR, SETTINGS


PIPELINE_ENV_VARS = {
    "triposr": ["TRIPOSR_CMD", "TRIPOSR_PY", "TRIPOSR_REPO", "TRIPOSR_DEVICE", "USE_REMBG"],
    "colmap": ["COLMAP_CMD", "COLMAP_BIN"],
    "gaussian_splatting": ["DGS_CMD", "DGS_TRAIN_SCRIPT", "DGS_ITERATIONS"],
}

PIPELINE_DEPENDENCIES = {
    "triposr": {"TripoSR source": BASE_DIR / "third_party" / "TripoSR"},
    "colmap": {},
    "gaussian_splatting": {
        "Gaussian Splatting source": BASE_DIR / "third_party" / "gaussian-splatting"
    },
}

PIPELINE_HINTS = {
    "triposr": "Set TRIPOSR_CMD or allow placeholder mode for local smoke tests.",
    "colmap": "Set COLMAP_CMD to run the in-repository wrapper or external COLMAP pipeline.",
    "gaussian_splatting": "Set DGS_CMD to run the 3DGS wrapper or training entry point.",
}


def _configured_env(name: str) -> dict[str, Any]:
    value = os.getenv(name)
    return {
        "name": name,
        "configured": bool(value),
    }


def _dependency_status(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "exists": resolved.exists(),
        "is_dir": resolved.is_dir(),
    }


def _support_summary(pipeline_id: str) -> str:
    if pipeline_id == "triposr":
        return "single image"
    if pipeline_id in {"colmap", "gaussian_splatting"}:
        return "multiple images"
    return "custom"


def get_pipeline_diagnostics() -> dict[str, Any]:
    items = []
    for pipeline in list_pipelines():
        env = [_configured_env(name) for name in PIPELINE_ENV_VARS.get(pipeline.id, [])]
        dependencies = {
            name: _dependency_status(path)
            for name, path in PIPELINE_DEPENDENCIES.get(pipeline.id, {}).items()
        }
        configured_env = [item["name"] for item in env if item["configured"]]
        missing_env = [item["name"] for item in env if not item["configured"]]
        placeholder_enabled = (
            pipeline.id == "triposr" and os.getenv("TRIPOSR_ALLOW_PLACEHOLDER", "0") == "1"
        )

        items.append(
            {
                "id": pipeline.id,
                "name": pipeline.name,
                "output_types": pipeline.output_types,
                "support": _support_summary(pipeline.id),
                "env": env,
                "configured_env": configured_env,
                "missing_env": missing_env,
                "dependencies": dependencies,
                "placeholder_enabled": placeholder_enabled,
                "ready": bool(configured_env) or placeholder_enabled,
                "hint": PIPELINE_HINTS.get(pipeline.id, "Register required environment variables."),
            }
        )

    return {
        "items": items,
        "tasks_root": str(SETTINGS.tasks_root),
        "limits": {
            "max_upload_files": SETTINGS.max_upload_files,
            "max_upload_bytes": SETTINGS.max_upload_bytes,
            "max_image_pixels": SETTINGS.max_image_pixels,
            "max_image_long_edge": SETTINGS.max_image_long_edge,
        },
    }
