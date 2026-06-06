from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.pipelines.registry import list_pipelines

from .settings import BASE_DIR, SETTINGS
from .upload_limits import limits_for_pipeline, limits_payload_for_pipelines


PIPELINE_ENV_VARS = {
    "triposr": ["TRIPOSR_CMD", "TRIPOSR_PY", "TRIPOSR_REPO", "TRIPOSR_DEVICE", "USE_REMBG"],
    "vggt": [
        "VGGT_PY",
        "VGGT_REPO",
        "VGGT_CHECKPOINT",
        "VGGT_MAX_IMAGES",
        "VGGT_CONF_PERCENTILE",
        "VGGT_SOURCE",
    ],
    "colmap": ["COLMAP_CMD", "COLMAP_BIN"],
    "colmap_dense": [
        "COLMAP_DENSE_CMD",
        "COLMAP_CMD",
        "COLMAP_BIN",
        "COLMAP_DENSE_MAX_IMAGE_SIZE",
    ],
    "gaussian_splatting": ["DGS_CMD", "DGS_TRAIN_SCRIPT", "DGS_ITERATIONS"],
}

PIPELINE_DEPENDENCIES = {
    "triposr": {"TripoSR source": BASE_DIR / "third_party" / "TripoSR"},
    "vggt": {"VGGT source": BASE_DIR.parent / "vggt"},
    "colmap": {"COLMAP CUDA build": BASE_DIR.parent / "colmap" / "colmap-x64-windows-cuda"},
    "colmap_dense": {
        "COLMAP CUDA build": BASE_DIR.parent / "colmap" / "colmap-x64-windows-cuda"
    },
    "gaussian_splatting": {
        "Gaussian Splatting source": BASE_DIR / "third_party" / "gaussian-splatting"
    },
}

PIPELINE_HINTS = {
    "triposr": "Set TRIPOSR_CMD or allow placeholder mode for local smoke tests.",
    "vggt": "Set VGGT_PY to the vggt conda python and VGGT_REPO to the local VGGT checkout.",
    "colmap": "Set COLMAP_CMD to run the in-repository wrapper or external COLMAP pipeline.",
    "colmap_dense": "Set COLMAP_BIN and use the in-repository wrapper with dense mode enabled.",
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
    if pipeline_id == "vggt":
        return "one or more images"
    if pipeline_id in {"colmap", "colmap_dense", "gaussian_splatting"}:
        return "multiple images"
    return "custom"


def get_pipeline_diagnostics() -> dict[str, Any]:
    items = []
    pipelines = list_pipelines()
    for pipeline in pipelines:
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
                "limits": limits_for_pipeline(pipeline.id).to_payload(),
            }
        )

    pipeline_ids = [pipeline.id for pipeline in pipelines]
    pipeline_limits = limits_payload_for_pipelines(pipeline_ids)
    return {
        "items": items,
        "tasks_root": str(SETTINGS.tasks_root),
        "features": {
            "explicit_pipeline_selection": True,
        },
        "limits": {
            "max_upload_files": SETTINGS.max_upload_files,
            "max_upload_bytes": SETTINGS.max_upload_bytes,
            "max_image_pixels": SETTINGS.max_image_pixels,
            "max_image_long_edge": SETTINGS.max_image_long_edge,
            "pipelines": pipeline_limits,
            "max_supported_upload_files": max(
                limit["max_upload_files"] for limit in pipeline_limits.values()
            )
            if pipeline_limits
            else SETTINGS.max_upload_files,
        },
    }
