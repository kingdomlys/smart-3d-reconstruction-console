from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COLMAP worker placeholder")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--interim-dir", required=True)
    return parser.parse_args()


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    interim_dir = Path(args.interim_dir) / "colmap" / "sparse"
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    interim_dir.mkdir(parents=True, exist_ok=True)

    cmd = os.getenv("COLMAP_CMD")
    emit({"status": "Running", "step": "colmap", "progress": 0.2})
    if cmd:
        args_list = cmd.split() + ["--input-dir", str(input_dir), "--output-dir", str(interim_dir)]
        result = subprocess.run(args_list, capture_output=True, text=True, check=False)
        if result.stdout:
            emit({"status": "Running", "step": "colmap", "progress": 0.4, "stdout": result.stdout})
        if result.stderr:
            emit({"status": "Running", "step": "colmap", "progress": 0.4, "stderr": result.stderr})
        if result.returncode != 0:
            raise RuntimeError("COLMAP_CMD failed")
    else:
        (interim_dir / "cameras.txt").write_text("# placeholder cameras", encoding="utf-8")
        (interim_dir / "images.txt").write_text("# placeholder images", encoding="utf-8")
        (interim_dir / "points3D.txt").write_text("# placeholder points", encoding="utf-8")

    emit({"status": "Running", "step": "colmap", "progress": 0.6})
    emit({"status": "Completed", "output": str(interim_dir)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
