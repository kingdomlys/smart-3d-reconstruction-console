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


def write_slow_pipeline(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import sys",
                "import time",
                "from pathlib import Path",
                "",
                "input_path = Path(sys.argv[-2])",
                "output_path = Path(sys.argv[-1])",
                "print(json.dumps({'status': 'Running', 'step': 'slow', 'progress': 0.2}), flush=True)",
                "time.sleep(30)",
                "output_path.write_text('glb', encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )


async def main_async() -> None:
    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"
        slow_script = tmp_root / "slow_pipeline.py"
        write_slow_pipeline(slow_script)

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["TRIPOSR_CMD"] = f"{sys.executable} {slow_script}"
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, cancel_task, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-cancel"
        db.create_task(task_id, mode="fast", image_count=1)
        dirs = storage_module.ensure_task_dirs(task_id)
        (dirs["inputs_dir"] / "input.png").write_bytes(b"placeholder image bytes")

        worker_task = asyncio.create_task(task_worker())
        try:
            await TASK_QUEUE.enqueue(task_id)

            for _ in range(50):
                if db.get_task(task_id)["status"] == "Running":
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("task did not start")

            canceled = await cancel_task(task_id)
            assert canceled["status"] == "Canceled", canceled

            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=10)
            task = db.get_task(task_id)
            assert task and task["status"] == "Canceled", task
            assert not (Path(dirs["outputs_dir"]) / "output.glb").exists()

            logs = storage_module.read_task_log(task_id)
            assert "Task canceled by user" in logs
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("task cancel smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
