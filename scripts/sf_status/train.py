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

from . import collect, effects, events, planning, wave_plan
from .config import ServerConfig
from .planning import Releases, Version
from .projects import TIME_RE, TRAIN_DAYS, Project

CATCH_UP = timedelta(hours=24)


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


def next_date(project: Project, now: datetime) -> date | None:
    """Next cut-off day whose moment is not before `now`, not in train_skip, at most 60 days ahead; None when unusable."""
    if not project.train:
        return None
    try:
        weekday, _, zone = _settings(project)
        today = now.astimezone(zone).date()
        for i in range(61):
            day = today + timedelta(days=i)
            if day.weekday() == weekday and day.isoformat() not in project.train_skip and cutoff(project, day) >= now:
                return day
    except (ValueError, KeyError, OSError, OverflowError):
        pass
    return None


TICKET_NR_RE = re.compile(r"T-\d+")


def board_entry(project: Project, tickets, releases, rows, strands, marker: dict, now: datetime) -> dict:
    """Numbers for the board headline of one project; missing files count as zero.

    tickets: planning.TicketTable | None, releases: planning.Releases | None, rows: parsed wave plan rows,
    strands: {"<project>/<short>": StrandView}, marker: the train marker (see load_marker)."""
    day = next_date(project, now)
    entry = marker.get(project.name) if isinstance(marker.get(project.name), dict) else {}
    dates = entry.get("dates") if isinstance(entry.get("dates"), dict) else {}
    questions = entry.get("questions") if isinstance(entry.get("questions"), dict) else {}
    rows_t = tickets.rows if tickets is not None else []
    state = lambda t: t.state.lower()  # noqa: E731
    versions = {v.version for v in candidates(releases)} if releases is not None else set()
    working = {t.nr for t in rows_t if state(t) == "in-progress"}
    for r in rows:
        view = strands.get(f"{project.name}/{r.short}")
        if r.approved and view is not None and view.state in ("running", "waiting"):
            working.update(TICKET_NR_RE.findall(r.tickets))
    open_q = sorted(qid for qid, q in questions.items() if isinstance(q, dict) and q.get("state") in ("open", "unclear"))
    return {
        "project": project.name,
        "date": day.isoformat() if day else None,
        "skipped": bool(day) and dates.get(day.isoformat()) == "skipped",
        "in": sum(1 for t in rows_t if state(t) in ("planned", "in-train") and t.version in versions),
        "working": len(working),
        "waiting": sum(1 for t in rows_t if state(t) in ("new", "assessed")) + len(open_q),
        "on_test": [f"{v.version} ({v.line})" for v in (releases.versions if releases is not None else [])
                    if v.state.lower() == "testing" and VERSION_RE.fullmatch(v.version)],
        "question": open_q[-1] if open_q else None,
    }


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


# ---- the human's answer to the train question: decided without a model ----------------------------

VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
QID_RE = re.compile(r"^train-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")
NEGATIONS = ("nein", "no", "not", "nicht", "kein", "keine", "warte", "warten", "wait", "abwarten", "later",
             "spaeter", "sp\u00e4ter", "hold", "never", "nie", "ohne", "stop", "stopp", "skip",
             "don't", "dont", "doesn't", "won't")
SKIP_WORDS = ("ausgesetzt", "aussetzen", "skip")
TRAIN_PREFIX = "zug-"
DEFAULT_COLUMNS = ["short", "strand", "approval", "starts when", "branch", "migrations", "may change"]


def candidates(rel: Releases) -> list[Version]:
    """Per line the first version in state planned (file order); only valid x.y.z numbers count."""
    seen: set[str] = set()
    out = []
    for v in rel.versions:
        if not VERSION_RE.fullmatch(v.version) or v.line in seen or v.state.lower() != "planned":
            continue
        seen.add(v.line)
        out.append(v)
    return out


def short_for(version: str) -> str:
    return TRAIN_PREFIX + version.replace(".", "-")


