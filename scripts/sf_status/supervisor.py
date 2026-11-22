"""Supervisor short run: one headless claude run per bundle of open triggers.

Single instance through a non-blocking flock on supervisor/supervisor.lock (the kernel frees it when
the process dies). The tries counter is raised before the run, so a crash cannot loop forever. Triggers
leave the open list only on proven success: exit 0, no is_error, notes.md newer than before.
The prompt carries fixed words and trigger ids only, never free text from events.
"""
import contextlib
import fcntl
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import effects, events
from .config import ServerConfig
from . import projects

TRIGGER_RE = re.compile(r"^[a-z]+(:[a-z0-9-]+)*$")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
RETRY = "retry"
NOTICE_STRAND = "supervisor"


def build_prompt(trigger_ids: list[str], aborted_before: bool, task_file: Path, notes_file: Path) -> str:
    head = "The last run was aborted - check status and tmux first, start nothing twice. " if aborted_before else ""
    return (f"{head}Read {task_file} and {notes_file}. "
            f"Handle exactly these triggers: {'; '.join(trigger_ids)}. Update {notes_file} at the end.")


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime(TIME_FORMAT)


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


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _triggers(path: Path) -> dict:
    data = _load(path)
    items = [i for i in data.get("open", []) if isinstance(i, dict) and isinstance(i.get("id"), str)]
    for i in items:
        if not isinstance(i.get("tries"), int):
            i["tries"] = 0
    parked = [p for p in data.get("parked", []) if isinstance(p, dict)]
    return {"open": items, "parked": parked, "last_run": data.get("last_run")}


def _notice(state_dir: Path, project: str | None, title: str, text: str, now: datetime) -> None:
    if project is None:
        return
    with contextlib.suppress(OSError, ValueError):
        events.append(state_dir, project, {"kind": "notice", "strand": NOTICE_STRAND, "level": "warning",
                                           "title": title, "text": text}, now)


def _supervisor_project(state_dir: Path):
    for p in projects.load(state_dir):
        if p.supervisor:
            return p
    return None


def run_once(cfg: ServerConfig, state_dir: Path, now: datetime) -> str:
    """Returns busy, nothing, ok, failed, timeout or parked."""
    state_dir = Path(state_dir)
    base = state_dir / "supervisor"
    base.mkdir(parents=True, exist_ok=True)
    lock_path = base / "supervisor.lock"
    lock = open(lock_path, "a+")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _busy(cfg, state_dir, lock_path, now)
            return "busy"
        os.utime(lock_path, (now.timestamp(), now.timestamp()))  # holder start time, read by waiting runs
        with contextlib.suppress(OSError):
            (base / "busy-notice").unlink()
        return _locked(cfg, state_dir, base, now)
    finally:
        lock.close()


def _busy(cfg: ServerConfig, state_dir: Path, lock_path: Path, now: datetime) -> None:
    started = _mtime(lock_path)
    flag = lock_path.with_name("busy-notice")
    if not started or now.timestamp() - started < cfg.supervisor_busy_minutes * 60 or flag.exists():
        return
    project = _supervisor_project(state_dir)
    _notice(state_dir, project.name if project else None, "supervisor run takes long",
            f"The supervisor run has held its lock for more than {cfg.supervisor_busy_minutes} minutes.", now)
    with contextlib.suppress(OSError):
        flag.write_text(_stamp(now), encoding="utf-8")


def _locked(cfg: ServerConfig, state_dir: Path, base: Path, now: datetime) -> str:
    if (base / "pause").exists():
        return "nothing"
    path = base / "triggers.json"
    data = _triggers(path)
    if not data["open"]:
        return "nothing"
    project = _supervisor_project(state_dir)
    aborted = any(i["tries"] > 0 for i in data["open"])  # an earlier run never proved success
    gone = [i for i in data["open"] if i["tries"] >= cfg.retry_limit]  # retry_limit real runs are used up
    data["open"] = [i for i in data["open"] if i["tries"] < cfg.retry_limit]
    for i in data["open"]:
        i["tries"] += 1
    data["parked"] = data["parked"] + gone
    _atomic(path, data)
    if gone:
        _notice(state_dir, project.name if project else None, "supervisor triggers parked",
                f"{len(gone)} trigger(s) parked after {cfg.retry_limit} tries; see supervisor/triggers.json.", now)
    run_ids = [i["id"] for i in data["open"] if TRIGGER_RE.match(i["id"])]
    if not data["open"]:
        return "parked"
    if project is None or not run_ids:
        return "nothing"

    task_file, notes_file = base / "task.md", base / "notes.md"
    before = _mtime(notes_file)
    env = {**os.environ, "SF_SOURCE": "supervisor"}
    try:
        code, answer = effects.run_claude(build_prompt(run_ids, aborted, task_file, notes_file), project.folder,
                                          cfg.supervisor_model, cfg.supervisor_timeout_minutes * 60, env)
    except Exception:  # unexpected: treat like a failure, never loop forever (tries are already counted)
        code, answer = 1, None
    answer = answer if isinstance(answer, dict) else {}
    end = effects.now()
    is_error = code != 0 or bool(answer.get("is_error"))
    ok = not is_error and _mtime(notes_file) > before
    result = "ok" if ok else ("timeout" if code == 124 else "failed")

    fresh = _triggers(path)  # triggers raised during the run stay
    if ok:
        fresh["open"] = [i for i in fresh["open"] if i["id"] not in run_ids]
    elif not any(i["id"] == RETRY for i in fresh["open"]):
        fresh["open"].append({"id": RETRY, "since": _stamp(end), "tries": 0})
    fresh["last_run"] = _stamp(now)
    _atomic(path, fresh)
    if not ok:
        _notice(state_dir, project.name, "supervisor run failed",
                "The supervisor run hit its time limit." if result == "timeout"
                else f"The supervisor run did not finish properly (exit {code}).", end)
    cost = answer.get("total_cost_usd")
    record = {"start": _stamp(now), "end": _stamp(end), "exit": code, "result": result, "triggers": run_ids,
              "cost_usd": cost if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None}
    with contextlib.suppress(OSError):
        _atomic(base / "runs" / f"{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json", record)
    return result
