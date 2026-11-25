import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "reminders.py"
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
