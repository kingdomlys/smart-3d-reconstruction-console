from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.colmap import ColmapPipeline
from backend.pipelines.context import PipelineContext


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COLMAP pipeline compatibility worker")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--interim-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interim_dir = Path(args.interim_dir)
    context = PipelineContext(
        task_id="standalone",
        mode="fast",
        inputs_dir=Path(args.input_dir),
        interim_dir=interim_dir,
        outputs_dir=interim_dir.parent / "outputs",
        logs_path=interim_dir.parent / "logs.txt",
        emit_event=lambda payload: context_emit(payload),
    )
    ColmapPipeline().run(context)
    return 0


def context_emit(payload: dict) -> None:
    import json

    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
