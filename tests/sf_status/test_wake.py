import json
from datetime import datetime, timedelta, timezone

from pathlib import Path

import pytest

from sf_status import events, wake
from sf_status.config import ServerConfig
from sf_status.projects import Project

T0 = datetime(2026, 11, 22, 8, 0, 0, tzinfo=timezone.utc)
PLAN = ("| short | strand | approval | starts when | branch | migrations | may change |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n")


@pytest.fixture
def proj(tmp_path):
    folder = tmp_path / "work" / "alpha"
    (folder / "planning").mkdir(parents=True)
    return Project(name="alpha", title="Alpha", folder=str(folder), supervisor=True)


def plan(proj, *rows):
    Path(proj.folder, proj.wave_plan).write_text(PLAN + "\n".join(rows) + "\n", encoding="utf-8")


def report(state, project, strand, st, text="x", at=T0):
    events.append(state, project, {"kind": "report", "strand": strand, "state": st, "text": text}, at)


def run(cfg, projs, state, now, commit=True):
    t = wake.collect_triggers(cfg, projs, state, now)
    if commit:
        wake.commit_triggers(state, t, now)
    return list(t)


def test_done_and_blocked_triggers_dedup_6h(cfg, state, proj):
    report(state, "alpha", "a", "done")
    report(state, "alpha", "b", "blocked")
    assert run(cfg, [proj], state, T0) == ["done:a", "blocked:b", "safety"]
    report(state, "alpha", "a", "done")
    later = T0 + timedelta(hours=1)
    assert "done:a" not in run(cfg, [proj], state, later)
    report(state, "alpha", "a", "done")
    assert "done:a" in run(cfg, [proj], state, T0 + timedelta(hours=7))


def test_answer_trigger(cfg, state, proj):
    events.append(state, "alpha", {"kind": "answer", "strand": "human", "question_id": "a-1", "text": "ok"}, T0)
    assert "answer:a-1" in run(cfg, [proj], state, T0)


def test_new_approved_row_once(cfg, state, proj):
    plan(proj, "| w1 | api | no | now | b | - | - |")
    run(cfg, [proj], state, T0)
    plan(proj, "| w1 | api | yes | now | b | - | - |")
    assert "approved:w1" in run(cfg, [proj], state, T0 + timedelta(minutes=5))
    assert "approved:w1" not in run(cfg, [proj], state, T0 + timedelta(minutes=10))
    plan(proj, "| w1 | api | yes | later | b | - | - |")  # changed row = new hash = new trigger
    assert "approved:w1" in run(cfg, [proj], state, T0 + timedelta(minutes=15))


def test_safety_every_3h(cfg, state, proj):
    assert "safety" in run(cfg, [proj], state, T0)
    assert "safety" not in run(cfg, [proj], state, T0 + timedelta(hours=2, minutes=59))
    assert "safety" in run(cfg, [proj], state, T0 + timedelta(hours=3))


def test_trigger_ids_match_pattern(cfg, state, proj):
    import re
    report(state, "alpha", "a", "done", text="x;rm -rf /")
    got = [t for t in run(cfg, [proj], state, T0) if t != "safety"]
    assert got == ["done:a"]
    assert all(re.fullmatch(r"[a-z]+(:[a-z0-9-]+)*", t) for t in got)


def test_supervisor_strand_ignored(cfg, state, proj):
    report(state, "alpha", "supervisor", "done")
    assert "done:supervisor" not in run(cfg, [proj], state, T0)


def test_projects_without_supervisor_ignored(cfg, state, proj):
    proj.supervisor = False
    report(state, "alpha", "a", "done")
    assert run(cfg, [proj], state, T0) == []


