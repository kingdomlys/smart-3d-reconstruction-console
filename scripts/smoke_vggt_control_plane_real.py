from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db


def _default_vggt_repo() -> Path:
    return Path(os.getenv("VGGT_REPO", r"E:\vscode\workspace\vggt")).resolve()


def _default_vggt_python() -> Path:
    return Path(os.getenv("VGGT_PY", r"E:\conda\workspace\envs\vggt\python.exe")).resolve()


def assert_vggt_runtime() -> tuple[Path, Path, Path]:
    vggt_repo = _default_vggt_repo()
    vggt_python = _default_vggt_python()
    checkpoint = Path(
        os.getenv("VGGT_CHECKPOINT", str(vggt_repo / "model_pretrained_weight" / "model.pt"))
    ).resolve()
    runner = vggt_repo / "run_local_vggt_pointcloud.py"
    preview = vggt_repo / "preview_ply_views.py"
    image_dir = vggt_repo / "examples" / "kitchen" / "images"

    missing = [
        str(path)
        for path in (vggt_python, runner, preview, checkpoint, image_dir)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("Missing VGGT runtime paths: " + ", ".join(missing))
    return vggt_repo, vggt_python, checkpoint


async def main_async() -> None:
    vggt_repo, vggt_python, checkpoint = assert_vggt_runtime()
    source_images = sorted((vggt_repo / "examples" / "kitchen" / "images").glob("*"))[:3]
    if len(source_images) < 3:
        raise RuntimeError("Need at least 3 VGGT kitchen images for the real smoke")

    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["VGGT_REPO"] = str(vggt_repo)
        os.environ["VGGT_PY"] = str(vggt_python)
        os.environ["VGGT_CHECKPOINT"] = str(checkpoint)
        os.environ["VGGT_MAX_IMAGES"] = "3"
        os.environ["VGGT_CONF_PERCENTILE"] = "70"
        os.environ["VGGT_SOURCE"] = "depth"
        os.environ["VGGT_PREPROCESS_MODE"] = "crop"
        os.environ["VGGT_PREVIEW"] = "1"
        os.environ["MULTI_IMAGE_PIPELINE"] = "vggt"
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-vggt-real"
        db.create_task(task_id, mode="fast", image_count=3)
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
            assert output_path.suffix.lower() == ".ply", output_path
            assert output_path.stat().st_size > 100_000, output_path.stat().st_size

            outputs = storage_module.list_output_files(task_id)
            output_types = {item["type"] for item in outputs}
            assert {"ply", "npz", "png"}.issubset(output_types), outputs
            assert sum(1 for item in outputs if item["type"] == "png") == 3, outputs
            assert any(item["relative_path"] == "predictions.npz" for item in outputs), outputs

            logs = storage_module.read_task_log(task_id)
            assert "Using device: cuda" in logs, logs[-2000:]
            assert "Task completed" in logs, logs[-2000:]
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("vggt control-plane real smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
