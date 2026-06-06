from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def make_image() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    stream.seek(0)
    return stream


def main() -> int:
    with TemporaryDirectory() as tmp:
        import os

        tmp_root = Path(tmp)
        os.environ["TASKS_ROOT"] = str(tmp_root / "tasks")
        os.environ["TRIPOSR_ALLOW_PLACEHOLDER"] = "1"

        from fastapi.testclient import TestClient

        from backend.app import db
        from backend.app.main import app
        from backend.app.storage import ensure_task_dirs
        from backend.app.tasks import TASK_QUEUE

        db.DB_PATH = tmp_root / "tasks.db"

        with TestClient(app) as client:
            root = client.get("/")
            assert root.status_code == 200, root.text
            config = client.get("/api/config")
            assert config.status_code == 200, config.text
            payload = config.json()
            assert payload["max_upload_files"] == 8

            response = client.post(
                "/api/tasks",
                files=[
                    ("files", (f"too_many_{index}.png", make_image(), "image/png"))
                    for index in range(payload["max_upload_files"] + 1)
                ],
            )
            assert response.status_code == 400, response.text
            assert response.json()["detail"]["error"] == "Too many files"

            task_id = "api-observe"
            db.create_task(task_id, mode="fast", image_count=1)
            db.update_task(task_id, status="Failed", error="failed for smoke")
            dirs = ensure_task_dirs(task_id)
            (dirs["inputs_dir"] / "input.png").write_bytes(make_image().getvalue())
            (dirs["task_dir"] / "logs.txt").write_text("task log\n", encoding="utf-8")
            (dirs["outputs_dir"] / "output.glb").write_text("glb", encoding="utf-8")

            logs = client.get(f"/api/tasks/{task_id}/logs")
            assert logs.status_code == 200, logs.text
            assert "task log" in logs.text

            outputs = client.get(f"/api/tasks/{task_id}/outputs")
            assert outputs.status_code == 200, outputs.text
            output_items = outputs.json()["items"]
            assert output_items[0]["relative_path"] == "output.glb"

            download = client.get(f"/api/tasks/{task_id}/outputs/output.glb")
            assert download.status_code == 200, download.text
            assert download.content == b"glb"

            queued: list[str] = []

            async def fake_enqueue(enqueued_task_id: str) -> None:
                queued.append(enqueued_task_id)

            original_enqueue = TASK_QUEUE.enqueue
            try:
                TASK_QUEUE.enqueue = fake_enqueue
                retry = client.post(f"/api/tasks/{task_id}/retry")
            finally:
                TASK_QUEUE.enqueue = original_enqueue
            assert retry.status_code == 200, retry.text
            assert retry.json()["status"] == "Pending"
            assert queued == [task_id]

    print("api smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
