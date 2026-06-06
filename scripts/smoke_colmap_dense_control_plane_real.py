from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db
from backend.pipelines.colmap.pipeline import _ply_vertex_count


def _default_colmap_bin() -> Path:
    return Path(
        os.getenv(
            "COLMAP_BIN",
            r"E:\vscode\workspace\colmap\colmap-x64-windows-cuda\bin\colmap.exe",
        )
    ).resolve()


def _default_vggt_repo() -> Path:
    return Path(os.getenv("VGGT_REPO", r"E:\vscode\workspace\vggt")).resolve()


def assert_colmap_runtime() -> tuple[Path, list[Path]]:
    colmap_bin = _default_colmap_bin()
    if not colmap_bin.exists():
        raise FileNotFoundError(f"COLMAP_BIN does not exist: {colmap_bin}")
    source_images = sorted((_default_vggt_repo() / "examples" / "kitchen" / "images").glob("*"))[:4]
    if len(source_images) < 4:
        raise RuntimeError("Need at least 4 input images for COLMAP dense smoke")
    return colmap_bin, source_images


async def main_async() -> None:
    colmap_bin, source_images = assert_colmap_runtime()

    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["COLMAP_BIN"] = str(colmap_bin)
        os.environ.pop("COLMAP_CMD", None)
        os.environ.pop("COLMAP_DENSE_CMD", None)
        os.environ["COLMAP_DENSE_MAX_IMAGE_SIZE"] = os.getenv("COLMAP_DENSE_MAX_IMAGE_SIZE", "768")
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-colmap-dense-real"
        db.create_task(task_id, mode="fast", image_count=len(source_images), pipeline_id="colmap_dense")
        dirs = storage_module.ensure_task_dirs(task_id)
        for image_path in source_images:
            shutil.copyfile(image_path, Path(dirs["inputs_dir"]) / image_path.name)

        worker_task = asyncio.create_task(task_worker())
        try:
            await TASK_QUEUE.enqueue(task_id)
            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=900)

            task = db.get_task(task_id)
            assert task and task["status"] == "Completed", task
            output_path = Path(task["output_path"])
            assert output_path.exists(), output_path
            assert output_path.as_posix().endswith("colmap_dense/dense/fused.ply"), output_path
            assert _ply_vertex_count(output_path) > 0, output_path
            assert output_path.stat().st_size > 1024, output_path.stat().st_size

            summary_path = output_path.parents[1] / "summary.json"
            assert summary_path.exists(), summary_path
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["reconstruction_type"] == "dense", summary
            assert summary["dense_point_count"] == _ply_vertex_count(output_path), summary

            outputs = storage_module.list_output_files(task_id)
            relative_paths = {item["relative_path"] for item in outputs}
            assert "colmap_dense/dense/fused.ply" in relative_paths, outputs
            assert "colmap_dense/sparse.ply" in relative_paths, outputs
            assert "colmap_dense/summary.json" in relative_paths, outputs

            logs = storage_module.read_task_log(task_id)
            assert "image_undistortion" in logs, logs[-2000:]
            assert "patch_match_stereo" in logs, logs[-2000:]
            assert "stereo_fusion" in logs, logs[-2000:]
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("colmap dense control-plane real smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
