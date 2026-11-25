#!/usr/bin/env python3
"""UserPromptSubmit hook: tells the session about due reminders of its project.

Reads the reminders file (see sf_config.reminders_file), lines of the form
`- [ ] YYYY-MM-DD | <project> | <text>`. Open entries whose day is today or
earlier are reported for the project of the session's cwd (the folder that
holds `.git`, a folder or a worktree file) and for project `*`. Reported once
per session and day. Outside a repository only `*` entries are due.

"Today" is date.today(); the env var SF_REMINDERS_TODAY (ISO date) overrides
it and is read only for tests. A hook never ends with a traceback: any
failure is silent, exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LINE = re.compile(
    r"^\s*[-*]\s+\[( |x|X)\]\s+(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$"
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
        entries.append(Entry(day, m.group(3), m.group(4)))
    return entries


def due(entries: list[Entry], today: date, project: str | None) -> list[Entry]:
    wanted = {"*"} if project is None else {"*", project.casefold()}
    hits = [e for e in entries if e.day <= today and (e.project == "*" or e.project.casefold() in wanted)]
    return sorted(hits, key=lambda e: e.day)


def project_of(cwd: str | None) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    path = Path(cwd)
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return folder.name or None
    return None


def _today() -> date:
    try:
        return date.fromisoformat(os.environ.get("SF_REMINDERS_TODAY", ""))
    except ValueError:
        return date.today()


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
    if marker.exists():
        return 0

    lines = [f"Due reminders ({cfg.reminders_file}):"]
    lines += [f"- {e.day.isoformat()} {e.text}" for e in hits]
    lines.append(CLOSING)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass
    return 0


def main(argv: list[str]) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        if argv:
            return 0  # --notify arrives in a later task
        return _hook()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
