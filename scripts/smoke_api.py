from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import app


def make_image() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (64, 64), "white").save(stream, format="PNG")
    stream.seek(0)
    return stream


def main() -> int:
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

    print("api smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
