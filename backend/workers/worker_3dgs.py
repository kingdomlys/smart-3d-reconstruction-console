from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.context import PipelineContext
from backend.pipelines.gaussian_splatting import GaussianSplattingPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="3DGS pipeline compatibility worker")
    parser.add_argument("--interim-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iterations", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("DGS_ITERATIONS", str(args.iterations))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    context = PipelineContext(
        task_id="standalone",
        mode="fast",
        inputs_dir=Path(args.interim_dir).parent / "inputs",
        interim_dir=Path(args.interim_dir),
        outputs_dir=output_dir,
        logs_path=output_dir.parent / "logs.txt",
        emit_event=lambda payload: context_emit(payload),
    )
    GaussianSplattingPipeline().run(context)
    return 0


def context_emit(payload: dict) -> None:
    import json

    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
