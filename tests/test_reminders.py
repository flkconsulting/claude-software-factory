import json
import os
import subprocess
import sys
from datetime import date, datetime, time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "reminders.py"
sys.path.insert(0, str(HOOK.parent))
import reminders  # noqa: E402

TAIL = ("Tell the user about these at the start of your answer. Mark an entry done "
        "([x]) only when the user says so or the task is shown to be done.")


def run(payload, home: Path, today="2026-12-05", raw=None):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    if today:
        env["SF_REMINDERS_TODAY"] = today
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data,
                          capture_output=True, text=True, env=env, timeout=30)


def state_dir(home: Path) -> Path:
    return home / ".claude" / "software-factory" / "state"


def write(home: Path, text: str, binary=False):
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    if binary:
        (d / "reminders.md").write_bytes(text)
    else:
        (d / "reminders.md").write_text(text, encoding="utf-8")


def repo(tmp_path: Path, name: str, as_file=False) -> Path:
    r = tmp_path / name
    r.mkdir()
    if as_file:
        (r / ".git").write_text("gitdir: /elsewhere\n")
    else:
        (r / ".git").mkdir()
    return r


def call(cwd, session="s1"):
    p = {"session_id": session}
    if cwd is not None:
        p["cwd"] = str(cwd)
    return p


def ctx(r):
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    return out["additionalContext"]


def test_no_file_silent(tmp_path):
    r = run(call(tmp_path), tmp_path)
    assert r.returncode == 0 and r.stdout == ""
    assert not state_dir(tmp_path).exists()


