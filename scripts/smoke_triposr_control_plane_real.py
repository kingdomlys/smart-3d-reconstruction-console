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


def assert_triposr_runtime() -> None:
    tripo_python = os.getenv("TRIPOSR_PY")
    if not tripo_python:
        raise RuntimeError("Set TRIPOSR_PY to the TripoSR environment python before running this smoke")
    if not Path(tripo_python).exists():
        raise FileNotFoundError(f"TRIPOSR_PY does not exist: {tripo_python}")


async def main_async() -> None:
    assert_triposr_runtime()

    input_image = REPO_ROOT / "third_party" / "TripoSR" / "examples" / "chair.png"
    if not input_image.exists():
        raise FileNotFoundError(f"TripoSR example image not found: {input_image}")

    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["TRIPOSR_REPO"] = str(REPO_ROOT / "third_party" / "TripoSR")
        os.environ["TRIPOSR_DEVICE"] = os.getenv("TRIPOSR_DEVICE", "cuda:0")
        os.environ["USE_REMBG"] = "0"
        os.environ.pop("TRIPOSR_ALLOW_PLACEHOLDER", None)
        os.environ.pop("TRIPOSR_CMD", None)
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-triposr-real"
        db.create_task(task_id, mode="fast", image_count=1)
        dirs = storage_module.ensure_task_dirs(task_id)
        shutil.copyfile(input_image, Path(dirs["inputs_dir"]) / "input.png")

        worker_task = asyncio.create_task(task_worker())
        try:
            await TASK_QUEUE.enqueue(task_id)
            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=300)

            task = db.get_task(task_id)
            assert task and task["status"] == "Completed", task
            output_path = Path(task["output_path"])
            assert output_path.exists(), output_path
            assert output_path.stat().st_size > 100_000, output_path.stat().st_size
            assert output_path.suffix.lower() == ".glb", output_path

            outputs = storage_module.list_output_files(task_id)
            assert any(item["relative_path"] == "output.glb" for item in outputs), outputs

            logs = storage_module.read_task_log(task_id)
            assert "Task completed" in logs
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("triposr control-plane real smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
