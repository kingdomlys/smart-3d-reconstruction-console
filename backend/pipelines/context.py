from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


EventEmitter = Callable[[dict[str, Any]], None]


def _noop_emit(_: dict[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class PipelineContext:
    task_id: str
    mode: str
    inputs_dir: Path
    interim_dir: Path
    outputs_dir: Path
    logs_path: Path
    emit_event: EventEmitter = _noop_emit

    def emit(self, payload: dict[str, Any]) -> None:
        self.emit_event(payload)

    def log(self, message: str) -> None:
        self.logs_path.parent.mkdir(parents=True, exist_ok=True)
        with self.logs_path.open("a", encoding="utf-8") as file:
            file.write(message.rstrip() + "\n")

    def emit_json(self, payload: dict[str, Any]) -> None:
        print(json.dumps(payload), flush=True)