def test_marker_not_advanced_when_commit_fails(cfg, state, proj):
    report(state, "alpha", "a", "done")
    (state / "supervisor" / "triggers.json").mkdir(parents=True)  # a directory: the write must fail
    t = wake.collect_triggers(cfg, [proj], state, T0)
    with pytest.raises(OSError):
        wake.commit_triggers(state, t, T0)
    assert events.load_marker(state, "wake") == {}
    (state / "supervisor" / "triggers.json").rmdir()
    assert "done:a" in run(cfg, [proj], state, T0)


def test_commit_writes_open_list_and_keeps_existing(cfg, state, proj):
    report(state, "alpha", "a", "done")
    run(cfg, [proj], state, T0)
    data = json.loads((state / "supervisor" / "triggers.json").read_text())
    assert {"id": "done:a", "since": "2026-11-22T08:00:00Z", "tries": 0} in data["open"]
    assert data["parked"] == [] and data["last_run"] is None


def test_fast_forward_raises_nothing(cfg, state, proj):
    report(state, "alpha", "a", "done")
    plan(proj, "| w1 | api | yes | now | b | - | - |")
    wake.fast_forward(cfg, [proj], state, T0)
    assert run(cfg, [proj], state, T0 + timedelta(minutes=1)) == []


def test_approval_before_first_run_triggers(cfg, state, proj):
    plan(proj, "| w1 | api | yes | now | b | - | - |")
    assert "approved:w1" in run(cfg, [proj], state, T0)


def test_invalid_short_not_stored_and_noticed_once(cfg, state, proj):
    plan(proj, "| W 1;x | api | yes | now | b | - | - |")
    got = run(cfg, [proj], state, T0)
    assert not [t for t in got if t.startswith("approved")]
    stored = json.loads((state / "markers" / "wake.json").read_text())
    assert list(stored["rows"].values()) == [False]
    run(cfg, [proj], state, T0 + timedelta(minutes=5))
    evs = [e for e in events.read(state, "alpha")[0] if e["kind"] == "notice"]
    assert len(evs) == 1 and evs[0]["level"] == "warning" and evs[0]["strand"] == "server"
    assert evs[0]["title"] == "wave plan row skipped" and ";" not in evs[0]["text"]


def test_failed_notice_keeps_marker_unadvanced(cfg, state, proj, monkeypatch):
    plan(proj, "| W 1 | api | yes | now | b | - | - |")
    t = wake.collect_triggers(cfg, [proj], state, T0)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(events, "append", boom)
    with pytest.raises(OSError):
        wake.commit_triggers(state, t, T0)
    assert not (state / "markers" / "wake.json").exists()


def test_answer_to_supervisor_question_triggers(cfg, state, proj):
    events.append(state, "alpha", {"kind": "question", "strand": "supervisor", "id": "supervisor-1",
                                   "question": "q", "background": "b", "recommendation": "r"}, T0)
    events.append(state, "alpha", {"kind": "answer", "strand": "supervisor", "question_id": "supervisor-1",
                                   "text": "yes"}, T0)
    report(state, "alpha", "supervisor", "done")
    got = run(cfg, [proj], state, T0)
    assert "answer:supervisor-1" in got and "done:supervisor" not in got


def test_reserved_names_match_state_keys():
    from sf_status import projects
    assert set(projects.RESERVED_NAMES) == {k for k in wake.STATE_KEYS if projects.NAME_RE.match(k)}


def test_commit_waits_for_triggers_lock(cfg, state, proj):
    import fcntl
    import threading
    report(state, "alpha", "a", "done")
    t = wake.collect_triggers(cfg, [proj], state, T0)
    lock_path = state / "supervisor" / "triggers.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        worker = threading.Thread(target=wake.commit_triggers, args=(state, t, T0))
        worker.start()
        worker.join(0.3)
        assert worker.is_alive()  # blocked while the supervisor holds the triggers lock
        assert not (state / "supervisor" / "triggers.json").exists()
    worker.join(5)
    assert not worker.is_alive()
    data = json.loads((state / "supervisor" / "triggers.json").read_text())
    assert "done:a" in [i["id"] for i in data["open"]]
