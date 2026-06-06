from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.commands import split_command


def main() -> int:
    command = r'"C:\Users\demo env\python.exe" "C:\repo path\worker.py" --flag value'
    parts = split_command(command)
    assert parts[0] == r"C:\Users\demo env\python.exe", parts
    assert parts[1] == r"C:\repo path\worker.py", parts
    assert parts[2:] == ["--flag", "value"], parts
    print("command split smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
