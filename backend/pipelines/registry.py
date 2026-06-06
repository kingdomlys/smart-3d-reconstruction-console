from __future__ import annotations

from .base import Pipeline
from .colmap.pipeline import ColmapPipeline
from .gaussian_splatting.pipeline import GaussianSplattingPipeline
from .triposr.pipeline import TripoSRPipeline
from .vggt.pipeline import VggtPipeline

_PIPELINES: dict[str, Pipeline] = {
    "triposr": TripoSRPipeline(),
    "vggt": VggtPipeline(),
    "colmap": ColmapPipeline(),
    "gaussian_splatting": GaussianSplattingPipeline(),
}


def list_pipelines() -> list[Pipeline]:
    return list(_PIPELINES.values())


def get_pipeline(pipeline_id: str) -> Pipeline:
    try:
        return _PIPELINES[pipeline_id]
    except KeyError as exc:
        raise ValueError(f"Unknown pipeline: {pipeline_id}") from exc


def select_pipeline(image_count: int, mode: str) -> Pipeline:
    for pipeline in list_pipelines():
        if pipeline.supports(image_count=image_count, mode=mode):
            return pipeline
    raise ValueError(f"No pipeline supports image_count={image_count}, mode={mode}")
