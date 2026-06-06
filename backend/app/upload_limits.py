from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from .settings import SETTINGS


COLMAP_DEFAULT_REFERENCE_PIXELS = 1280 * 720


@dataclass(frozen=True)
class UploadLimits:
    pipeline_id: str
    min_upload_files: int
    max_upload_files: int
    max_upload_bytes: int
    max_image_pixels: int
    max_image_long_edge: int
    max_total_image_pixels: int | None = None
    target_vram_gb: int | None = None
    note: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _base_limits(pipeline_id: str, max_upload_files: int) -> UploadLimits:
    return UploadLimits(
        pipeline_id=pipeline_id,
        min_upload_files=1,
        max_upload_files=max_upload_files,
        max_upload_bytes=SETTINGS.max_upload_bytes,
        max_image_pixels=SETTINGS.max_image_pixels,
        max_image_long_edge=SETTINGS.max_image_long_edge,
        max_total_image_pixels=max_upload_files * SETTINGS.max_image_pixels,
    )


def limits_for_pipeline(pipeline_id: str | None) -> UploadLimits:
    selected = (pipeline_id or "default").strip().lower()

    if selected == "triposr":
        return UploadLimits(
            pipeline_id="triposr",
            min_upload_files=1,
            max_upload_files=1,
            max_upload_bytes=_env_int("TRIPOSR_MAX_UPLOAD_BYTES", SETTINGS.max_upload_bytes),
            max_image_pixels=_env_int("TRIPOSR_MAX_IMAGE_PIXELS", SETTINGS.max_image_pixels),
            max_image_long_edge=_env_int("TRIPOSR_MAX_IMAGE_LONG_EDGE", SETTINGS.max_image_long_edge),
            max_total_image_pixels=_env_int("TRIPOSR_MAX_TOTAL_IMAGE_PIXELS", SETTINGS.max_image_pixels),
            note="single-image mesh reconstruction",
        )

    if selected == "vggt":
        max_upload_files = _env_int("VGGT_MAX_IMAGES", SETTINGS.max_upload_files)
        return UploadLimits(
            pipeline_id="vggt",
            min_upload_files=1,
            max_upload_files=max_upload_files,
            max_upload_bytes=_env_int("VGGT_MAX_UPLOAD_BYTES", SETTINGS.max_upload_bytes),
            max_image_pixels=_env_int("VGGT_MAX_IMAGE_PIXELS", SETTINGS.max_image_pixels),
            max_image_long_edge=_env_int("VGGT_MAX_IMAGE_LONG_EDGE", SETTINGS.max_image_long_edge),
            max_total_image_pixels=_env_int(
                "VGGT_MAX_TOTAL_IMAGE_PIXELS",
                max_upload_files * SETTINGS.max_image_pixels,
            ),
            note="VGGT preprocesses images before inference; upload validation still caps raw inputs",
        )

    if selected in {"colmap", "colmap_dense"}:
        dense = selected == "colmap_dense"
        prefix = "COLMAP_DENSE" if dense else "COLMAP"
        default_max_files = 16 if dense else 32
        default_total_pixels = default_max_files * COLMAP_DEFAULT_REFERENCE_PIXELS
        max_upload_files = _env_int(f"{prefix}_MAX_UPLOAD_FILES", default_max_files)
        max_image_pixels = _env_int(f"{prefix}_MAX_IMAGE_PIXELS", SETTINGS.max_image_pixels)
        return UploadLimits(
            pipeline_id=selected,
            min_upload_files=2,
            max_upload_files=max_upload_files,
            max_upload_bytes=_env_int(f"{prefix}_MAX_UPLOAD_BYTES", SETTINGS.max_upload_bytes),
            max_image_pixels=max_image_pixels,
            max_image_long_edge=_env_int(f"{prefix}_MAX_IMAGE_LONG_EDGE", SETTINGS.max_image_long_edge),
            max_total_image_pixels=_env_int(
                f"{prefix}_MAX_TOTAL_IMAGE_PIXELS",
                default_total_pixels,
            ),
            target_vram_gb=_env_int(f"{prefix}_TARGET_VRAM_GB", 8),
            note=(
                "dense COLMAP route; default budget is conservative because PatchMatch stereo is memory-heavy"
                if dense
                else "sparse COLMAP route; default total-pixel budget allows 32 images near 1280x720"
            ),
        )

    return _base_limits("default", SETTINGS.max_upload_files)


def limits_payload_for_pipelines(pipeline_ids: list[str]) -> dict[str, dict[str, Any]]:
    return {pipeline_id: limits_for_pipeline(pipeline_id).to_payload() for pipeline_id in pipeline_ids}
