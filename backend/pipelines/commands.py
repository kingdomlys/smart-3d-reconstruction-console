from __future__ import annotations

import os
import shlex


def split_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=os.name != "nt")
    if os.name != "nt":
        return parts
    return [_strip_wrapping_quotes(part) for part in parts]


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
