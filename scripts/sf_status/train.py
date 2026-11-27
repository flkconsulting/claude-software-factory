"""Release train cut-off: when the weekly train question is due, once per date.

The marker markers/train.json keeps, per project, the dates already handled
({"<project>": {"dates": {"<date>": "due|skipped|missed"}, "questions": {...}}}). check() only
computes; the caller records the result in "dates" and saves the marker (see wake.commit_triggers).
Settings that cannot be parsed (a hand-edited projects.json) mean "no train", never a crash.
"""
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .projects import TRAIN_DAYS, Project

CATCH_UP = timedelta(hours=24)
TIME_RE = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])", re.ASCII)


@dataclass
class Due:
    date: str
    kind: str  # due | skipped | missed


def _settings(project: Project) -> tuple[int, time, ZoneInfo]:
    """(weekday number, local time, zone); raises ValueError/KeyError on unusable settings."""
    m = TIME_RE.fullmatch(project.train_time)
    if m is None:
        raise ValueError("bad train time")
    return TRAIN_DAYS.index(project.train_day), time(int(m[1]), int(m[2])), ZoneInfo(project.train_tz)


def cutoff(project: Project, day: date) -> datetime:
    """Aware UTC moment of the cut-off on `day`: train_time local in train_tz (a DST gap uses the usual offset)."""
    _, at, zone = _settings(project)
    return datetime.combine(day, at, tzinfo=zone).astimezone(timezone.utc)


def check(project: Project, marker: dict, now: datetime) -> Due | None:
    if not project.train:
        return None
    try:
        weekday, _, zone = _settings(project)
        day = now.astimezone(zone).date()
        day -= timedelta(days=(day.weekday() - weekday) % 7)
        if cutoff(project, day) > now:
            day -= timedelta(days=7)
        at = cutoff(project, day)
    except (ValueError, KeyError, OSError, OverflowError):  # bad day/time, unknown zone (KeyError), no zone data
        return None
    key = day.isoformat()
    entry = marker.get(project.name)
    if isinstance(entry, dict) and isinstance(entry.get("dates"), dict) and key in entry["dates"]:
        return None
    if key in project.train_skip:
        return Due(key, "skipped")
    return Due(key, "due" if now - at <= CATCH_UP else "missed")


def load_marker(state_dir: Path) -> dict:
    try:
        data = json.loads((Path(state_dir) / "markers" / "train.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("dates", {}), dict)}


def save_marker(state_dir: Path, data: dict) -> None:
    path = Path(state_dir) / "markers" / "train.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
