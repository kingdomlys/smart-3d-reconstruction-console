from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TripoSR CLI wrapper")
    parser.add_argument("input_path")
    parser.add_argument("output_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path).resolve()
    output_path = Path(args.output_path).resolve()

    repo_root = Path(os.getenv("TRIPOSR_REPO", "third_party/TripoSR")).resolve()
    project_root = Path(__file__).resolve().parents[2]
    compat_root = project_root / "backend" / "compat"
    run_script = repo_root / "run.py"
    if not run_script.exists():
        raise FileNotFoundError(f"TripoSR run.py not found: {run_script}")

    output_dir = output_path.parent / "tripo_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "0").mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(run_script),
        str(input_path),
        "--output-dir",
        str(output_dir),
        "--model-save-format",
        "glb",
        "--no-remove-bg",
    ]

    device = os.getenv("TRIPOSR_DEVICE")
    if device:
        cmd += ["--device", device]

    env = os.environ.copy()
    pythonpath_parts = [str(compat_root), str(repo_root)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(details or "TripoSR run failed")

    candidates = list(output_dir.rglob("mesh.glb"))
    if not candidates:
        raise RuntimeError("TripoSR output mesh.glb not found")

    output_path.write_bytes(candidates[0].read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
