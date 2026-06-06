from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.workers.colmap_pipeline import _write_sparse_ply
from backend.pipelines.colmap.pipeline import _ply_vertex_count


def main() -> int:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        points_txt = root / "points3D.txt"
        sparse_ply = root / "sparse.ply"
        points_txt.write_text(
            "\n".join(
                [
                    "# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]",
                    "1 1.0 2.0 3.0 10 20 30 0.1 1 2 3 4",
                    "2 -1.5 0.25 4.5 200 180 160 0.2 1 5 3 6",
                ]
            ),
            encoding="utf-8",
        )
        written = _write_sparse_ply(points_txt, sparse_ply)
        if written != 2:
            raise AssertionError(f"expected 2 written points, got {written}")
        if _ply_vertex_count(sparse_ply) != 2:
            raise AssertionError("PLY vertex count should be readable")
        text = sparse_ply.read_text(encoding="ascii")
        if "element vertex 2" not in text or "10 20 30" not in text:
            raise AssertionError(text)

    print("colmap sparse ply export smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
