from __future__ import annotations

import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db


def write_failing_pipeline(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import sys",
                "print('progress before failure')",
                "print('CUDA model weights missing for smoke', file=sys.stderr)",
                "raise SystemExit(7)",
            ]
        ),
        encoding="utf-8",
    )


def make_image_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    return stream.getvalue()


async def main_async() -> None:
    with TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        task_root = tmp_root / "tasks"
        failing_script = tmp_root / "failing_pipeline.py"
        write_failing_pipeline(failing_script)

        os.environ["TASKS_ROOT"] = str(task_root)
        os.environ["TRIPOSR_CMD"] = f"{sys.executable} {failing_script}"
        os.environ["USE_REMBG"] = "0"
        db.DB_PATH = tmp_root / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module
        from backend.app.tasks import TASK_QUEUE, task_worker

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task_id = "smoke-failure-summary"
        db.create_task(task_id, mode="fast", image_count=1)
        dirs = storage_module.ensure_task_dirs(task_id)
        (dirs["inputs_dir"] / "input.png").write_bytes(make_image_bytes())

        worker_task = asyncio.create_task(task_worker())
        try:
            await TASK_QUEUE.enqueue(task_id)
            await asyncio.wait_for(TASK_QUEUE.queue.join(), timeout=10)

            task = db.get_task(task_id)
            assert task and task["status"] == "Failed", task
            assert "triposr pipeline failed with exit code 1" in task["error"], task["error"]
            assert "CUDA model weights missing for smoke" in task["error"], task["error"]
            assert "progress before failure" in task["error"], task["error"]

            logs = storage_module.read_task_log(task_id)
            assert "Task failed:" in logs
            assert "CUDA model weights missing for smoke" in logs
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def main() -> int:
    asyncio.run(main_async())
    print("task failure summary smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
