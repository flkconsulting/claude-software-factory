"""State collector: reads events, report files and tmux; writes only its own events and markers.

Events are written before the markers that remember them. Strands are never restarted.
"""
import json
import os
from collections.abc import Container
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import checks, effects, events, stall, usage as usage_mod
from .config import ServerConfig
from .planning import load_releases, load_tickets
from .projects import SYSTEM_STRAND, Project, project_for_path

REPORT_STATES = {"DONE": "done", "BLOCKED": "blocked"}
NOTICE_DAYS = 7
MAX_NOTICES = 50
MAX_RECENT = 20
MAX_RUNS = 5
HUMAN_WAIT = ("human", "heavy-run")
SUPERVISOR_STRAND = "supervisor"  # runs without a tmux session
STALL_TITLE = ": possibly stalled"
GONE_TITLE = ": tmux session missing"
FINISHED = ("done", "blocked")
LOCAL_TITLE = ("local step ", " waiting")  # around the request id
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
    local: list[dict] = field(default_factory=list)  # open local step requests, oldest first


_load_json = events.load_json
_save_json = events.save_json


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sort_events(evs: list[dict]) -> list[dict]:
    """Events in board order: time, then strand, then kind."""
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


def _waits_for_local(rep: dict, open_ids: Container[str]) -> bool:
    """Waiting for a local step ("local <id>") whose request is still open; "localhost db" is not one,
    and a refused or already answered request is measured like any other wait."""
    waiting = str(rep.get("waiting_for", ""))
    return waiting.lower().startswith("local ") and waiting[6:].strip() in open_ids


def _obsolete(notice: dict, finished: dict[tuple[str, str], str],
              answered: frozenset[tuple[str, str]] = frozenset()) -> bool:
    """A stall or missing-session notice of a strand that reported done or blocked after it,
    or a local step notice whose request has a result."""
    title = str(notice.get("title", ""))
    if title.startswith(LOCAL_TITLE[0]) and title.endswith(LOCAL_TITLE[1]):
        rid = title[len(LOCAL_TITLE[0]):-len(LOCAL_TITLE[1])]
        return (str(notice.get("project", "")), rid) in answered
    strand = notice.get("strand")
    if not isinstance(strand, str) or notice.get("title") not in (strand + STALL_TITLE, strand + GONE_TITLE):
        return False
    done_at = finished.get((str(notice.get("project", "")), strand))
    return done_at is not None and done_at >= str(notice.get("time", ""))


def cutoff_iso(now: float) -> str:
    return _iso(now - NOTICE_DAYS * 86400)


def shown_notices(all_events: list[dict], cutoff: str) -> list[dict]:
    """Notices of the event list as the board shows them: not older than cutoff, not obsolete,
    not dismissed. Events carry their project; the list may span several projects."""
    answered = frozenset((str(e.get("project", "")), str(e.get("request_id", "")))
                         for e in all_events if e.get("kind") == "local_result")
    finished = {(str(e.get("project", "")), e["strand"]): str(e.get("time", "")) for e in all_events
                if e.get("kind") == "report" and e.get("state") in FINISHED and isinstance(e.get("strand"), str)}
    dismissed = {(str(e.get("project", "")), str(e.get("notice_time", "")), str(e.get("notice_title", "")))
                 for e in all_events if e.get("kind") == "dismiss"}
    return [e for e in all_events if e.get("kind") == "notice" and str(e.get("time", "")) >= cutoff
            and (str(e.get("project", "")), str(e.get("time", "")), str(e.get("title", ""))) not in dismissed
            and not _obsolete(e, finished, answered)][-MAX_NOTICES:]


def strand_sessions(projects: list[Project], sessions: list[tuple[str, str]]) -> dict[str, tuple[str, str | None]]:
    """tmux session -> (project, strand name or None), by session name and pane path only.

    The known-strand rule (report or start event) is the caller's business.
    """
    out: dict[str, tuple[str, str | None]] = {}
    for name, path in sessions:
        project = project_for_path(projects, Path(path))
        if project is None:
            continue
        out[name] = (project, name.removeprefix(project + "-") if name.startswith(project + "-") else None)
    return out


def running_strand_sessions(projects: list[Project], name: str, state_dir: Path,
                           sessions: list[tuple[str, str]] | None = None) -> list[str]:
    """tmux sessions '<name>-<strand>' of project `name` that still count: no supervisor, no done/blocked strand.

    `sessions` is the tmux listing if the caller already has it.
    """
    try:
        reports = _last_reports(events.read(state_dir, name)[0])
    except OSError:
        reports = {}  # events unreadable: count every session (safe side)
    found = []
    listing = effects.tmux_sessions() if sessions is None else sessions
    for session, (project, strand) in strand_sessions(projects, listing).items():
        if project != name or strand is None or strand == SUPERVISOR_STRAND:
            continue
        if reports.get(strand, {}).get("state") in FINISHED:
            continue
        found.append(session)
    return found


