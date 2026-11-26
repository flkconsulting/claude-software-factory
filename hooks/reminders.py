#!/usr/bin/env python3
"""UserPromptSubmit hook: tells the session about due reminders of its project.

Reads the reminders file (see sf_config.reminders_file), lines of the form
`- [ ] YYYY-MM-DD[ HH:MM] | <project> | <text>` (optional time of day, 00:00 to
23:59; an invalid time makes the line invalid; no time means all day). Open
entries whose day is today or earlier are reported (the time is only shown,
never used for dueness) for the project of the session's cwd (the folder that
holds `.git`, a folder or a worktree file) and for project `*`. Reported once
per session and day. Outside a repository only `*` entries are due.

`--notify` shows a macOS notification, `--html` writes the week view
(~/.claude/software-factory/termine.html) and opens it on macOS.

"Today" is date.today(); the env var SF_REMINDERS_TODAY (ISO date) overrides
it and is read only for tests; SF_REMINDERS_NOW (ISO date and time, local,
no timezone) overrides the clock the same way, and SF_REMINDERS_TODAY wins
over its date. A hook never ends with a traceback: any
failure is silent, exit 0.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

LINE = re.compile(
    r"^\s*[-*]\s+\[( |x|X)\]\s+"
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})(?:\s+([0-9]{2}:[0-9]{2}))?"
    r"\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$"
)

CLOSING = (
    "Tell the user about these at the start of your answer. Mark an entry done "
    "([x]) only when the user says so or the task is shown to be done."
)


@dataclass(frozen=True)
class Entry:
    day: date
    project: str
    text: str
    time: time | None = None


def sort_key(e: Entry) -> tuple:
    t = e.time
    return (e.day, t is not None, t or time(0, 0))


def when(e: Entry) -> str:
    return f"{e.day.isoformat()} {e.time.strftime('%H:%M')}" if e.time else e.day.isoformat()


def parse(text: str) -> list[Entry]:
    entries = []
    for line in text.splitlines():
        m = LINE.match(line)
        if not m or m.group(1) != " ":
            continue
        try:
            day = date.fromisoformat(m.group(2))
        except ValueError:
            continue
        at = None
        if m.group(3):
            hh, mm = int(m.group(3)[:2]), int(m.group(3)[3:])
            if hh > 23 or mm > 59:
                continue
            at = time(hh, mm)
        entries.append(Entry(day, m.group(4), m.group(5), at))
    return entries


def due(entries: list[Entry], today: date, project: str | None) -> list[Entry]:
    wanted = {"*"} if project is None else {"*", project.casefold()}
    hits = [e for e in entries if e.day <= today and (e.project == "*" or e.project.casefold() in wanted)]
    return sorted(hits, key=sort_key)


def project_of(cwd: str | None) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    path = Path(cwd)
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return folder.name or None
    return None


def _now() -> datetime:
    try:
        return datetime.fromisoformat(os.environ.get("SF_REMINDERS_NOW", ""))
    except ValueError:
        return datetime.now()


def _today() -> date:
    try:
        return date.fromisoformat(os.environ.get("SF_REMINDERS_TODAY", ""))
    except ValueError:
        return _now().date()


def _platform() -> str:
    return os.environ.get("SF_REMINDERS_PLATFORM") or sys.platform


def _hook() -> int:
    from sf_config import load_config

    data = json.load(sys.stdin)
    if not isinstance(data, dict):
        return 0
    cfg = load_config()
    try:
        text = cfg.reminders_file.read_text(encoding="utf-8-sig")
    except OSError:
        return 0
    today = _today()
    hits = due(parse(text), today, project_of(data.get("cwd")))
    if not hits:
        return 0

    session = data.get("session_id")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session) if isinstance(session, str) and session else "unknown"
    marker = cfg.state_dir / f"reminders-{safe_id}-{today.isoformat()}"
    try:
        marked = marker.exists()
    except OSError:
        marked = False
    if marked:
        return 0

    lines = [f"Due reminders ({cfg.reminders_file}):"]
    lines += [f"- {when(e)} {e.text}" for e in hits]
    lines.append(CLOSING)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        return 0
    _prune_markers(cfg.state_dir, today)
    return 0


MARKER = re.compile(r"^reminders-.+-(\d{4}-\d{2}-\d{2})$")


def _prune_markers(state_dir: Path, today: date) -> None:
    try:
        for f in state_dir.iterdir():
            try:
                m = MARKER.match(f.name)
                if m and date.fromisoformat(m.group(1)) < today:
                    f.unlink()
            except (OSError, ValueError):
                pass
    except OSError:
        pass


def notify_text(entries: list[Entry]) -> tuple[str, str]:
    body = "; ".join(f"{e.project}: {e.time.strftime('%H:%M') + ' ' if e.time else ''}{e.text}" for e in entries[:3])
    if len(entries) > 3:
        body += f" (+{len(entries) - 3} more)"
    return f"Reminders: {len(entries)} due", body


def applescript(title: str, body: str) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    return f'display notification "{esc(body)}" with title "{esc(title)}"'


def _notify() -> int:
    from sf_config import load_config

    try:
        text = load_config().reminders_file.read_text(encoding="utf-8-sig")
    except OSError:
        return 0
    today = _today()
    hits = sorted((e for e in parse(text) if e.day <= today), key=sort_key)
    if not hits:
        return 0
    if _platform() != "darwin":
        print("notification not available on this system")
        return 0
    try:
        subprocess.run(["osascript", "-e", applescript(*notify_text(hits))],
                       timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

CSS = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 1rem;"
    "color:#1f2933;background:#f7f8fa}"
    "h1{font-size:1.5rem}h2{font-size:1.1rem;margin:1.5rem 0 .4rem;border-bottom:1px solid #cbd2d9}"
    "h2.late{color:#b42318}ul{list-style:none;margin:0;padding:0}"
    "li{display:flex;gap:.8rem;padding:.2rem 0}.t{width:5.5rem;color:#52606d}"
    ".p{width:7rem;color:#52606d}.none{color:#7b8794}"
)


def _rows(entries: list[Entry], with_day: bool) -> str:
    items = []
    for e in entries:
        label = (e.day.strftime("%d.%m.") + " ") if with_day else ""
        label += e.time.strftime("%H:%M") if e.time else "ganzt&auml;gig"
        items.append(f'<li><span class="t">{label}</span>'
                     f'<span class="p">{html.escape(e.project)}</span>'
                     f'<span>{html.escape(e.text)}</span></li>')
    return "<ul>" + "".join(items) + "</ul>"


def _day_heading(day: date, today: date) -> str:
    full = f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"
    if day == today:
        return f"Heute, {full}"
    if day == today + timedelta(days=1):
        return f"Morgen, {full}"
    return full


def render_html(entries: list[Entry], today: date) -> str:
    open_entries = sorted(entries, key=sort_key)
    parts = []
    late = [e for e in open_entries if e.day < today]
    if late:
        parts.append('<h2 class="late">&Uuml;berf&auml;llig</h2>' + _rows(late, True))
    for offset in range(7):
        day = today + timedelta(days=offset)
        todays = [e for e in open_entries if e.day == day]
        body = _rows(todays, False) if todays else '<p class="none">keine Termine</p>'
        parts.append(f"<h2>{_day_heading(day, today)}</h2>{body}")
    return ('<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8">'
            '<title>Termine</title>'
            f"<style>{CSS}</style></head><body><h1>Termine</h1>"
            + "".join(parts) + "</body></html>\n")


def html_path(state_dir: Path) -> Path:
    return state_dir.parent / "termine.html"


def _html() -> int:
    from sf_config import load_config

    cfg = load_config()
    try:
        entries = parse(cfg.reminders_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        entries = []
    page = html_path(cfg.state_dir)
    try:
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(render_html(entries, _today()), encoding="utf-8")
    except OSError as exc:
        print(f"cannot write {page}: {exc}", file=sys.stderr)
        return 1
    print(page)
    if _platform() == "darwin":
        try:
            subprocess.run(["open", str(page)], timeout=10, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            pass
    return 0


def main(argv: list[str]) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        if argv == ["--html"]:
            try:
                return _html()
            except Exception as exc:
                print(f"cannot create the week view: {exc}", file=sys.stderr)
                return 1
        if argv:
            return _notify() if argv == ["--notify"] else 0
        return _hook()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
