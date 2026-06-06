from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db


async def main_async() -> None:
    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"

        os.environ["TASKS_ROOT"] = str(task_root)
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        import backend.app.tasks as tasks_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        async def fake_run_vggt(task_id: str, mode: str, on_event: callable) -> Path:
            await on_event({"status": "Running", "step": "vggt-fake", "progress": 0.5})
            output_path = Path(storage_module.ensure_task_dirs(task_id)["outputs_dir"]) / "fake.ply"
            output_path.write_text("ply", encoding="utf-8")
            return output_path

        async def fake_run_colmap(task_id: str, mode: str, on_event: callable) -> Path:
            await on_event({"status": "Running", "step": "colmap-fake", "progress": 0.5})
            dirs = storage_module.ensure_task_dirs(task_id)
            output_root = Path(dirs["outputs_dir"]) / "colmap"
            output_root.mkdir(parents=True, exist_ok=True)
            output_path = output_root / "sparse.ply"
            output_path.write_text("ply", encoding="utf-8")
            summary_path = output_root / "summary.json"
            summary_path.write_text("{}", encoding="utf-8")
            sparse_dir = Path(dirs["interim_dir"]) / "colmap" / "sparse"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sparse_dir.mkdir(parents=True, exist_ok=True)
            return output_path

        async def fake_run_colmap_dense(task_id: str, mode: str, on_event: callable) -> Path:
            await on_event({"status": "Running", "step": "colmap-dense-fake", "progress": 0.5})
            dirs = storage_module.ensure_task_dirs(task_id)
            output_root = Path(dirs["outputs_dir"]) / "colmap_dense"
            dense_root = output_root / "dense"
            dense_root.mkdir(parents=True, exist_ok=True)
            output_path = dense_root / "fused.ply"
            output_path.write_text("ply", encoding="utf-8")
            (output_root / "sparse.ply").write_text("ply", encoding="utf-8")
            (output_root / "summary.json").write_text("{}", encoding="utf-8")
            return output_path

        original_vggt = tasks_module._run_vggt_worker
        original_colmap = tasks_module._run_colmap_worker
        original_colmap_dense = tasks_module._run_colmap_dense_worker
        tasks_module._run_vggt_worker = fake_run_vggt
        tasks_module._run_colmap_worker = fake_run_colmap
        tasks_module._run_colmap_dense_worker = fake_run_colmap_dense
        db.init_db()

        worker_task = asyncio.create_task(task_worker())
        try:
            for task_id, pipeline_id, image_count in (
                ("smoke-vggt-route", "vggt", 1),
                ("smoke-colmap-route", "colmap", 2),
                ("smoke-colmap-dense-route", "colmap_dense", 2),
            ):
                db.create_task(task_id, mode="fast", image_count=image_count, pipeline_id=pipeline_id)
                await TASK_QUEUE.enqueue(task_id)

            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=10)

            vggt_task = db.get_task("smoke-vggt-route")
            assert vggt_task and vggt_task["status"] == "Completed", vggt_task
            assert vggt_task["pipeline_id"] == "vggt", vggt_task
            assert Path(vggt_task["output_path"]).name == "fake.ply", vggt_task

            colmap_task = db.get_task("smoke-colmap-route")
            assert colmap_task and colmap_task["status"] == "Completed", colmap_task
            assert colmap_task["pipeline_id"] == "colmap", colmap_task
            assert colmap_task["output_path"].endswith("sparse.ply"), colmap_task

            colmap_dense_task = db.get_task("smoke-colmap-dense-route")
            assert colmap_dense_task and colmap_dense_task["status"] == "Completed", colmap_dense_task
            assert colmap_dense_task["pipeline_id"] == "colmap_dense", colmap_dense_task
            assert colmap_dense_task["output_path"].endswith("fused.ply"), colmap_dense_task
        finally:
            tasks_module._run_vggt_worker = original_vggt
            tasks_module._run_colmap_worker = original_colmap
            tasks_module._run_colmap_dense_worker = original_colmap_dense
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("worker pipeline events smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
