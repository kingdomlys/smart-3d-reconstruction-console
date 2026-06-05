from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.context import PipelineContext
from backend.pipelines.registry import get_pipeline, select_pipeline


def write_image(path: Path) -> None:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    path.write_bytes(stream.getvalue())


def make_context(root: Path, pipeline_id: str) -> PipelineContext:
    inputs_dir = root / pipeline_id / "inputs"
    interim_dir = root / pipeline_id / "interim"
    outputs_dir = root / pipeline_id / "outputs"
    for path in (inputs_dir, interim_dir, outputs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return PipelineContext(
        task_id=f"smoke-{pipeline_id}",
        mode="fast",
        inputs_dir=inputs_dir,
        interim_dir=interim_dir,
        outputs_dir=outputs_dir,
        logs_path=root / pipeline_id / "logs.txt",
        emit_event=lambda payload: print(f"{pipeline_id}: {payload.get('step') or payload.get('status')}"),
    )


def main() -> int:
    if select_pipeline(image_count=1, mode="fast").id != "triposr":
        raise AssertionError("single-image route should select triposr")
    if select_pipeline(image_count=2, mode="fast").id != "colmap":
        raise AssertionError("multi-image first route should select colmap")

    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        tripo_context = make_context(root, "triposr")
        write_image(tripo_context.inputs_dir / "input.png")
        tripo_result = get_pipeline("triposr").run(tripo_context)
        if not tripo_result.primary_output_path.exists():
            raise AssertionError("TripoSR pipeline did not write output")

        colmap_context = make_context(root, "colmap")
        write_image(colmap_context.inputs_dir / "image_1.png")
        write_image(colmap_context.inputs_dir / "image_2.png")
        colmap_result = get_pipeline("colmap").run(colmap_context)
        if not (colmap_result.primary_output_path / "cameras.txt").exists():
            raise AssertionError("COLMAP pipeline did not write sparse output")

        gs_context = make_context(root, "gaussian_splatting")
        gs_result = get_pipeline("gaussian_splatting").run(gs_context)
        if not gs_result.outputs["ply"].exists() or not gs_result.outputs["splat"].exists():
            raise AssertionError("3DGS pipeline did not write both outputs")

    print("pipeline registry smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
