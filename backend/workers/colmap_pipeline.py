from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_MODEL_FILES = ("cameras.txt", "images.txt", "points3D.txt")
RAW_MODEL_FILES = ("cameras.bin", "images.bin", "points3D.bin")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COLMAP pipeline wrapper")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True, help="COLMAP workspace output directory")
    return parser.parse_args()


def _colmap_bin() -> str:
    override = os.getenv("COLMAP_BIN")
    if override:
        return override
    return "colmap"


def _colmap_env(colmap: str) -> dict[str, str]:
    env = os.environ.copy()
    colmap_dir = Path(colmap).expanduser().resolve().parent
    if colmap_dir.exists():
        env["PATH"] = str(colmap_dir) + os.pathsep + env.get("PATH", "")
    return env


def _tail(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return "[truncated]\n" + text[-max_chars:]


def _run(cmd: list[str], step: str, env: dict[str, str]) -> None:
    print(json.dumps({"step": step, "cmd": cmd}), flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.stdout:
        print(f"[{step}:stdout]\n{_tail(result.stdout)}", flush=True)
    if result.stderr:
        print(f"[{step}:stderr]\n{_tail(result.stderr)}", flush=True)
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"{step} failed: {_tail(details)}")


def _count_text_rows(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            count += 1
    return count


def _registered_image_count(images_txt: Path) -> int:
    return _count_text_rows(images_txt) // 2


def _image_count(input_dir: Path) -> int:
    return sum(1 for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _best_sparse_model(sparse_dir: Path) -> Path:
    candidates = []
    for model_dir in sorted(path for path in sparse_dir.iterdir() if path.is_dir()):
        raw_count = sum(1 for name in RAW_MODEL_FILES if (model_dir / name).exists())
        if raw_count == len(RAW_MODEL_FILES):
            candidates.append((model_dir, (model_dir / "points3D.bin").stat().st_size))
    if not candidates:
        raise RuntimeError("no_sparse_model: COLMAP mapper did not produce cameras/images/points3D binaries")
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def _write_summary(
    summary_path: Path,
    input_dir: Path,
    database_path: Path,
    sparse_model_dir: Path,
    sparse_text_dir: Path,
) -> dict[str, object]:
    cameras_txt = sparse_text_dir / "cameras.txt"
    images_txt = sparse_text_dir / "images.txt"
    points_txt = sparse_text_dir / "points3D.txt"
    summary = {
        "status": "completed",
        "input_image_count": _image_count(input_dir),
        "database_path": str(database_path),
        "sparse_model_path": str(sparse_model_dir),
        "sparse_text_path": str(sparse_text_dir),
        "camera_count": _count_text_rows(cameras_txt),
        "registered_image_count": _registered_image_count(images_txt),
        "point_count": _count_text_rows(points_txt),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    workspace = Path(args.output_dir).resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    if _image_count(input_dir) < 2:
        raise RuntimeError("not_enough_images: COLMAP requires at least two input images")

    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "database.db"
    sparse_dir = workspace / "sparse"
    sparse_txt_dir = workspace / "sparse_txt"
    summary_path = workspace / "summary.json"
    if db_path.exists():
        db_path.unlink()
    for path in (sparse_dir, sparse_txt_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    colmap = _colmap_bin()
    env = _colmap_env(colmap)
    _run([
        colmap,
        "feature_extractor",
        "--database_path",
        str(db_path),
        "--image_path",
        str(input_dir),
        "--ImageReader.single_camera",
        os.getenv("COLMAP_SINGLE_CAMERA", "1"),
        "--FeatureExtraction.use_gpu",
        os.getenv("COLMAP_USE_GPU", "1"),
        "--SiftExtraction.max_num_features",
        os.getenv("COLMAP_MAX_NUM_FEATURES", "8192"),
    ], "feature_extraction", env)
    _run([
        colmap,
        "exhaustive_matcher",
        "--database_path",
        str(db_path),
        "--FeatureMatching.use_gpu",
        os.getenv("COLMAP_USE_GPU", "1"),
    ], "matching", env)
    _run([
        colmap,
        "mapper",
        "--database_path",
        str(db_path),
        "--image_path",
        str(input_dir),
        "--output_path",
        str(sparse_dir),
        "--Mapper.multiple_models",
        os.getenv("COLMAP_MULTIPLE_MODELS", "0"),
        "--Mapper.min_model_size",
        os.getenv("COLMAP_MAPPER_MIN_MODEL_SIZE", "2"),
        "--Mapper.init_min_num_inliers",
        os.getenv("COLMAP_INIT_MIN_NUM_INLIERS", "30"),
        "--Mapper.abs_pose_min_num_inliers",
        os.getenv("COLMAP_ABS_POSE_MIN_NUM_INLIERS", "15"),
    ], "mapping", env)

    sparse_model_dir = _best_sparse_model(sparse_dir)
    _run([
        colmap,
        "model_converter",
        "--input_path",
        str(sparse_model_dir),
        "--output_path",
        str(sparse_txt_dir),
        "--output_type",
        "TXT",
    ], "model_conversion", env)

    missing_text = [name for name in TEXT_MODEL_FILES if not (sparse_txt_dir / name).exists()]
    if missing_text:
        raise RuntimeError(f"missing_sparse_text: {', '.join(missing_text)}")

    summary = _write_summary(summary_path, input_dir, db_path, sparse_model_dir, sparse_txt_dir)
    if summary["registered_image_count"] < 2:
        raise RuntimeError("insufficient_reconstruction: fewer than two images were registered")

    print(json.dumps({"step": "summary", "summary": summary}), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
