from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="3DGS worker placeholder")
    parser.add_argument("--interim-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iterations", required=True)
    return parser.parse_args()


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> int:
    args = parse_args()
    interim_dir = Path(args.interim_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    emit({"status": "Running", "step": "3dgs", "progress": 0.8})
    output_path = output_dir / "point_cloud.ply"
    output_path.write_text("ply placeholder", encoding="utf-8")
    emit({"status": "Completed", "output": str(output_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
