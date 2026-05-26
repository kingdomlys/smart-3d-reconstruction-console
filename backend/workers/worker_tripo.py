from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TripoSR worker placeholder")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--interim-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def _pick_input_image(input_dir: Path) -> Path:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        match = next(input_dir.glob(f"*{ext}"), None)
        if match:
            return match
    raise FileNotFoundError(f"No supported image found in {input_dir}")


def _maybe_remove_bg(input_path: Path, interim_dir: Path) -> Path:
    use_rembg = os.getenv("USE_REMBG", "1") == "1"
    if not use_rembg:
        emit({"status": "Running", "step": "rembg", "progress": 0.2, "skipped": True})
        return input_path
    try:
        from rembg import remove
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional dependency
        emit({"status": "Running", "step": "rembg", "progress": 0.2, "warning": str(exc)})
        return input_path

    emit({"status": "Running", "step": "rembg", "progress": 0.2})
    interim_dir.mkdir(parents=True, exist_ok=True)
    output_path = interim_dir / "input_nobg.png"
    with Image.open(input_path) as image:
        result = remove(image)
        result.save(output_path)
    emit({"status": "Running", "step": "rembg", "progress": 0.3})
    return output_path


def _run_external_tripo(input_path: Path, output_path: Path) -> Optional[str]:
    cmd = os.getenv("TRIPOSR_CMD")
    if not cmd:
        return None
    emit({"status": "Running", "step": "tripo", "progress": 0.5, "cmd": cmd})
    args = cmd.split()
    args += [str(input_path), str(output_path)]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.stdout:
        emit({"status": "Running", "step": "tripo", "progress": 0.6, "stdout": result.stdout})
    if result.stderr:
        emit({"status": "Running", "step": "tripo", "progress": 0.6, "stderr": result.stderr})
    if result.returncode != 0:
        raise RuntimeError("TRIPOSR_CMD failed")
    return cmd


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    interim_dir = Path(args.interim_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    emit({"status": "Running", "step": "load", "progress": 0.1})
    input_path = _pick_input_image(input_dir)
    processed_input = _maybe_remove_bg(input_path, interim_dir)

    output_path = output_dir / "output.glb"
    used_cmd = _run_external_tripo(processed_input, output_path)
    if used_cmd is None:
        output_path.write_text("GLB_PLACEHOLDER", encoding="utf-8")
        emit(
            {
                "status": "Running",
                "step": "tripo",
                "progress": 0.7,
                "warning": "TRIPOSR_CMD not set; placeholder output written",
            }
        )
    emit({"status": "Completed", "output_path": str(output_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