def test_nothing_due_silent(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-06 | Alpha | later\n")
    r = run(call(a), tmp_path)
    assert r.returncode == 0 and r.stdout == ""


def test_due_and_overdue_reported_sorted(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-05 | Alpha | second\n- [ ] 2026-12-01 | Alpha | first\n")
    r = run(call(a), tmp_path)
    c = ctx(r)
    path = tmp_path / ".claude" / "reminders.md"
    assert c.startswith(f"Due reminders ({path}):")
    assert c.index("- 2026-12-01 first") < c.index("- 2026-12-05 second")
    assert c.endswith(TAIL)


def test_done_entries_ignored(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [x] 2026-12-01 | Alpha | a\n- [X] 2026-12-01 | Alpha | b\n")
    r = run(call(a), tmp_path)
    assert r.returncode == 0 and r.stdout == ""


def test_other_project_not_reported_star_is(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-01 | Beta | beta thing\n- [ ] 2026-12-01 | * | star thing\n")
    c = ctx(run(call(a), tmp_path))
    assert "star thing" in c and "beta thing" not in c


def test_worktree_counts_with_own_folder_name(tmp_path):
    w = repo(tmp_path, "alpha-wt", as_file=True)
    sub = w / "sub"
    sub.mkdir()
    write(tmp_path, "- [ ] 2026-12-01 | alpha-wt | wt thing\n- [ ] 2026-12-01 | alpha | main thing\n")
    c = ctx(run(call(sub), tmp_path))
    assert "wt thing" in c and "main thing" not in c


def test_no_repo_only_star(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    write(tmp_path, "- [ ] 2026-12-01 | plain | p\n- [ ] 2026-12-01 | * | s\n")
    c = ctx(run(call(plain), tmp_path))
    assert "- 2026-12-01 s" in c and "] p" not in c and "- 2026-12-01 p" not in c
    c2 = ctx(run(call(None, "s2"), tmp_path))
    assert "- 2026-12-01 s" in c2 and "- 2026-12-01 p" not in c2


def test_once_per_session_and_day(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-01 | Alpha | x\n")
    assert ctx(run(call(a), tmp_path))
    assert run(call(a), tmp_path).stdout == ""
    assert ctx(run(call(a), tmp_path, today="2026-12-06"))
    assert ctx(run(call(a, "s2"), tmp_path))
    names = sorted(f.name for f in state_dir(tmp_path).iterdir())
    # the run on 12-06 pruned the 12-05 marker of s1 (older than today)
    assert names == ["reminders-s1-2026-12-06", "reminders-s2-2026-12-05"]


def test_bom_crlf_bad_date_and_garbage_lines(tmp_path):
    a = repo(tmp_path, "Alpha")
    raw = ("﻿- [ ] 2026-12-01 | Alpha | good\r\n"
           "- [ ] 2026-02-30 | Alpha | bad date\r\n"
           "hello\r\n"
           "* [ ] 2026-12-02 | Alpha | star bullet\r\n").encode("utf-8")
    write(tmp_path, raw, binary=True)
    r = run(call(a), tmp_path)
    c = ctx(r)
    assert r.returncode == 0
    assert "good" in c and "star bullet" in c and "bad date" not in c and "hello" not in c


def test_unwritable_state_still_reports(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-01 | Alpha | x\n")
    sd = state_dir(tmp_path)
    sd.parent.mkdir(parents=True)
    sd.write_text("blocker")
    r = run(call(a), tmp_path)
    assert r.returncode == 0 and "- 2026-12-01 x" in ctx(r)


def test_bad_stdin_silent(tmp_path):
    write(tmp_path, "- [ ] 2026-12-01 | * | x\n")
    r = run(None, tmp_path, raw="not json")
    assert r.returncode == 0 and r.stdout == ""


# --- Task 3: --notify and marker handling -----------------------------------


def test_notify_text_three_and_more():
    es = [reminders.Entry(date(2026, 12, 1), f"P{i}", f"t{i}") for i in range(5)]
    title, body = reminders.notify_text(es)
    assert title == "Reminders: 5 due"
    assert body == "P0: t0; P1: t1; P2: t2 (+2 more)"
    assert reminders.notify_text(es[:2]) == ("Reminders: 2 due", "P0: t0; P1: t1")


def test_applescript_escapes_quotes_and_backslash():
    s = reminders.applescript('T "x"', 'a\\b "c"')
    assert s == 'display notification "a\\\\b \\"c\\"" with title "T \\"x\\""'


def notify(home, tmp_path, platform="darwin", fake=True, today="2026-12-05"):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    out = tmp_path / "osa-args.txt"
    if fake:
        f = bindir / "osascript"
        f.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{out}"\n')
        f.chmod(0o755)
    env = {"HOME": str(home), "PATH": str(bindir) if not fake else f"{bindir}:/usr/bin:/bin",
           "SF_REMINDERS_TODAY": today, "SF_REMINDERS_PLATFORM": platform}
    r = subprocess.run([sys.executable, str(HOOK), "--notify"], capture_output=True,
                       text=True, env=env, timeout=30)
    return r, out


def test_notify_calls_osascript(tmp_path):
    write(tmp_path, "- [ ] 2026-12-02 | B | second\n- [ ] 2026-12-01 | A | first\n"
                    "- [ ] 2026-12-09 | A | future\n- [x] 2026-12-01 | A | done\n")
    r, out = notify(tmp_path, tmp_path)
    assert r.returncode == 0
    args = out.read_text().splitlines()
    assert args[0] == "-e"
    assert args[1] == ('display notification "A: first; B: second" '
                       'with title "Reminders: 2 due"')
    assert not state_dir(tmp_path).exists()


def test_notify_nothing_due_no_call(tmp_path):
    write(tmp_path, "- [ ] 2026-12-09 | A | future\n")
    r, out = notify(tmp_path, tmp_path)
    assert r.returncode == 0 and not out.exists()


def test_notify_not_darwin_message(tmp_path):
    write(tmp_path, "- [ ] 2026-12-01 | A | x\n")
    r, out = notify(tmp_path, tmp_path, platform="linux")
    assert r.returncode == 0 and r.stdout.strip() == "notification not available on this system"
    assert not out.exists()


def test_notify_osascript_missing_exit0(tmp_path):
    write(tmp_path, "- [ ] 2026-12-01 | A | x\n")
    r, out = notify(tmp_path, tmp_path, fake=False)
    assert r.returncode == 0 and not out.exists()


def test_other_argv_silent(tmp_path):
    write(tmp_path, "- [ ] 2026-12-01 | A | x\n")
    r = subprocess.run([sys.executable, str(HOOK), "--bogus"], capture_output=True,
                       text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, timeout=30)
    assert r.returncode == 0 and r.stdout == ""


def test_marker_check_error_still_prints(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-01 | Alpha | x\n")
    sd = state_dir(tmp_path)
    sd.mkdir(parents=True)
    sd.chmod(0)
    try:
        if os.access(sd, os.X_OK):
            pytest.skip("running as root: cannot provoke the error")
        r = run(call(a), tmp_path)
    finally:
        sd.chmod(0o755)
    assert r.returncode == 0 and "- 2026-12-01 x" in ctx(r)


def test_old_markers_removed_others_survive(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-01 | Alpha | x\n")
    sd = state_dir(tmp_path)
    sd.mkdir(parents=True)
    old = sd / "reminders-old-2026-12-04"
    keep = [sd / "reminders-s9-2026-12-05", sd / "reminders-s9-2026-12-06",
            sd / "context-load-abc.txt", sd / "reminders-launchd.log"]
    for f in [old, *keep]:
        f.write_text("")
    assert ctx(run(call(a), tmp_path))
    assert not old.exists()
    assert all(f.exists() for f in keep)


# --- Task 2 (Terminanzeige): optional time of day ----------------------------


def test_parse_time_optional():
    es = reminders.parse("- [ ] 2026-12-05 14:00 | * | Kunde X\n"
                         "- [ ] 2026-12-10 | * | Rechnung pruefen\n")
    assert len(es) == 2
    assert es[0].time == time(14, 0) and es[0].text == "Kunde X"
    assert es[1].time is None


@pytest.mark.parametrize("hhmm,valid", [
    ("00:00", True), ("23:59", True),
    ("24:00", False), ("25:99", False), ("9:00", False),
    ("14:60", False), ("14:00:00", False),
])
def test_parse_time_bounds(hhmm, valid):
    es = reminders.parse(f"- [ ] 2026-12-05 {hhmm} | * | t\n")
    assert (len(es) == 1) == valid


def test_old_lines_still_parse():
    raw = ("- [ ] 2026-12-01 | Alpha | good\r\n"
           "- [ ] 2026-02-30 | Alpha | bad date\r\n"
           "hello\r\n"
           "* [ ] 2026-12-02 | Alpha | star bullet\r\n")
    es = reminders.parse(raw)
    assert [e.text for e in es] == ["good", "star bullet"]
    assert all(e.time is None for e in es)
    tight = reminders.parse("- [ ] 2026-12-05|*|tight\n")
    assert len(tight) == 1 and tight[0].text == "tight"


def test_sort_all_day_first_then_time():
    es = [reminders.Entry(date(2026, 12, 5), "*", "a", time(14, 0)),
          reminders.Entry(date(2026, 12, 5), "*", "b"),
          reminders.Entry(date(2026, 12, 5), "*", "c", time(9, 0)),
          reminders.Entry(date(2026, 12, 4), "*", "d", time(18, 0))]
    out = sorted(es, key=reminders.sort_key)
    assert [e.text for e in out] == ["d", "b", "c", "a"]
    assert [reminders.when(e) for e in out] == [
        "2026-12-04 18:00", "2026-12-05", "2026-12-05 09:00", "2026-12-05 14:00"]


def test_hook_output_shows_time_also_overdue(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-05 | Alpha | all day\n"
                    "- [ ] 2026-12-01 09:30 | Alpha | old\n")
    c = ctx(run(call(a), tmp_path))
    assert "- 2026-12-01 09:30 old" in c and "- 2026-12-05 all day" in c
    assert c.index("- 2026-12-01 09:30 old") < c.index("- 2026-12-05 all day")


def test_time_does_not_change_dueness(tmp_path):
    a = repo(tmp_path, "Alpha")
    write(tmp_path, "- [ ] 2026-12-05 23:59 | * | late\n")
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
           "SF_REMINDERS_TODAY": "2026-12-05", "SF_REMINDERS_NOW": "2026-12-05T08:00"}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(call(a)),
                       capture_output=True, text=True, env=env, timeout=30)
    assert "- 2026-12-05 23:59 late" in ctx(r)


def test_notify_text_includes_time():
    e = reminders.Entry(date(2026, 12, 1), "A", "first", time(9, 30))
    assert reminders.notify_text([e])[1] == "A: 09:30 first"
    assert reminders.notify_text([reminders.Entry(date(2026, 12, 1), "A", "first")])[1] == "A: first"


def test_now_override(monkeypatch):
    monkeypatch.delenv("SF_REMINDERS_TODAY", raising=False)
    monkeypatch.setenv("SF_REMINDERS_NOW", "2026-12-05T14:30")
    assert reminders._now() == datetime(2026, 12, 5, 14, 30)
    assert reminders._today() == date(2026, 12, 5)
    monkeypatch.setenv("SF_REMINDERS_TODAY", "2026-12-06")
    assert reminders._today() == date(2026, 12, 6)
    monkeypatch.delenv("SF_REMINDERS_TODAY")
    monkeypatch.setenv("SF_REMINDERS_NOW", "garbage")
    assert isinstance(reminders._now(), datetime)
    before = date.today()
    result = reminders._today()
    assert result in (before, date.today())


# --- week view (--html) and /termine -----------------------------------------

SAMPLE = (
    "- [ ] 2026-12-01 | A | alt\n"
    "- [ ] 2026-12-05 14:00 | * | Kunde X\n"
    "- [ ] 2026-12-05 | * | ganztag\n"
    "- [ ] 2026-12-11 | * | sechs Tage\n"
    "- [ ] 2026-12-12 | * | zu spaet\n"
    "- [x] 2026-12-06 | * | erledigt\n"
)


def html_run(home, tmp_path, platform="darwin", fake=True):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    out = tmp_path / "open-args.txt"
    if fake:
        f = bindir / "open"
        f.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{out}"\n')
        f.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin",
           "SF_REMINDERS_NOW": "2026-12-05T10:00", "SF_REMINDERS_PLATFORM": platform}
    r = subprocess.run([sys.executable, str(HOOK), "--html"], capture_output=True,
                       text=True, env=env, timeout=30)
    return r, out, home / ".claude" / "software-factory" / "termine.html"


def test_html_written_and_opened_on_darwin(tmp_path):
    write(tmp_path, SAMPLE)
    r, out, page = html_run(tmp_path, tmp_path)
    assert r.returncode == 0 and page.is_file()
    assert out.read_text().splitlines() == [str(page)]
    assert r.stdout.strip().splitlines()[-1] == str(page)


def test_html_other_platform_only_path(tmp_path):
    write(tmp_path, SAMPLE)
    r, out, page = html_run(tmp_path, tmp_path, platform="linux")
    assert r.returncode == 0 and page.is_file() and not out.exists()
    assert r.stdout.strip().splitlines()[-1] == str(page)


def test_html_sections_and_hidden_entries(tmp_path):
    write(tmp_path, SAMPLE)
    r, _, page = html_run(tmp_path, tmp_path, platform="linux")
    page_text = page.read_text(encoding="utf-8")
    assert "&Uuml;berf&auml;llig" in page_text
    late_part = page_text[page_text.index("&Uuml;berf&auml;llig"):]
    assert late_part.index(">alt<") < late_part.index(">Kunde X<")
    assert late_part.index(">ganztag<") < late_part.index(">Kunde X<")
    assert "sechs Tage" in page_text
    assert "zu spaet" not in page_text and "erledigt" not in page_text
    for heading in ("Heute", "Morgen", "Sonntag, 06.12.2026"):
        assert heading in page_text


def test_html_invalid_utf8_file_gives_empty_page(tmp_path):
    write(tmp_path, b"\xff\xfe- [ ] 2026-12-05 | * | x\n", binary=True)
    r, _, page = html_run(tmp_path, tmp_path, platform="linux")
    assert r.returncode == 0 and page.is_file()
    assert "keine Termine" in page.read_text(encoding="utf-8")


def test_html_escapes_text(tmp_path):
    write(tmp_path, '- [ ] 2026-12-05 | A&B | <script>alert("x")</script>\n')
    r, _, page = html_run(tmp_path, tmp_path, platform="linux")
    html = page.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "A&amp;B" in html and "<script>" not in html


def test_html_is_self_contained(tmp_path):
    write(tmp_path, SAMPLE)
    r, _, page = html_run(tmp_path, tmp_path, platform="linux")
    html = page.read_text(encoding="utf-8")
    for bad in ("http://", "https://", "<script", "<link"):
        assert bad not in html


def test_html_without_file_shows_no_appointments(tmp_path):
    r, _, page = html_run(tmp_path, tmp_path, platform="linux")
    assert r.returncode == 0 and page.is_file()
    assert "keine Termine" in page.read_text(encoding="utf-8")


def test_html_unwritable_target_reports(tmp_path):
    write(tmp_path, SAMPLE)
    (tmp_path / ".claude" / "software-factory").write_text("not a folder")
    r, _, _ = html_run(tmp_path, tmp_path, platform="linux")
    assert r.returncode == 1 and r.stderr.strip() and "Traceback" not in r.stderr


def test_termine_command_file():
    f = HOOK.parent.parent / "commands" / "termine.md"
    text = f.read_text(encoding="utf-8")
    assert text.startswith("---") and "description:" in text
    assert 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reminders.py" --html' in text
