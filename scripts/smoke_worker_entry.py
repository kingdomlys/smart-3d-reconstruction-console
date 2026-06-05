from __future__ import annotations

import subprocess
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_image(path: Path) -> None:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    path.write_bytes(stream.getvalue())


def main() -> int:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs_dir = root / "inputs"
        interim_dir = root / "interim"
        outputs_dir = root / "outputs"
        for path in (inputs_dir, interim_dir, outputs_dir):
            path.mkdir(parents=True, exist_ok=True)
        write_image(inputs_dir / "input.png")

        cmd = [
            sys.executable,
            str(REPO_ROOT / "backend" / "workers" / "run_pipeline.py"),
            "--pipeline",
            "triposr",
            "--task-id",
            "smoke-worker",
            "--mode",
            "fast",
            "--input-dir",
            str(inputs_dir),
            "--interim-dir",
            str(interim_dir),
            "--output-dir",
            str(outputs_dir),
            "--logs-path",
            str(root / "logs.txt"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            raise SystemExit(result.returncode)
        output_path = outputs_dir / "output.glb"
        if not output_path.exists():
            raise AssertionError("worker entry did not write output.glb")
        print("worker entry smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
