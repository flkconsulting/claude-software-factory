"""Wake triggers: what makes the supervisor run. Fixed words and ids only, never free text.

collect_triggers() reads and computes, it changes nothing on disk. commit_triggers() first
adopts the triggers into supervisor/triggers.json and only then advances markers/wake.json,
so a failed write leaves everything to be found again by the next run.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import events, train
from .config import ServerConfig
from .projects import Project
from .supervisor import triggers_lock
from .wave_plan import parse_wave_plan

READER = "wake"
DEBOUNCE = timedelta(hours=6)
DEBOUNCED_STATES = ("done", "blocked")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
STATE_KEYS = ("rows", "seen", "last_safety")


class Triggers(list):
    """Trigger ids plus the marker state to write once they are adopted."""

    pending: dict
    notices: list  # (project, sanitized short cell) of approved rows that cannot become a trigger
    train_marks: dict  # new markers/train.json content
    train_notices: list  # (project, level, title, text) for skipped / missed train dates


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime(TIME_FORMAT)


def _parse(value) -> datetime | None:
    try:
        return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _approved_rows(project: Project) -> dict[str, str] | None:
    """{row hash: short} of approved rows; None if the plan cannot be read."""
    try:
        text = (Path(project.folder) / project.wave_plan).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return {r.row_hash: r.short for r in parse_wave_plan(text) if r.approved}


def collect_triggers(cfg: ServerConfig, projects: list[Project], state_dir: Path, now: datetime) -> Triggers:
    state_dir = Path(state_dir)
    stored = _load(state_dir / "markers" / f"{READER}.json")
    offsets = events.load_marker(state_dir, READER)
    rows: dict[str, bool] = dict(stored["rows"]) if isinstance(stored.get("rows"), dict) else {}
    seen = {k: v for k, v in (stored.get("seen") or {}).items()
            if isinstance(stored.get("seen"), dict) and (t := _parse(v)) and now - t < DEBOUNCE}
    found = Triggers()
    found.notices = []
    found.train_notices = []
    train_marks = train.load_marker(state_dir)
    new_offsets = dict(offsets)

    def add(trigger: str, debounce: bool) -> None:
        if trigger in found or (debounce and trigger in seen):
            return
        found.append(trigger)
        if debounce:
            seen[trigger] = _stamp(now)

    for project in projects:
        evs, new_offsets[project.name] = events.read(state_dir, project.name, offsets.get(project.name, 0))
        if not project.supervisor:
            continue
        for e in evs:
            strand, kind = e.get("strand"), e.get("kind")
            if strand == "supervisor" and kind not in ("answer", "local_result"):  # written by the human / the laptop
                continue
            if kind == "report" and e.get("state") in DEBOUNCED_STATES and events.valid_id(strand):
                add(f"{e['state']}:{strand}", True)
            elif kind == "answer" and events.valid_id(e.get("question_id")):
                add(f"answer:{e['question_id']}", False)
            elif kind == "local_result" and events.valid_id(e.get("request_id")):
                add(f"local:{e['request_id']}", False)
            elif kind == "stall" and events.valid_id(strand):
                add(f"stall:{strand}", True)
        due = train.check(project, train_marks, now)
        if due is not None:
            entry = train_marks.setdefault(project.name, {})
            entry.setdefault("dates", {})[due.date] = due.kind
            entry.setdefault("questions", {})
            if due.kind == "due":
                add(f"train:{due.date}", False)
            else:
                level = "info" if due.kind == "skipped" else "warning"
                found.train_notices.append((project.name, level, f"Train {due.date} {due.kind}",
                                            f"The train cut-off of {due.date} was {due.kind}; no train question was asked."))
        approved = _approved_rows(project)
        if approved is None:
            continue
        for row_hash, short in sorted(approved.items(), key=lambda kv: kv[1]):
            key = f"{project.name}/{row_hash}"
            if key in rows:
                continue
            if events.valid_id(short.lower()):
                rows[key] = True
                add(f"approved:{short.lower()}", False)
            else:  # remembered with False so the warning comes once per row hash
                rows[key] = False
                found.notices.append((project.name, re.sub(r"[^A-Za-z0-9 _.-]", "?", short)[:40]))

    last = _parse(stored.get("last_safety"))
    last_safety = stored.get("last_safety") if last else None
    if any(p.supervisor for p in projects) and (last is None or now - last >= timedelta(hours=cfg.safety_pass_hours)):
        add("safety", False)
        last_safety = _stamp(now)

    found.train_marks = train_marks
    found.pending = {**new_offsets, "rows": rows, "seen": seen}
    if last_safety:
        found.pending["last_safety"] = last_safety
    return found


def commit_triggers(state_dir: Path, triggers: Triggers, now: datetime | None = None) -> None:
    """Adopt triggers into supervisor/triggers.json, then advance the marker. Raises OSError on failure."""
    state_dir = Path(state_dir)
    path = state_dir / "supervisor" / "triggers.json"
    when = now or datetime.now(timezone.utc)
    since = _stamp(when)
    with triggers_lock(state_dir):  # shared with the supervisor's writes
        data = _load(path)
        open_items = [i for i in data.get("open", []) if isinstance(i, dict) and "id" in i]
        known = {i["id"] for i in open_items}
        for trigger in triggers:
            if trigger not in known:
                open_items.append({"id": trigger, "since": since, "tries": 0})
                known.add(trigger)
        data["open"] = open_items
        data.setdefault("parked", [])
        data.setdefault("last_run", None)
        _atomic(path, data)
    for project, short in triggers.notices:
        events.append(state_dir, project, {
            "kind": "notice", "strand": "server", "level": "warning", "title": "wave plan row skipped",
            "text": f"Approved row with short {short!r} has no valid id (a-z, 0-9, hyphens) and starts nothing."}, when)
    for project, level, title, text in triggers.train_notices:
        events.append(state_dir, project, {"kind": "notice", "strand": "server", "level": level,
                                           "title": title, "text": text}, when)
    if triggers.train_marks:
        train.save_marker(state_dir, triggers.train_marks)
    _atomic(state_dir / "markers" / f"{READER}.json", triggers.pending)


def fast_forward(cfg: ServerConfig, projects: list[Project], state_dir: Path, now: datetime) -> None:
    """Set all wake markers to now without raising triggers; afterwards only new things wake."""
    triggers = collect_triggers(cfg, projects, state_dir, now)
    pending = dict(triggers.pending)
    pending["last_safety"] = _stamp(now)
    if triggers.train_marks:
        train.save_marker(state_dir, triggers.train_marks)
    _atomic(Path(state_dir) / "markers" / f"{READER}.json", pending)
