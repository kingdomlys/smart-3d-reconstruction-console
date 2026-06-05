from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .context import PipelineContext


@dataclass(frozen=True)
class PipelineResult:
    primary_output_path: Path
    output_types: list[str]
    outputs: dict[str, Path] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class Pipeline(Protocol):
    id: str
    name: str
    output_types: list[str]

    def supports(self, image_count: int, mode: str) -> bool:
        ...

    def run(self, context: PipelineContext) -> PipelineResult:
        ...
