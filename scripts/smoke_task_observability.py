from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db
from backend.app.storage import list_output_files, read_task_log, resolve_output_file


def main() -> int:
    with TemporaryDirectory() as tmp:
        task_root = Path(tmp) / "tasks"
        db_path = Path(tmp) / "tasks.db"

        os.environ["TASKS_ROOT"] = str(task_root)
        db.DB_PATH = db_path

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        task = db.create_task("smoke-observe", mode="fast", image_count=1)
        assert task["status"] == "Pending"

        task_dir = task_root / "smoke-observe"
        outputs_dir = task_dir / "outputs"
        outputs_dir.mkdir(parents=True)
        (task_dir / "logs.txt").write_text("line 1\nline 2\n", encoding="utf-8")
        (outputs_dir / "output.glb").write_text("glb", encoding="utf-8")
        (outputs_dir / "ignored.tmp").write_text("tmp", encoding="utf-8")

        assert "line 2" in read_task_log("smoke-observe")
        outputs = list_output_files("smoke-observe")
        assert len(outputs) == 1
        assert outputs[0]["relative_path"] == "output.glb"
        assert resolve_output_file("smoke-observe", "output.glb").name == "output.glb"

        try:
            resolve_output_file("smoke-observe", "../escape.glb")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("path traversal should be rejected")

        interrupted = db.mark_incomplete_tasks_interrupted()
        assert interrupted == 1
        assert db.get_task("smoke-observe")["status"] == "Interrupted"

    print("task observability smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
