from __future__ import annotations

import os
import subprocess

from backend.pipelines.base import PipelineResult
from backend.pipelines.commands import split_command
from backend.pipelines.context import PipelineContext


class GaussianSplattingPipeline:
    id = "gaussian_splatting"
    name = "3D Gaussian Splatting"
    output_types = ["ply", "splat"]

    def supports(self, image_count: int, mode: str) -> bool:
        return image_count > 1

    def run(self, context: PipelineContext) -> PipelineResult:
        context.outputs_dir.mkdir(parents=True, exist_ok=True)
        cmd = os.getenv("DGS_CMD")
        iterations = os.getenv("DGS_ITERATIONS", "1000")

        context.emit({"status": "Running", "step": "3dgs", "progress": 0.8})
        if cmd:
            args = split_command(cmd) + [
                "--interim-dir",
                str(context.interim_dir),
                "--output-dir",
                str(context.outputs_dir),
                "--iterations",
                iterations,
            ]
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.stdout:
                context.emit({"status": "Running", "step": "3dgs", "progress": 0.9, "stdout": result.stdout})
            if result.stderr:
                context.emit({"status": "Running", "step": "3dgs", "progress": 0.9, "stderr": result.stderr})
            if result.returncode != 0:
                raise RuntimeError("DGS_CMD failed")

        ply_path = context.outputs_dir / "point_cloud.ply"
        splat_path = context.outputs_dir / "scene.splat"
        if not ply_path.exists():
            ply_path.write_text("ply placeholder", encoding="utf-8")
        if not splat_path.exists():
            splat_path.write_text("splat placeholder", encoding="utf-8")
        context.emit({"status": "Completed", "output": str(ply_path)})
        return PipelineResult(
            primary_output_path=ply_path,
            output_types=self.output_types,
            outputs={"ply": ply_path, "splat": splat_path},
        )
