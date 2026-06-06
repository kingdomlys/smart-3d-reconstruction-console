from __future__ import annotations

import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.storage import save_uploads, validate_uploads


class InMemoryUpload:
    def __init__(self, filename: str, size: tuple[int, int]) -> None:
        stream = BytesIO()
        Image.new("RGB", size, "white").save(stream, format="PNG")
        stream.seek(0)
        self.filename = filename
        self.file = stream


def expect_error(label: str, uploads: list[InMemoryUpload]) -> None:
    try:
        validate_uploads(uploads)
    except Exception as exc:
        detail = getattr(exc, "detail", {})
        print(f"{label}: {type(exc).__name__} - {detail.get('error')}")
        return
    raise AssertionError(f"{label}: expected validation error")


def main() -> int:
    with TemporaryDirectory() as tmp:
        upload = InMemoryUpload("../unsafe name.png", (1920, 1080))
        validate_uploads([upload])
        saved = save_uploads([upload], Path(tmp))
        print(f"safe_name: {saved[0].name}")
        if saved[0].name != "01_unsafe_name.png":
            raise AssertionError(f"unexpected saved filename: {saved[0].name}")

    expect_error("oversize", [InMemoryUpload("too_large.png", (1921, 1080))])
    expect_error("too_many", [InMemoryUpload(f"image_{i}.png", (64, 64)) for i in range(17)])

    import backend.app.storage as storage_module

    original_settings = storage_module.SETTINGS
    storage_module.SETTINGS = replace(original_settings, max_upload_bytes=16)
    try:
        expect_error("too_large_bytes", [InMemoryUpload("too_large_bytes.png", (64, 64))])
    finally:
        storage_module.SETTINGS = original_settings

    print("upload validation smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
