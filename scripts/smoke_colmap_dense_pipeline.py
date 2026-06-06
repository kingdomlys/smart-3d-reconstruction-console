from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.colmap.pipeline import ColmapDensePipeline, _ply_vertex_count
from backend.pipelines.context import PipelineContext


def _write_image(path: Path) -> None:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    path.write_bytes(stream.getvalue())


def _write_ply(path: Path, points: list[tuple[float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write(f"element vertex {len(points)}\n")
        file.write("property float x\n")
        file.write("property float y\n")
        file.write("property float z\n")
        file.write("end_header\n")
        for x, y, z in points:
            file.write(f"{x} {y} {z}\n")


def _write_fake_colmap_dense_worker(path: Path) -> None:
    path.write_text(
        r'''
from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_ply(path: Path, rows: list[tuple[float, float, float, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write(f"element vertex {len(rows)}\n")
        file.write("property float x\n")
        file.write("property float y\n")
        file.write("property float z\n")
        file.write("property uchar red\n")
        file.write("property uchar green\n")
        file.write("property uchar blue\n")
        file.write("end_header\n")
        for row in rows:
            file.write("{} {} {} {} {} {}\n".format(*row))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dense", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.output_dir)
    sparse_dir = workspace / "sparse" / "0"
    sparse_txt = workspace / "sparse_txt"
    dense_dir = workspace / "dense"
    sparse_dir.mkdir(parents=True, exist_ok=True)
    sparse_txt.mkdir(parents=True, exist_ok=True)
    dense_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "database.db").write_bytes(b"db")
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_dir / name).write_bytes(b"bin")
    (sparse_txt / "cameras.txt").write_text("# cameras\n1 PINHOLE 64 64 1 1 32 32\n", encoding="utf-8")
    (sparse_txt / "images.txt").write_text(
        "# images\n1 1 0 0 0 0 0 0 1 a.png\n\n2 1 0 0 0 1 0 0 1 b.png\n\n",
        encoding="utf-8",
    )
    (sparse_txt / "points3D.txt").write_text(
        "# points\n1 0 0 0 255 0 0 0.1 1 2\n2 1 0 0 0 255 0 0.1 1 2\n",
        encoding="utf-8",
    )
    write_ply(workspace / "sparse.ply", [(0, 0, 0, 255, 0, 0), (1, 0, 0, 0, 255, 0)])
    write_ply(dense_dir / "fused.ply", [(0, 0, 0, 255, 255, 255), (1, 0, 0, 255, 255, 255), (0, 1, 0, 255, 255, 255)])
    summary = {
        "status": "completed",
        "reconstruction_type": "dense",
        "input_image_count": 2,
        "registered_image_count": 2,
        "point_count": 2,
        "dense_point_count": 3,
    }
    (workspace / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    print(json.dumps({"step": "summary", "summary": summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''.lstrip(),
        encoding="utf-8",
    )


def main() -> int:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs_dir = root / "inputs"
        interim_dir = root / "interim"
        outputs_dir = root / "outputs"
        for path in (inputs_dir, interim_dir, outputs_dir):
            path.mkdir(parents=True, exist_ok=True)
        _write_image(inputs_dir / "a.png")
        _write_image(inputs_dir / "b.png")

        fake_worker = root / "fake_colmap_dense_worker.py"
        _write_fake_colmap_dense_worker(fake_worker)
        os.environ["COLMAP_DENSE_CMD"] = f"{sys.executable} {fake_worker}"
        try:
            context = PipelineContext(
                task_id="smoke-colmap-dense",
                mode="fast",
                inputs_dir=inputs_dir,
                interim_dir=interim_dir,
                outputs_dir=outputs_dir,
                logs_path=root / "logs.txt",
            )
            result = ColmapDensePipeline().run(context)
        finally:
            os.environ.pop("COLMAP_DENSE_CMD", None)

        dense_ply = outputs_dir / "colmap_dense" / "dense" / "fused.ply"
        sparse_ply = outputs_dir / "colmap_dense" / "sparse.ply"
        summary_path = outputs_dir / "colmap_dense" / "summary.json"
        assert result.primary_output_path == dense_ply, result
        assert dense_ply.exists(), dense_ply
        assert sparse_ply.exists(), sparse_ply
        assert summary_path.exists(), summary_path
        assert _ply_vertex_count(dense_ply) == 3, dense_ply
        assert json.loads(summary_path.read_text(encoding="utf-8"))["reconstruction_type"] == "dense"

    print("colmap dense pipeline smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
