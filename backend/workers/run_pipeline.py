from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.context import PipelineContext
from backend.pipelines.registry import get_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a project pipeline")
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mode", default="fast")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--interim-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--logs-path", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = get_pipeline(args.pipeline)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    context = PipelineContext(
        task_id=args.task_id,
        mode=args.mode,
        inputs_dir=Path(args.input_dir),
        interim_dir=Path(args.interim_dir),
        outputs_dir=output_dir,
        logs_path=Path(args.logs_path),
        emit_event=lambda payload: print_payload(payload),
    )
    pipeline.run(context)
    return 0


def print_payload(payload: dict) -> None:
    import json

    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
