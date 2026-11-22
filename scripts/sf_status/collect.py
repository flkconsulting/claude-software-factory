"""State collector: reads events, report files and tmux; writes only its own events and markers.

Events are written before the markers that remember them. Strands are never restarted.
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import effects, events, stall, usage as usage_mod
from .config import ServerConfig
from .projects import SYSTEM_STRAND, Project, project_for_path

REPORT_STATES = {"DONE": "done", "BLOCKED": "blocked"}
NOTICE_DAYS = 7
MAX_NOTICES = 50
MAX_RECENT = 20
MAX_RUNS = 5
HUMAN_WAIT = ("human", "heavy-run")
SUPERVISOR_STRAND = "supervisor"  # runs without a tmux session
PRICES_FILE = Path(__file__).with_name("prices.json")


@dataclass
class StrandView:
    project: str
    strand: str
    state: str
    since: str
    branch: str | None = None
    text: str = ""
    stalled: bool = False


@dataclass
class State:
    strands: dict[str, StrandView] = field(default_factory=dict)
    questions: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    notices: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)
    usage: dict | None = None
    recent: list[dict] = field(default_factory=list)
    triggers: dict | None = None  # supervisor/triggers.json content, filled by render.write


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sorted(evs: list[dict]) -> list[dict]:
    return sorted(evs, key=lambda e: (str(e.get("time", "")), str(e.get("strand", "")), str(e.get("kind", ""))))


def _last_reports(evs: list[dict]) -> dict[str, dict]:
    last: dict[str, dict] = {}
    for e in evs:
        if e.get("kind") == "report" and e.get("strand"):
            last[e["strand"]] = e
    return last


def _strand_view(project: str, strand: str, reports: list[dict]) -> StrandView:
    since, state, branch = "", "", None
    for e in reports:
        if e.get("state") != state:
            state, since = e.get("state", ""), e.get("time", "")
        branch = e.get("branch") or branch
    return StrandView(project, strand, state, since, branch, str(reports[-1].get("text", "")))


def _read_reports(state_dir: Path, project: str) -> list[tuple[str, str]]:
    """(short, first line) of every report file of a project."""
    out = []
    folder = state_dir / "reports" / project
    try:
        files = sorted(folder.glob("*.md"))
    except OSError:
        return out
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                first = fh.readline().strip()
        except OSError:
            continue
        if events.valid_id(f.stem):
            out.append((f.stem, first))
    return out


def _report_events(state_dir: Path, projects: list[Project], now: datetime) -> set[str]:
    """Write one report event per new first line; returns "<project>/<short>" of all report files."""
    marker_path = state_dir / "markers" / "reports.json"
    marker = _load_json(marker_path)
    new = dict(marker)
    present: set[str] = set()
    for p in projects:
        for short, line in _read_reports(state_dir, p.name):
            key = f"{p.name}/{short}"
            present.add(key)
            if marker.get(key) == line:
                continue
            parts = line.rsplit(" ", 1)
            if len(parts) == 2 and parts[1] in REPORT_STATES:
                events.append(state_dir, p.name, {"kind": "report", "strand": short,
                                                  "state": REPORT_STATES[parts[1]],
                                                  "text": f"Report: {line}"[:500], "source": "report-file"}, now)
            new[key] = line
    if new != marker:
        _save_json(marker_path, new)
    return present


def _runs(state_dir: Path) -> list[dict]:
    out = []
    for f in (state_dir / "supervisor" / "runs").glob("*.json"):
        d = _load_json(f)
        if d:
            out.append(d)
    out.sort(key=lambda d: str(d.get("start", "")), reverse=True)
    return out[:MAX_RUNS]


def _reset_stall(entry: dict) -> bool:
    """Forget the pane hash and stall start, so a resumed strand is measured anew."""
    changed = any(k in entry for k in ("hash", "since")) or bool(entry.get("reported"))
    entry.pop("hash", None)
    entry.pop("since", None)
    entry["reported"] = False
    return changed


def collect(cfg: ServerConfig, projects: list[Project], now: float,
            transcripts_root: Path | None = None) -> State:
    state_dir = Path(cfg.state_dir)
    when = datetime.fromtimestamp(now, timezone.utc)
    limit_s = cfg.stall_minutes * 60

    def write(project: str, event: dict) -> None:
        events.append(state_dir, project, event, when)

    report_files = _report_events(state_dir, projects, when)

    def load_events(project: str) -> list[dict]:
        return _sorted(events.read(state_dir, project)[0])

    per_project = {p.name: load_events(p.name) for p in projects}
    last = {p: _last_reports(evs) for p, evs in per_project.items()}

    # tmux sessions -> (project, strand); strand None means unknown
    sessions: dict[str, tuple[str, str | None]] = {}
    for name, path in effects.tmux_sessions():
        project = project_for_path(projects, Path(path))
        if project is None:
            continue
        strand = name.removeprefix(project + "-") if name.startswith(project + "-") else None
        sessions[name] = (project, strand if strand in last[project] else None)

    marker_path = state_dir / "markers" / "stall.json"
    marker = {k: dict(v) for k, v in _load_json(marker_path).items() if isinstance(v, dict)}
    wrote = False

    for name, (project, strand) in sorted(sessions.items()):
        entry = marker.setdefault(name, {})
        if strand is None:
            if not entry.get("hinted"):
                write(project, {"kind": "notice", "strand": SYSTEM_STRAND, "level": "info",
                                "title": f"{name}: unknown tmux session",
                                "text": f"{name}: tmux session in this project does not belong to a known "
                                        "strand. Register it with sf-status report or close it."})
                entry["hinted"] = True
                wrote = True
            continue
        if strand == SUPERVISOR_STRAND:
            continue
        rep = last[project][strand]
        entry["gone"] = False
        if rep.get("state") not in ("running", "waiting") or (
                rep.get("state") == "waiting"
                and any(w in str(rep.get("waiting_for", "")).lower() for w in HUMAN_WAIT)):
            if _reset_stall(entry):
                wrote = True
            continue
        pane = effects.capture_pane(name)
        if pane is None:
            continue
        marker[name], report_now = stall.check(entry, stall.pane_hash(pane), now, limit_s)
        if report_now:
            minutes = int((now - float(marker[name].get("since", now))) // 60)
            write(project, {"kind": "stall", "strand": strand, "session": name, "minutes": minutes})
            write(project, {"kind": "notice", "strand": strand, "level": "warning",
                            "title": f"{strand}: possibly stalled",
                            "text": f"{name}: screen unchanged for {minutes} min, possibly stalled."})
        wrote = True

    # expected sessions that are gone (running/waiting, no report file, no tmux session)
    for name, entry in marker.items():
        if name not in sessions and _reset_stall(entry):
            wrote = True
    for project, reps in last.items():
        for strand, rep in sorted(reps.items()):
            name = f"{project}-{strand}"
            if strand == SUPERVISOR_STRAND:
                continue
            if (rep.get("state") not in ("running", "waiting") or name in sessions
                    or f"{project}/{strand}" in report_files):
                continue
            entry = marker.setdefault(name, {})
            if not entry.get("gone"):
                write(project, {"kind": "notice", "strand": strand, "level": "info",
                                "title": f"{strand}: tmux session missing",
                                "text": f"{name}: tmux session not found and no report. Please check."})
                entry["gone"] = True
                wrote = True
    if wrote:
        _save_json(marker_path, marker)

    # build the view from the events as they are now
    all_events: list[dict] = []
    result = State()
    cutoff = _iso(now - NOTICE_DAYS * 86400)
    open_q: list[dict] = []
    tasks: dict[tuple[str, str], dict] = {}
    for p in projects:
        evs = load_events(p.name)
        all_events.extend(evs)
        by_strand: dict[str, list[dict]] = {}
        for e in evs:
            if e.get("kind") == "report" and e.get("strand"):
                by_strand.setdefault(e["strand"], []).append(e)
            elif e.get("kind") == "task" and isinstance(e.get("id"), str):
                tasks[(p.name, e["id"])] = e
            elif e.get("kind") == "task_done":
                tasks.pop((p.name, e.get("id")), None)
        open_q.extend(events.open_questions(evs).values())
        for strand, reps in by_strand.items():
            view = _strand_view(p.name, strand, reps)
            m = marker.get(f"{p.name}-{strand}", {})
            view.stalled = bool(m.get("reported")) and not m.get("gone") and view.state in ("running", "waiting")
            result.strands[f"{p.name}/{strand}"] = view
    all_events = _sorted(all_events)
    result.questions = _sorted(open_q)
    result.tasks = _sorted(list(tasks.values()))
    result.notices = [e for e in all_events if e.get("kind") == "notice" and str(e.get("time", "")) >= cutoff][-MAX_NOTICES:]
    result.recent = all_events[-MAX_RECENT:]
    result.runs = _runs(state_dir)
    if cfg.usage_report:
        try:
            root = transcripts_root if transcripts_root is not None else usage_mod.DEFAULT_ROOT
            result.usage = usage_mod.summarize(root, when.date(), usage_mod.load_prices(PRICES_FILE), projects)
        except Exception:  # the report is optional; a changed transcript format must not stop the run
            result.usage = None
    return result