def names_version(text: str, version: str) -> bool:
    """The version stands in `text` as a word of its own (2.1.0 is not in 2.1.00, 12.1.0 or 2.1.0.1)."""
    return re.search(rf"(?<![\w.]){re.escape(version)}(?!\w|\.\d)", text.lower()) is not None


def decide(text: str, candidates: list[str]) -> tuple[str, str | None]:
    """("approve", version) | ("skip", None) | ("unclear", None); no model, fixed words only."""
    lower = text.lower()
    if "?" in lower or "|" in lower:
        return "unclear", None
    words = set(re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*", lower.replace("\u2019", "'")))
    named = [v for v in candidates if names_version(lower, v)]
    if len(named) == 1:
        return ("unclear", None) if words & set(NEGATIONS) else ("approve", named[0])
    if not named and words & set(SKIP_WORDS):
        return "skip", None
    return "unclear", None


def wave_row(header: list[str], values: dict[str, str]) -> str:
    """One table row in the column order of the header; columns without a value stay empty."""
    cells = [values.get(name.strip().lower(), "") for name in header]
    return "| " + " | ".join(cells) + " |"


def open_train_strands(project: Project, state_dir: Path, live: list[tuple[str, str]] | None = None) -> list[str]:
    """Shorts of train strands that are not finished: approved rows with short zug-... whose strand has no
    done/blocked report. With `live` (the tmux listing) only strands with a running session count, plus any
    running session zug-... of the project. Shared by process_answers and launch."""
    try:
        text = (Path(project.folder) / project.wave_plan).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    try:
        reports = collect._last_reports(events.read(Path(state_dir), project.name)[0])
    except (OSError, ValueError):
        reports = {}  # unreadable: count every strand (safe side)
    found = {r.short for r in wave_plan.parse_wave_plan(text)
             if r.approved and r.short.startswith(TRAIN_PREFIX)
             and reports.get(r.short, {}).get("state") not in collect.FINISHED}
    if live is not None:
        names = {name for name, _ in live}
        found = {s for s in found if f"{project.name}-{s}" in names}
        prefix = f"{project.name}-"
        for session in collect.running_strand_sessions([project], project.name, Path(state_dir), live):
            strand = session[len(prefix):]
            if strand.startswith(TRAIN_PREFIX):
                found.add(strand)
    return sorted(found)


def _insert_row(text: str, row: str) -> str:
    """Text with `row` added after the last line of the table that holds the header (or at the end)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    last = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|"):
            last = i
        elif last is not None and line.strip():
            break  # first non-table text after the table
    if last is None:
        head = "| " + " | ".join(DEFAULT_COLUMNS) + " |"
        sep = "| " + " | ".join("---" for _ in DEFAULT_COLUMNS) + " |"
        return text + ("" if not text or text.endswith("\n") else nl) + nl.join([head, sep, row]) + nl
    if not lines[last].endswith("\n"):
        lines[last] += nl
    lines.insert(last + 1, row + nl)
    return "".join(lines)


def _header(text: str) -> list[str]:
    for line in text.splitlines():
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and cells and cells[0] == "short":
            return cells
    return list(DEFAULT_COLUMNS)


def process_answers(cfg: ServerConfig, projects: list[Project], state_dir: Path, now: datetime) -> None:
    """Evaluate answers to train questions and write the approval row; see the plan, Task 3.

    Changes the marker only when something happened. A row is written and committed locally (never pushed);
    if anything fails the file is put back and the next run tries again.
    """
    state_dir = Path(state_dir)
    marker = load_marker(state_dir)
    changed = False
    for project in projects:
        if not project.train:
            continue
        try:
            evs = events.read(state_dir, project.name)[0]
        except (OSError, ValueError):
            continue
        entry = marker.get(project.name, {})
        questions = entry.get("questions") if isinstance(entry.get("questions"), dict) else {}
        for e in evs:
            qid = e.get("question_id")
            if e.get("kind") != "answer" or not isinstance(qid, str) or not (m := QID_RE.match(qid)):
                continue
            q = questions.get(qid)
            if isinstance(q, dict) and q.get("state") != "open":
                continue  # handled before
            entry = marker.setdefault(project.name, {})
            entry.setdefault("dates", {})
            questions = entry.setdefault("questions", {})
            changed = True
            if not isinstance(q, dict):
                questions[qid] = {"state": "unclear"}
                continue
            _handle(project, state_dir, now, entry, q, qid, m[1], str(e.get("text", "")))
    if changed:
        save_marker(state_dir, marker)


def _notice(state_dir: Path, project: Project, now: datetime, level: str, title: str, text: str) -> None:
    try:
        events.append(state_dir, project.name, {"kind": "notice", "strand": "server", "level": level,
                                                "title": title, "text": text}, now)
    except (OSError, ValueError):
        pass


def _wait(state_dir: Path, project: Project, now: datetime, q: dict, date_: str, reason: str, detail: str) -> None:
    """Keep the question open; one warning per question and reason."""
    if q.get("noticed") != reason:
        q["noticed"] = reason
        _notice(state_dir, project, now, "warning", f"Train {date_} waits: {reason}", detail)


def _handle(project: Project, state_dir: Path, now: datetime, entry: dict, q: dict, qid: str, date_: str,
            raw: str) -> None:
    words = " ".join(raw.split())  # line breaks become one space
    cands = [c for c in q.get("candidates", []) if isinstance(c, str)]
    verdict, version = decide(words, cands)
    if verdict == "unclear":
        q["state"] = "unclear"
        return
    if verdict == "skip":
        q["state"] = "skipped"
        entry["dates"][date_] = "skipped"
        _notice(state_dir, project, now, "info", f"Train {date_} skipped on your answer",
                f"Your answer to {qid} suspends the train of {date_}.")
        return
    short = short_for(version)
    path = Path(project.folder) / project.wave_plan
    try:
        original = path.read_bytes()
    except OSError:
        _wait(state_dir, project, now, q, date_, "wave plan cannot be read", f"Cannot read {project.wave_plan}.")
        return
    text = original.decode("utf-8", errors="replace")
    done = any(r.short == short and r.approved for r in wave_plan.parse_wave_plan(text))
    if not done:  # an existing row means a repeat after a crash: nothing to write
        busy = open_train_strands(project, state_dir)
        if busy:
            _wait(state_dir, project, now, q, date_, f"train strand {busy[0]} is open",
                  f"Train {date_} waits for train strand {busy[0]}: it ends with a done or blocked report.")
            return
        clean = effects.git_path_clean(Path(project.folder), project.wave_plan)
        if clean is not True:
            reason = "wave plan has local changes" if clean is False else "wave plan state cannot be checked"
            _wait(state_dir, project, now, q, date_, reason,
                  f"Train {date_}: {project.wave_plan} {'has local changes; commit or undo them' if clean is False else 'is not in a readable git repository'}"
                  "; the row is written on a later run.")
            return
        rel = planning.load_releases(project)
        line = next((v.line for v in (rel.versions if rel else []) if v.version == version), None)
        if line is None:
            q["state"] = "unclear"  # the version vanished from RELEASES.md: ask again
            return
        row = wave_row(_header(text), {
            "short": short, "strand": f"Release train {version}", "approval": f'yes - "{words}"',
            "starts when": "immediately", "branch": f"release/{version}", "base": line,
            "migrations": "none", "may change": f"release/{version}"})
        try:
            path.write_bytes(_insert_row(text, row).encode("utf-8"))
        except OSError:
            _wait(state_dir, project, now, q, date_, "wave plan cannot be written", f"Cannot write {project.wave_plan}.")
            return
        if not effects.git_commit_path(Path(project.folder), project.wave_plan, f"chore(planning): approve train {version}"):
            try:
                path.write_bytes(original)
            except OSError:
                pass
            _wait(state_dir, project, now, q, date_, "commit failed",
                  f"Train {date_}: the approval row could not be committed; the file was put back and the next run tries again.")
            return
    q["state"] = "approved"
    q["version"] = version
    entry["dates"][date_] = "approved"
