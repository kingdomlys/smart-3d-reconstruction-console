from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COLMAP pipeline wrapper")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def _colmap_bin() -> str:
    override = os.getenv("COLMAP_BIN")
    if override:
        return override
    return "colmap"


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "COLMAP command failed")


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = output_dir.parent
    db_path = workspace / "database.db"

    colmap = _colmap_bin()
    _run([
        colmap,
        "feature_extractor",
        "--database_path",
        str(db_path),
        "--image_path",
        str(input_dir),
    ])
    _run([
        colmap,
        "exhaustive_matcher",
        "--database_path",
        str(db_path),
    ])
    _run([
        colmap,
        "mapper",
        "--database_path",
        str(db_path),
        "--image_path",
        str(input_dir),
        "--output_path",
        str(output_dir),
    ])

    # Normalize output into output_dir if COLMAP created a subfolder.
    if (output_dir / "0").exists():
        sparse_dir = output_dir / "0"
        for name in ("cameras.txt", "images.txt", "points3D.txt"):
            src = sparse_dir / name
            if src.exists():
                shutil.copy2(src, output_dir / name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
