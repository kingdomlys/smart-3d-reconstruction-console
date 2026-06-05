from __future__ import annotations

import os
import shlex
import subprocess

from backend.pipelines.base import PipelineResult
from backend.pipelines.context import PipelineContext


class ColmapPipeline:
    id = "colmap"
    name = "COLMAP"
    output_types = ["colmap_sparse"]

    def supports(self, image_count: int, mode: str) -> bool:
        return image_count > 1

    def run(self, context: PipelineContext) -> PipelineResult:
        sparse_dir = context.interim_dir / "colmap" / "sparse"
        if not context.inputs_dir.exists():
            raise FileNotFoundError(f"Input dir not found: {context.inputs_dir}")
        sparse_dir.mkdir(parents=True, exist_ok=True)

        cmd = os.getenv("COLMAP_CMD")
        context.emit({"status": "Running", "step": "colmap", "progress": 0.2})
        if cmd:
            args = shlex.split(cmd) + [
                "--input-dir",
                str(context.inputs_dir),
                "--output-dir",
                str(sparse_dir),
            ]
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.stdout:
                context.emit({"status": "Running", "step": "colmap", "progress": 0.4, "stdout": result.stdout})
            if result.stderr:
                context.emit({"status": "Running", "step": "colmap", "progress": 0.4, "stderr": result.stderr})
            if result.returncode != 0:
                raise RuntimeError("COLMAP_CMD failed")
        else:
            (sparse_dir / "cameras.txt").write_text("# placeholder cameras", encoding="utf-8")
            (sparse_dir / "images.txt").write_text("# placeholder images", encoding="utf-8")
            (sparse_dir / "points3D.txt").write_text("# placeholder points", encoding="utf-8")

        context.emit({"status": "Running", "step": "colmap", "progress": 0.6})
        context.emit({"status": "Completed", "output": str(sparse_dir)})
        return PipelineResult(
            primary_output_path=sparse_dir,
            output_types=self.output_types,
            outputs={"colmap_sparse": sparse_dir},
        )
