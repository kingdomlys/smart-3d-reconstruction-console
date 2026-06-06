from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_IMAGE = REPO_ROOT / "third_party" / "TripoSR" / "examples" / "chair.png"
OUTPUT_PATH = REPO_ROOT / "data" / "tripo_smoke" / "output.glb"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("TRIPOSR_REPO", str(REPO_ROOT / "third_party" / "TripoSR"))
    env.setdefault("TRIPOSR_DEVICE", "cuda:0")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "backend" / "workers" / "triposr_infer.py"),
        str(INPUT_IMAGE),
        str(OUTPUT_PATH),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size <= 0:
        raise AssertionError("TripoSR real smoke did not produce a non-empty GLB")
    print(f"triposr real smoke passed: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
