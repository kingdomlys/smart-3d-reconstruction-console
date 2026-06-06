from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from backend.pipelines.base import PipelineResult
from backend.pipelines.commands import split_command
from backend.pipelines.context import PipelineContext

TEXT_MODEL_FILES = ("cameras.txt", "images.txt", "points3D.txt")
RAW_MODEL_FILES = ("cameras.bin", "images.bin", "points3D.bin")
SPARSE_PLY_NAME = "sparse.ply"


class ColmapPipeline:
    id = "colmap"
    name = "COLMAP"
    output_types = ["ply", "colmap_sparse", "db", "json", "txt", "bin"]

    def supports(self, image_count: int, mode: str) -> bool:
        return image_count > 1

    def run(self, context: PipelineContext) -> PipelineResult:
        workspace = context.interim_dir / "colmap"
        sparse_dir = workspace / "sparse"
        sparse_text_dir = workspace / "sparse_txt"
        sparse_ply_path = workspace / SPARSE_PLY_NAME
        summary_path = workspace / "summary.json"
        if not context.inputs_dir.exists():
            raise FileNotFoundError(f"Input dir not found: {context.inputs_dir}")
        workspace.mkdir(parents=True, exist_ok=True)

        context.emit({"status": "Running", "step": "colmap", "progress": 0.2})
        args = self._command() + [
            "--input-dir",
            str(context.inputs_dir),
            "--output-dir",
            str(workspace),
        ]
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.stdout:
            context.log(result.stdout)
            context.emit({"status": "Running", "step": "colmap", "progress": 0.4, "stdout": _tail(result.stdout)})
        if result.stderr:
            context.log(result.stderr)
            context.emit({"status": "Running", "step": "colmap", "progress": 0.4, "stderr": _tail(result.stderr)})
        if result.returncode != 0:
            details = "\n".join(part for part in (result.stdout, result.stderr) if part)
            failure = _classify_failure(details)
            raise RuntimeError(f"COLMAP {failure}: {_failure_hint(failure)}\n{_tail(details)}")

        self._validate_outputs(workspace, sparse_dir, sparse_text_dir, sparse_ply_path, summary_path)
        outputs = self._copy_outputs(
            context.outputs_dir,
            workspace,
            sparse_dir,
            sparse_text_dir,
            sparse_ply_path,
            summary_path,
        )

        context.emit({"status": "Running", "step": "colmap", "progress": 0.6})
        context.emit({"status": "Completed", "output": str(outputs["ply"])})
        return PipelineResult(
            primary_output_path=outputs["ply"],
            output_types=self.output_types,
            outputs=outputs,
            metadata=json.loads(summary_path.read_text(encoding="utf-8")),
        )

    def _command(self) -> list[str]:
        cmd = os.getenv("COLMAP_CMD")
        if cmd:
            return split_command(cmd)
        script_path = Path(__file__).resolve().parents[2] / "workers" / "colmap_pipeline.py"
        return [sys.executable, str(script_path)]

    def _validate_outputs(
        self,
        workspace: Path,
        sparse_dir: Path,
        sparse_text_dir: Path,
        sparse_ply_path: Path,
        summary_path: Path,
    ) -> None:
        if not (workspace / "database.db").exists():
            raise RuntimeError("COLMAP did not produce database.db")
        if not sparse_dir.exists() or not any(sparse_dir.iterdir()):
            raise RuntimeError("COLMAP did not produce sparse model output")
        missing_text = [name for name in TEXT_MODEL_FILES if not (sparse_text_dir / name).exists()]
        if missing_text:
            raise RuntimeError(f"COLMAP sparse text output missing: {', '.join(missing_text)}")
        if not sparse_ply_path.exists() or sparse_ply_path.stat().st_size == 0:
            raise RuntimeError("COLMAP did not produce sparse.ply")
        if not summary_path.exists():
            raise RuntimeError("COLMAP did not produce summary.json")

    def _copy_outputs(
        self,
        outputs_dir: Path,
        workspace: Path,
        sparse_dir: Path,
        sparse_text_dir: Path,
        sparse_ply_path: Path,
        summary_path: Path,
    ) -> dict[str, Path]:
        target_root = outputs_dir / "colmap"
        target_sparse = target_root / "sparse"
        target_sparse_text = target_root / "sparse_txt"
        for path in (target_sparse, target_sparse_text):
            path.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, Path] = {}
        summary_target = target_root / "summary.json"
        database_target = target_root / "database.db"
        sparse_ply_target = target_root / SPARSE_PLY_NAME
        shutil.copy2(summary_path, summary_target)
        shutil.copy2(workspace / "database.db", database_target)
        shutil.copy2(sparse_ply_path, sparse_ply_target)
        outputs["ply"] = sparse_ply_target
        outputs["json"] = summary_target
        outputs["db"] = database_target

        for source in sparse_dir.rglob("*"):
            if source.is_file() and source.name in RAW_MODEL_FILES:
                relative = source.relative_to(sparse_dir)
                target = target_sparse / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                outputs[f"bin:{relative.as_posix()}"] = target

        for name in TEXT_MODEL_FILES:
            source = sparse_text_dir / name
            target = target_sparse_text / name
            shutil.copy2(source, target)
            outputs[f"txt:{name}"] = target
        return outputs


def _tail(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return "[truncated]\n" + text[-max_chars:]


def _classify_failure(output: str) -> str:
    lowered = output.lower()
    if "no_initial_pair" in lowered:
        return "no_initial_pair"
    if "bad_initial_pair" in lowered:
        return "bad_initial_pair"
    if "failed to create any sparse model" in lowered:
        return "no_initial_pair"
    if "no good initial image pair" in lowered:
        return "no_initial_pair"
    if "bad initial pair" in lowered:
        return "bad_initial_pair"
    if "feature_extraction" in lowered or "feature extractor" in lowered:
        return "feature_extraction_failed"
    if "matching" in lowered or "matcher" in lowered:
        return "matching_failed"
    if "mapping" in lowered or "mapper" in lowered:
        return "mapping_failed"
    if "model_conversion" in lowered or "model_converter" in lowered:
        return "model_conversion_failed"
    if "no_sparse_model" in lowered:
        return "no_sparse_model"
    if "insufficient_reconstruction" in lowered:
        return "insufficient_reconstruction"
    if "not_enough_images" in lowered:
        return "not_enough_images"
    return "failed"


def _failure_hint(failure: str) -> str:
    if failure in {"no_initial_pair", "bad_initial_pair"}:
        return (
            "COLMAP could not initialize a sparse reconstruction. Use photos of the same static "
            "scene/object with strong overlap, visible texture, and moderate viewpoint changes; "
            "avoid unrelated images, large jumps, heavy blur, reflective surfaces, or pure background."
        )
    if failure == "not_enough_images":
        return "COLMAP needs at least two images, and usually benefits from 4-12 overlapping views."
    if failure == "insufficient_reconstruction":
        return "COLMAP ran but registered too few images for a usable sparse model."
    return "Inspect task logs and COLMAP inputs for details."
