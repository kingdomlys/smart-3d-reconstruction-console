from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="3DGS pipeline wrapper")
    parser.add_argument("--interim-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iterations", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interim_dir = Path(args.interim_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    train_script = os.getenv("DGS_TRAIN_SCRIPT")
    if not train_script:
        raise RuntimeError("DGS_TRAIN_SCRIPT is not set")

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        train_script,
        "--interim-dir",
        str(interim_dir),
        "--output-dir",
        str(output_dir),
        "--iterations",
        str(args.iterations),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "3DGS training failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
