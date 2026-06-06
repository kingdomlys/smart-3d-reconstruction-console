from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import db


def main() -> int:
    with TemporaryDirectory() as tmp:
        task_root = Path(tmp) / "tasks"
        os.environ["TASKS_ROOT"] = str(task_root)
        db.DB_PATH = Path(tmp) / "tasks.db"

        import backend.app.settings as settings_module
        import backend.app.storage as storage_module

        storage_module.SETTINGS = settings_module.Settings.from_env()

        db.init_db()
        db.create_task("smoke-assets", mode="fast", image_count=2)
        outputs_dir = task_root / "smoke-assets" / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "output.glb").write_text("glb", encoding="utf-8")
        (outputs_dir / "point_cloud.ply").write_text("ply", encoding="utf-8")
        (outputs_dir / "scene.splat").write_text("splat", encoding="utf-8")
        (outputs_dir / "pointcloud_front_xy.png").write_text("png", encoding="utf-8")
        (outputs_dir / "notes.md").write_text("ignored", encoding="utf-8")

        outputs = storage_module.list_output_files("smoke-assets")
        output_types = {item["type"] for item in outputs}
        relative_paths = {item["relative_path"] for item in outputs}

        assert output_types == {"glb", "ply", "png", "splat"}, output_types
        assert relative_paths == {
            "output.glb",
            "point_cloud.ply",
            "pointcloud_front_xy.png",
            "scene.splat",
        }, relative_paths
        for item in outputs:
            assert item["download_url"].startswith("/api/tasks/smoke-assets/outputs/")

    print("output asset smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
