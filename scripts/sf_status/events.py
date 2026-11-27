"""Append-only event log: one JSON line per event, one write per line.

Readers keep a byte offset per project in markers/<reader>.json.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_LINE = 4000  # bytes; one O_APPEND write per line puts every line at the end of the file, the limit keeps lines small
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
LOCAL_STATES = ("ok", "failed")
STATES = ("running", "waiting", "blocked", "done")
LEVELS = ("approval", "decision", "info", "warning")

# kind -> (required fields, optional fields); time/project/strand/kind are common
SCHEMA: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "report": (("state", "text"), ("progress", "branch", "waiting_for", "source")),
    "start": (("topic", "text"), ("wave",)),
    "question": (("id", "question", "background", "recommendation"), ()),
    "answer": (("question_id", "text"), ()),
    "task": (("id", "title", "why"), ()),
    "task_done": (("id",), ()),
    "notice": (("level", "title", "text"), ()),
    "dismiss": (("notice_time", "notice_title"), ("by",)),
    "stall": (("session", "minutes"), ()),
    "local_request": (("id", "step", "branch", "commit"), ("note",)),
    "local_result": (("request_id", "state", "text"), ()),
    "delivered": (("seq",), ()),
    "project_added": ((), ()),
    "project_removed": ((), ()),
}
ID_FIELDS = ("id", "question_id", "request_id")


def valid_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.fullmatch(value))


def events_file(state_dir: Path, project: str) -> Path:
    if not valid_id(project):
        raise ValueError(f"invalid project id: {project!r}")
    return Path(state_dir) / "events" / f"{project}.jsonl"


def _validate(project: str, event: dict) -> None:
    kind = event.get("kind")
    if kind not in SCHEMA:
        raise ValueError(f"unknown event kind: {kind!r}")
    if not valid_id(project):
        raise ValueError(f"invalid project id: {project!r}")
    if not valid_id(event.get("strand")):
        raise ValueError(f"invalid strand id: {event.get('strand')!r}")
    required, optional = SCHEMA[kind]
    for name in required:
        if name not in event:
            raise ValueError(f"event kind {kind!r} needs field {name!r}")
    extra = set(event) - set(required) - set(optional) - {"kind", "strand", "time", "project"}
    if extra:
        raise ValueError(f"unexpected fields for {kind!r}: {', '.join(sorted(extra))}")
    for name in ID_FIELDS:
        if name in event and not valid_id(event[name]):
            raise ValueError(f"invalid id in field {name!r}: {event[name]!r}")
    if kind == "task_done" and not valid_id(event["id"]):
        raise ValueError("invalid task id")
    if kind == "report" and event["state"] not in STATES:
        raise ValueError(f"invalid state: {event['state']!r}")
    if kind == "notice" and event["level"] not in LEVELS:
        raise ValueError(f"invalid level: {event['level']!r}")
    if kind == "dismiss":
        for name in ("notice_time", "notice_title"):
            if not (isinstance(event[name], str) and event[name]):
                raise ValueError(f"{name} must be a non-empty string")
        if "by" in event and not (isinstance(event["by"], str) and event["by"]):
            raise ValueError("by must be a non-empty string")
    if kind == "local_request":
        if not valid_id(event["step"]):
            raise ValueError(f"invalid step: {event['step']!r}")
        if not (isinstance(event["branch"], str) and BRANCH_RE.fullmatch(event["branch"])):
            raise ValueError(f"invalid branch: {event['branch']!r}")
        if not (isinstance(event["commit"], str) and COMMIT_RE.fullmatch(event["commit"])):
            raise ValueError(f"invalid commit: {event['commit']!r}")
    if kind == "local_result" and event["state"] not in LOCAL_STATES:
        raise ValueError(f"invalid local state: {event['state']!r}")
    progress = event.get("progress")
    if progress is not None and (
        not isinstance(progress, int) or isinstance(progress, bool) or not 0 <= progress <= 100
    ):
        raise ValueError("progress must be an integer from 0 to 100")


def append(state_dir: Path, project: str, event: dict, now: datetime | None = None) -> dict:
    """Validate and append one event; returns the stored event (with time and project)."""
    _validate(project, event)
    now = now or datetime.now(timezone.utc)
    stored = {**event, "time": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "project": project}
    raw = (json.dumps(stored, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    if len(raw) > MAX_LINE:
        raise ValueError(f"event too long ({len(raw)} bytes, at most {MAX_LINE}); shorten the text")
    target = events_file(state_dir, project)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if os.write(fd, raw) != len(raw):
            raise OSError("event written only partially")
    finally:
        os.close(fd)
    return stored


def read(state_dir: Path, project: str, offset: int = 0) -> tuple[list[dict], int]:
    """Complete lines from a byte offset; returns (events, new offset)."""
    target = events_file(state_dir, project)
    try:
        with open(target, "rb") as f:
            f.seek(offset)
            data = f.read()
    except FileNotFoundError:
        return [], offset
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    out = []
    for line in data[: end + 1].splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue  # skip a corrupt line, never crash
        if isinstance(item, dict):
            out.append(item)
    return out, offset + end + 1


def _marker_path(state_dir: Path, reader: str) -> Path:
    if not valid_id(reader):
        raise ValueError(f"invalid reader name: {reader!r}")
    return Path(state_dir) / "markers" / f"{reader}.json"


def load_marker(state_dir: Path, reader: str) -> dict[str, int]:
    try:
        data = json.loads(_marker_path(state_dir, reader).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, int) and not isinstance(v, bool) and v >= 0}


def save_marker(state_dir: Path, reader: str, offsets: dict[str, int]) -> None:
    target = _marker_path(state_dir, reader)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(offsets, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)


def load_json(path: Path) -> dict:
    """A JSON object from `path`; {} if missing, unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: dict) -> None:
    """Atomic write (temp file, then replace); creates the folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def open_questions(events: list[dict]) -> dict[str, dict]:
    """Questions without an answer, by question id."""
    asked: dict[str, dict] = {}
    for e in events:
        if e.get("kind") == "question" and isinstance(e.get("id"), str):
            asked[e["id"]] = e
        elif e.get("kind") == "answer":
            qid = e.get("question_id")
            if isinstance(qid, str):
                asked.pop(qid, None)
    return asked


def open_local(events: list[dict]) -> dict[str, dict]:
    """Local step requests without a result, by request id, in file order."""
    pending: dict[str, dict] = {}
    for e in events:
        if e.get("kind") == "local_request" and isinstance(e.get("id"), str):
            pending[e["id"]] = e
        elif e.get("kind") == "local_result":
            rid = e.get("request_id")
            if isinstance(rid, str):
                pending.pop(rid, None)
    return pending


def next_local_id(events: list[dict], strand: str) -> str:
    """Next request id for a strand: <strand>-l<n>, n = 1 + its earlier local requests."""
    n = sum(1 for e in events if e.get("kind") == "local_request" and e.get("strand") == strand)
    return f"{strand}-l{n + 1}"
