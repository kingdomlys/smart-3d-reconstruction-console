from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    with TemporaryDirectory() as tmp:
        os.environ["TASKS_ROOT"] = str(Path(tmp) / "tasks")
        os.environ["TRIPOSR_ALLOW_PLACEHOLDER"] = "1"
        os.environ["VGGT_PY"] = "secret-vggt-python"
        os.environ["COLMAP_BIN"] = "secret-colmap-bin"

        from fastapi.testclient import TestClient

        from backend.app import db
        from backend.app.main import app

        db.DB_PATH = Path(tmp) / "tasks.db"

        with TestClient(app) as client:
            response = client.get("/api/pipelines")
            assert response.status_code == 200, response.text
            payload = response.json()

        items = {item["id"]: item for item in payload["items"]}
        assert set(items) == {"triposr", "vggt", "colmap"}, items
        assert items["triposr"]["placeholder_enabled"] is True
        assert items["triposr"]["ready"] is True
        assert "VGGT_PY" in items["vggt"]["configured_env"]
        assert "COLMAP_BIN" in items["colmap"]["configured_env"]
        assert "secret-vggt-python" not in str(payload)
        assert "secret-colmap-bin" not in str(payload)
        assert payload["limits"]["max_upload_files"] == 16
        assert payload["limits"]["max_upload_bytes"] == 20 * 1024 * 1024

    print("pipeline diagnostics smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
