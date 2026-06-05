from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from backend.pipelines.base import PipelineResult
from backend.pipelines.context import PipelineContext

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class TripoSRPipeline:
    id = "triposr"
    name = "TripoSR"
    output_types = ["glb"]

    def supports(self, image_count: int, mode: str) -> bool:
        return image_count == 1

    def run(self, context: PipelineContext) -> PipelineResult:
        context.emit({"status": "Running", "step": "load", "progress": 0.1})
        input_path = self._pick_input_image(context.inputs_dir)
        processed_input = self._maybe_remove_bg(input_path, context)

        output_path = context.outputs_dir / "output.glb"
        used_cmd = self._run_external_tripo(processed_input, output_path, context)
        if used_cmd is None:
            output_path.write_text("GLB_PLACEHOLDER", encoding="utf-8")
            context.emit(
                {
                    "status": "Running",
                    "step": "tripo",
                    "progress": 0.7,
                    "warning": "TRIPOSR_CMD not set; placeholder output written",
                }
            )

        context.emit({"status": "Completed", "output_path": str(output_path)})
        return PipelineResult(
            primary_output_path=output_path,
            output_types=self.output_types,
            outputs={"glb": output_path},
        )

    def _pick_input_image(self, input_dir: Path) -> Path:
        for ext in SUPPORTED_EXTENSIONS:
            match = next(input_dir.glob(f"*{ext}"), None)
            if match:
                return match
        raise FileNotFoundError(f"No supported image found in {input_dir}")

    def _maybe_remove_bg(self, input_path: Path, context: PipelineContext) -> Path:
        use_rembg = os.getenv("USE_REMBG", "1") == "1"
        if not use_rembg:
            context.emit({"status": "Running", "step": "rembg", "progress": 0.2, "skipped": True})
            return input_path
        try:
            from rembg import remove
            from PIL import Image
        except Exception as exc:  # pragma: no cover - optional dependency
            context.emit({"status": "Running", "step": "rembg", "progress": 0.2, "warning": str(exc)})
            return input_path

        context.emit({"status": "Running", "step": "rembg", "progress": 0.2})
        context.interim_dir.mkdir(parents=True, exist_ok=True)
        output_path = context.interim_dir / "input_nobg.png"
        with Image.open(input_path) as image:
            result = remove(image)
            result.save(output_path)
        context.emit({"status": "Running", "step": "rembg", "progress": 0.3})
        return output_path

    def _run_external_tripo(
        self,
        input_path: Path,
        output_path: Path,
        context: PipelineContext,
    ) -> str | None:
        cmd = os.getenv("TRIPOSR_CMD")
        if not cmd:
            return None

        context.emit({"status": "Running", "step": "tripo", "progress": 0.5, "cmd": cmd})
        args = shlex.split(cmd) + [str(input_path), str(output_path)]
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.stdout:
            context.emit({"status": "Running", "step": "tripo", "progress": 0.6, "stdout": result.stdout})
        if result.stderr:
            context.emit({"status": "Running", "step": "tripo", "progress": 0.6, "stderr": result.stderr})
        if result.returncode != 0:
            raise RuntimeError("TRIPOSR_CMD failed")
        return cmd
