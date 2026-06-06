from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from backend.pipelines.base import PipelineResult
from backend.pipelines.context import PipelineContext


class VggtPipeline:
    id = "vggt"
    name = "VGGT"
    output_types = ["ply", "npz", "png"]

    def supports(self, image_count: int, mode: str) -> bool:
        return image_count > 1

    def run(self, context: PipelineContext) -> PipelineResult:
        configured_repo = os.getenv("VGGT_REPO")
        repo_root = (
            Path(configured_repo).expanduser()
            if configured_repo
            else Path(__file__).resolve().parents[3].parent / "vggt"
        )
        repo_root = repo_root.resolve()
        script_path = repo_root / "run_local_vggt_pointcloud.py"
        preview_script = repo_root / "preview_ply_views.py"
        checkpoint_path = Path(
            os.getenv("VGGT_CHECKPOINT", str(repo_root / "model_pretrained_weight" / "model.pt"))
        ).expanduser()
        if not checkpoint_path.is_absolute():
            checkpoint_path = (repo_root / checkpoint_path).resolve()

        if not script_path.exists():
            raise FileNotFoundError(f"VGGT runner not found: {script_path}")
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"VGGT checkpoint not found: {checkpoint_path}")

        output_dir = context.interim_dir / "vggt"
        output_dir.mkdir(parents=True, exist_ok=True)

        max_images = os.getenv("VGGT_MAX_IMAGES", "3")
        conf_percentile = os.getenv("VGGT_CONF_PERCENTILE", "70")
        source = os.getenv("VGGT_SOURCE", "depth")
        preprocess_mode = os.getenv("VGGT_PREPROCESS_MODE", "crop")

        context.emit({"status": "Running", "step": "vggt", "progress": 0.2})
        cmd = [
            os.getenv("VGGT_PY") or sys.executable,
            str(script_path),
            "--image_folder",
            str(context.inputs_dir),
            "--checkpoint",
            str(checkpoint_path),
            "--output_dir",
            str(output_dir),
            "--max_images",
            max_images,
            "--conf_percentile",
            conf_percentile,
            "--source",
            source,
            "--preprocess_mode",
            preprocess_mode,
        ]
        self._run(cmd, repo_root, context, "VGGT inference failed")
        context.emit({"status": "Running", "step": "vggt", "progress": 0.8})

        ply_candidates = sorted(output_dir.glob(f"pointcloud_{source}_*imgs_p*.ply"))
        if not ply_candidates:
            raise RuntimeError("VGGT did not produce a point cloud PLY")
        source_ply = ply_candidates[0]
        output_ply = context.outputs_dir / source_ply.name
        shutil.copyfile(source_ply, output_ply)

        source_npz = output_dir / "predictions.npz"
        outputs = {"ply": output_ply}
        if source_npz.exists():
            output_npz = context.outputs_dir / source_npz.name
            shutil.copyfile(source_npz, output_npz)
            outputs["npz"] = output_npz

        if preview_script.exists() and os.getenv("VGGT_PREVIEW", "1") == "1":
            preview_cmd = [
                os.getenv("VGGT_PY") or sys.executable,
                str(preview_script),
                str(source_ply),
                "--output_dir",
                str(output_dir),
            ]
            self._run(preview_cmd, repo_root, context, "VGGT preview generation failed")
            for preview in sorted(output_dir.glob(f"{source_ply.stem}_*.png")):
                target = context.outputs_dir / preview.name
                shutil.copyfile(preview, target)
                outputs[f"png:{preview.stem}"] = target

        context.emit({"status": "Completed", "output_path": str(output_ply)})
        return PipelineResult(
            primary_output_path=output_ply,
            output_types=self.output_types,
            outputs=outputs,
            metadata={
                "source": source,
                "max_images": max_images,
                "conf_percentile": conf_percentile,
            },
        )

    def _run(self, cmd: list[str], cwd: Path, context: PipelineContext, error_message: str) -> None:
        context.log(f"[vggt] cmd: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        if result.stdout:
            context.log(result.stdout)
            context.emit({"status": "Running", "step": "vggt", "progress": 0.5, "stdout": result.stdout})
        if result.stderr:
            context.log(result.stderr)
            context.emit({"status": "Running", "step": "vggt", "progress": 0.5, "stderr": result.stderr})
        if result.returncode != 0:
            details = "\n".join(part for part in (result.stdout, result.stderr) if part)
            raise RuntimeError(details or error_message)
