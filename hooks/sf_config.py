"""Shared per-user settings loader for the software-factory hooks.

Reads ~/.claude/software-factory.json. Standard library only. Never raises:
any problem falls back to defaults, validated per field.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODE = "block"
VALID_MODES = ("block", "warn")
DEFAULT_THRESHOLDS = (150000, 300000)


@dataclass(frozen=True)
class Config:
    mode: str
    thresholds: tuple[int, int]
    state_dir: Path


def _valid_thresholds(value) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    if any(type(v) is not int or v <= 0 for v in value):
        return False
    return value[0] < value[1]


def load_config(home: Path | None = None) -> Config:
    base = (home if home is not None else Path.home()) / ".claude"
    state_dir = base / "software-factory" / "state"
    data: dict = {}
    try:
        loaded = json.loads((base / "software-factory.json").read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError):
        pass

    mode = data.get("mode")
    if not (isinstance(mode, str) and mode in VALID_MODES):
        mode = DEFAULT_MODE
    raw = data.get("context_thresholds")
    thresholds = (raw[0], raw[1]) if _valid_thresholds(raw) else DEFAULT_THRESHOLDS
    return Config(mode=mode, thresholds=thresholds, state_dir=state_dir)