def collect(cfg: ServerConfig, projects: list[Project], now: float,
            transcripts_root: Path | None = None) -> State:
    state_dir = Path(cfg.state_dir)
    when = datetime.fromtimestamp(now, timezone.utc)
    limit_s = cfg.stall_minutes * 60

    def write(project: str, event: dict) -> None:
        events.append(state_dir, project, event, when)

    report_files = _report_events(state_dir, projects, when)

    def load_events(project: str) -> list[dict]:
        return sort_events(events.read(state_dir, project)[0])

    per_project = {p.name: load_events(p.name) for p in projects}
    last = {p: _last_reports(evs) for p, evs in per_project.items()}
    # launched strands count as known before their first report
    started = {p: {e["strand"] for e in evs if e.get("kind") == "start" and isinstance(e.get("strand"), str)}
               for p, evs in per_project.items()}

    # tmux sessions -> (project, strand); strand None means unknown
    sessions = {name: (project, strand if strand in last[project] or strand in started[project] else None)
                for name, (project, strand) in strand_sessions(projects, effects.tmux_sessions()).items()}

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
        rep = last[project].get(strand) or {"state": "running"}  # started, no report yet: measured as running
        entry["gone"] = False
        if rep.get("state") not in ("running", "waiting") or (
                rep.get("state") == "waiting"
                and (any(w in str(rep.get("waiting_for", "")).lower() for w in HUMAN_WAIT)
                     or _waits_for_local(rep, events.open_local(per_project[project])))):
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
                            "title": f"{strand}{STALL_TITLE}",
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
                                "title": f"{strand}{GONE_TITLE}",
                                "text": f"{name}: tmux session not found and no report. Please check."})
                entry["gone"] = True
                wrote = True
    if wrote:
        _save_json(marker_path, marker)

    # a local step request that stays open too long gets one warning notice
    local_path = state_dir / "markers" / "local.json"
    stored_noticed = _load_json(local_path).get("noticed")
    noticed = {x for x in stored_noticed if isinstance(x, str)} if isinstance(stored_noticed, list) else set()
    kept: set[str] = set()
    for p in projects:
        for rid, req in events.open_local(load_events(p.name)).items():
            key = f"{p.name}/{rid}"
            if key in noticed:
                kept.add(key)
            elif str(req.get("time", "9")) <= _iso(now - cfg.local_notice_hours * 3600):
                write(p.name, {"kind": "notice", "strand": req.get("strand", SYSTEM_STRAND), "level": "warning",
                               "title": f"{LOCAL_TITLE[0]}{rid}{LOCAL_TITLE[1]}",
                               "text": f"{rid}: no local result after {cfg.local_notice_hours} h. "
                                       "Is the local machine running the watcher?"})
                kept.add(key)
    if kept != noticed:
        _save_json(local_path, {"noticed": sorted(kept)})

    # findings on planning/TICKETS.md and planning/RELEASES.md, one notice per ticket and finding
    found: dict[str, list[checks.Finding]] = {}
    for p in projects:
        tickets, releases = load_tickets(p), load_releases(p)
        found[p.name] = (
            (checks.ticket_findings(tickets, releases, when, cfg.ticket_critical_hours) if tickets is not None else [])
            + (checks.release_findings(releases) if releases is not None else []))
    checks.emit_once(state_dir, found, when)

    # build the view from the events as they are now
    all_events: list[dict] = []
    result = State()
    cutoff = cutoff_iso(now)
    open_q: list[dict] = []
    tasks: dict[tuple[str, str], dict] = {}
    local: list[dict] = []
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
        last_result: dict[str, str] = {}
        for e in evs:
            if e.get("kind") == "local_result":
                last_result[str(e.get("strand", ""))] = f"{e.get('state')}: {e.get('text', '')}"
        for rid, req in events.open_local(evs).items():
            local.append({"project": p.name, "id": rid, "strand": req.get("strand", ""),
                          "step": req.get("step", ""), "branch": req.get("branch", ""),
                          "commit": req.get("commit", ""), "since": req.get("time", ""),
                          "last_result": last_result.get(str(req.get("strand", "")), "")})
        for strand, reps in by_strand.items():
            view = _strand_view(p.name, strand, reps)
            m = marker.get(f"{p.name}-{strand}", {})
            view.stalled = bool(m.get("reported")) and not m.get("gone") and view.state in ("running", "waiting")
            result.strands[f"{p.name}/{strand}"] = view
    all_events = sort_events(all_events)
    result.questions = sort_events(open_q)
    result.tasks = sort_events(list(tasks.values()))
    result.local = sorted(local, key=lambda r: str(r["since"]))
    result.notices = shown_notices(all_events, cutoff)
    result.recent = all_events[-MAX_RECENT:]
    result.runs = _runs(state_dir)
    if cfg.usage_report:
        try:
            root = transcripts_root if transcripts_root is not None else usage_mod.DEFAULT_ROOT
            result.usage = usage_mod.summarize(root, when.date(), usage_mod.load_prices(PRICES_FILE), projects)
        except Exception:  # the report is optional; a changed transcript format must not stop the run
            result.usage = None
    return result
