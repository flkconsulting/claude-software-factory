import json

import pytest

from sf_status import collect, effects, events
from sf_status.projects import Project

NOW = 1_800_000_000.0
LIMIT = 45 * 60


@pytest.fixture
def fake(monkeypatch):
    class Fake:
        sessions: list = []
        panes: dict = {}
        started: list = []

    f = Fake()
    f.sessions, f.panes, f.started = [], {}, []
    monkeypatch.setattr(effects, "tmux_sessions", lambda: list(f.sessions))
    monkeypatch.setattr(effects, "capture_pane", lambda s: f.panes.get(s))
    monkeypatch.setattr(effects, "tmux_new_session", lambda *a, **k: f.started.append(a) or True)
    return f


@pytest.fixture
def projects(tmp_path):
    return [Project(name="alpha", title="Alpha", folder=str(tmp_path / "work" / "alpha"))]


def report(state, strand, project="alpha", **kw):
    return events.append(state, project, {"kind": "report", "strand": strand, "state": kw.pop("st", "running"),
                                          "text": "x", **kw})


def of_kind(state, kind, project="alpha"):
    return [e for e in events.read(state, project)[0] if e["kind"] == kind]


def write_report(state, short, first, project="alpha"):
    p = state / "reports" / project / f"{short}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(first + "\nbody\n", encoding="utf-8")


def test_report_file_first_line_becomes_event(cfg, state, projects, fake):
    write_report(state, "a", "A DONE")
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 60)
    reps = of_kind(state, "report")
    assert len(reps) == 1
    assert reps[0]["state"] == "done" and reps[0]["source"] == "report-file" and reps[0]["strand"] == "a"
    write_report(state, "a", "A BLOCKED")
    collect.collect(cfg, projects, NOW + 120)
    assert [e["state"] for e in of_kind(state, "report")] == ["done", "blocked"]
    write_report(state, "b", "no state here")
    collect.collect(cfg, projects, NOW + 180)
    assert len(of_kind(state, "report")) == 2



def test_in_progress_line_rearms_done(cfg, state, projects, fake):
    write_report(state, "a", "A DONE")
    collect.collect(cfg, projects, NOW)
    write_report(state, "a", "A IN PROGRESS")
    collect.collect(cfg, projects, NOW + 60)
    assert [e["state"] for e in of_kind(state, "report")] == ["done"]
    write_report(state, "a", "A DONE")
    collect.collect(cfg, projects, NOW + 120)
    assert [e["state"] for e in of_kind(state, "report")] == ["done", "done"]

def running(cfg, state, projects, fake, pane="busy\n"):
    report(state, "a")
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": pane}


def test_stall_event_and_notice_once(cfg, state, projects, fake):
    running(cfg, state, projects, fake)
    collect.collect(cfg, projects, NOW)
    s = collect.collect(cfg, projects, NOW + LIMIT)
    assert len(of_kind(state, "stall")) == 1
    st = of_kind(state, "stall")[0]
    assert st["session"] == "alpha-a" and st["strand"] == "a" and st["minutes"] >= 45
    assert [n["level"] for n in of_kind(state, "notice")] == ["warning"]
    assert s.strands["alpha/a"].stalled is True
    s = collect.collect(cfg, projects, NOW + 2 * LIMIT)
    assert len(of_kind(state, "stall")) == 1 and len(of_kind(state, "notice")) == 1
    fake.panes["alpha-a"] = "changed\n"
    s = collect.collect(cfg, projects, NOW + 2 * LIMIT + 60)
    assert s.strands["alpha/a"].stalled is False
    assert fake.started == []


@pytest.mark.parametrize("who", ["human", "heavy-run"])
def test_waiting_for_human_not_stalled(cfg, state, projects, fake, who):
    report(state, "a", st="waiting", waiting_for=who)
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "same\n"}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    assert of_kind(state, "stall") == []


def test_done_strand_not_checked(cfg, state, projects, fake):
    report(state, "a", st="done")
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "same\n"}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    assert of_kind(state, "stall") == [] and of_kind(state, "notice") == []


def test_unknown_tmux_session_hint_once(cfg, state, projects, fake):
    fake.sessions = [("alpha-zzz", projects[0].folder + "-zzz"), ("elsewhere", "/nowhere")]
    fake.panes = {}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 60)
    notes = of_kind(state, "notice")
    assert len(notes) == 1 and notes[0]["strand"] == "server" and notes[0]["level"] == "info"


def test_gone_session_hint_once(cfg, state, projects, fake):
    report(state, "a")
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 60)
    notes = of_kind(state, "notice")
    assert len(notes) == 1 and notes[0]["strand"] == "a"
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "x\n"}
    collect.collect(cfg, projects, NOW + 120)
    fake.sessions = []
    collect.collect(cfg, projects, NOW + 180)
    assert len(of_kind(state, "notice")) == 2


def test_gone_session_with_report_file_is_quiet(cfg, state, projects, fake):
    report(state, "a")
    write_report(state, "a", "A DONE")
    collect.collect(cfg, projects, NOW)
    assert of_kind(state, "notice") == []


def test_no_restart(cfg, state, projects, fake):
    report(state, "a")
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    assert fake.started == []


def test_tmux_missing_is_empty(cfg, state, projects, monkeypatch):
    import subprocess

    def boom(*a, **k):
        raise FileNotFoundError("tmux")

    monkeypatch.setattr(subprocess, "run", boom)
    assert effects.tmux_sessions() == []
    s = collect.collect(cfg, projects, NOW)
    assert s.strands == {}


def test_state_views(cfg, state, projects, fake):
    report(state, "a", branch="feature/x")
    events.append(state, "alpha", {"kind": "question", "strand": "a", "id": "a-1", "question": "q",
                                   "background": "b", "recommendation": "r"})
    events.append(state, "alpha", {"kind": "task", "strand": "a", "id": "t1", "title": "T", "why": "w"})
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "x\n"}
    runs = state / "supervisor" / "runs"
    runs.mkdir(parents=True)
    (runs / "1.json").write_text(json.dumps({"start": "t", "result": "ok"}))
    (runs / "2.json").write_text("not json")
    s = collect.collect(cfg, projects, NOW)
    v = s.strands["alpha/a"]
    assert v.state == "running" and v.branch == "feature/x" and v.text == "x"
    assert [q["id"] for q in s.questions] == ["a-1"]
    assert [t["id"] for t in s.tasks] == ["t1"]
    assert len(s.runs) == 1 and s.usage is None and s.recent


def test_supervisor_strand_excluded_from_gone_and_stall(cfg, state, projects, fake):
    report(state, "supervisor")
    collect.collect(cfg, projects, NOW)
    assert of_kind(state, "notice") == []
    fake.sessions = [("alpha-supervisor", projects[0].folder + "-supervisor")]
    fake.panes = {"alpha-supervisor": "same\n"}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    assert of_kind(state, "stall") == [] and of_kind(state, "notice") == []


def test_stall_marker_reset_after_leaving_checked_states(cfg, state, projects, fake):
    running(cfg, state, projects, fake, pane="same\n")
    collect.collect(cfg, projects, NOW)
    report(state, "a", st="waiting", waiting_for="human")
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    report(state, "a", st="running")
    s = collect.collect(cfg, projects, NOW + 3 * LIMIT + 60)
    assert of_kind(state, "stall") == []
    assert s.strands["alpha/a"].stalled is False


def test_stall_marker_reset_when_session_disappears(cfg, state, projects, fake):
    running(cfg, state, projects, fake, pane="same\n")
    collect.collect(cfg, projects, NOW)
    fake.sessions = []
    collect.collect(cfg, projects, NOW + 3 * LIMIT)
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    collect.collect(cfg, projects, NOW + 3 * LIMIT + 60)
    assert of_kind(state, "stall") == []


def test_launched_strand_without_report_is_known(cfg, state, projects, fake):
    events.append(state, "alpha", {"kind": "start", "strand": "zzz", "topic": "t", "text": "started"})
    fake.sessions = [("alpha-zzz", projects[0].folder + "-zzz")]
    fake.panes = {"alpha-zzz": "x\n"}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 60)
    assert of_kind(state, "notice") == []
    assert of_kind(state, "stall") == []


def test_launched_strand_without_report_is_not_reported_gone(cfg, state, projects, fake):
    events.append(state, "alpha", {"kind": "start", "strand": "zzz", "topic": "t", "text": "started"})
    collect.collect(cfg, projects, NOW)
    assert of_kind(state, "notice") == []


def _at(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc)


def _visible_titles(s):
    return [n["title"] for n in s.notices]


def test_stall_notice_dropped_after_strand_done(cfg, state, projects, fake):
    running(cfg, state, projects, fake)
    events.append(state, "alpha", {"kind": "notice", "strand": "a", "level": "info",
                                   "title": "a: own note", "text": "keep me"}, _at(NOW))
    collect.collect(cfg, projects, NOW)
    s = collect.collect(cfg, projects, NOW + LIMIT)
    assert "a: possibly stalled" in _visible_titles(s)
    write_report(state, "a", "A DONE")
    s = collect.collect(cfg, projects, NOW + LIMIT + 60)
    assert "a: possibly stalled" not in _visible_titles(s)
    assert "a: own note" in _visible_titles(s)
    assert len([n for n in of_kind(state, "notice") if n["title"] == "a: possibly stalled"]) == 1  # log untouched


def test_stall_notice_kept_while_strand_runs(cfg, state, projects, fake):
    running(cfg, state, projects, fake)
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + LIMIT)
    events.append(state, "alpha", {"kind": "report", "strand": "a", "state": "running", "text": "x"},
                  _at(NOW + LIMIT + 30))
    s = collect.collect(cfg, projects, NOW + LIMIT + 60)
    assert "a: possibly stalled" in _visible_titles(s)


def test_gone_notice_dropped_after_strand_blocked(cfg, state, projects, fake):
    events.append(state, "alpha", {"kind": "report", "strand": "a", "state": "running", "text": "x"}, _at(NOW))
    s = collect.collect(cfg, projects, NOW)
    assert "a: tmux session missing" in _visible_titles(s)
    events.append(state, "alpha", {"kind": "report", "strand": "a", "state": "blocked", "text": "x"}, _at(NOW + 30))
    s = collect.collect(cfg, projects, NOW + 60)
    assert "a: tmux session missing" not in _visible_titles(s)
    events.append(state, "alpha", {"kind": "report", "strand": "a", "state": "running", "text": "rework"},
                  _at(NOW + 90))
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "busy\n"}
    s = collect.collect(cfg, projects, NOW + 120)
    assert "a: tmux session missing" not in _visible_titles(s)


def test_running_strand_sessions_counts_unreadable_events_as_running(state, projects, fake, monkeypatch):
    fake.sessions = [("alpha-a", str(state / "work" / "alpha-a")), ("alpha-supervisor", str(state / "work" / "alpha"))]

    def boom(*a, **k):
        raise OSError("denied")
    monkeypatch.setattr(events, "read", boom)
    assert collect.running_strand_sessions(projects, "alpha", state) == ["alpha-a"]


def test_collect_survives_usage_error(cfg, state, projects, fake, monkeypatch):
    from dataclasses import replace
    from sf_status import usage as usage_mod

    def boom(*a, **k):
        raise RuntimeError("changed format")

    monkeypatch.setattr(usage_mod, "summarize", boom)
    report(state, "a")
    s = collect.collect(replace(cfg, usage_report=True), projects, NOW)
    assert s.usage is None and "alpha/a" in s.strands


def _waiting_local(cfg, state, projects, fake, what):
    report(state, "a", st="waiting", waiting_for=what)
    fake.sessions = [("alpha-a", projects[0].folder + "-a")]
    fake.panes = {"alpha-a": "same\n"}
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 3 * LIMIT)


def test_waiting_for_local_not_stalled(cfg, state, projects, fake):
    _local_request(state)
    _waiting_local(cfg, state, projects, fake, "local a-l1")
    assert of_kind(state, "stall") == []


def test_waiting_for_local_without_request_is_stalled(cfg, state, projects, fake):
    _waiting_local(cfg, state, projects, fake, "local a-l1")
    assert len(of_kind(state, "stall")) == 1


def test_waiting_for_local_after_result_is_stalled(cfg, state, projects, fake):
    _local_request(state)
    _local_result(state)
    _waiting_local(cfg, state, projects, fake, "local a-l1")
    assert len(of_kind(state, "stall")) == 1


def test_waiting_for_localhost_still_stalled(cfg, state, projects, fake):
    _waiting_local(cfg, state, projects, fake, "localhost db")
    assert len(of_kind(state, "stall")) == 1


def _local_request(state, rid="a-l1", strand="a", at=NOW):
    events.append(state, "alpha", {"kind": "local_request", "strand": strand, "id": rid, "step": "build",
                                   "branch": "feature/x", "commit": "abc1234"}, _at(at))


def _local_result(state, rid="a-l1", st="ok", text="fine", strand="a", at=NOW):
    events.append(state, "alpha", {"kind": "local_result", "strand": strand, "request_id": rid,
                                   "state": st, "text": text}, _at(at))


def _local_notices(state):
    return [n for n in of_kind(state, "notice") if n["title"].startswith("local step ")]


def test_local_notice_once_after_hours(cfg, state, projects, fake):
    _local_request(state)
    collect.collect(cfg, projects, NOW + 7 * 3600)
    assert _local_notices(state) == []
    collect.collect(cfg, projects, NOW + 9 * 3600)
    notes = _local_notices(state)
    assert len(notes) == 1 and notes[0]["level"] == "warning" and "a-l1" in notes[0]["title"]
    assert notes[0]["strand"] == "a"
    collect.collect(cfg, projects, NOW + 20 * 3600)
    assert len(_local_notices(state)) == 1


def test_local_notice_respects_config(cfg, state, projects, fake):
    import dataclasses
    _local_request(state)
    collect.collect(dataclasses.replace(cfg, local_notice_hours=1), projects, NOW + 2 * 3600)
    assert len(_local_notices(state)) == 1


def test_local_notice_hidden_after_result(cfg, state, projects, fake):
    _local_request(state)
    s = collect.collect(cfg, projects, NOW + 9 * 3600)
    assert "local step a-l1 waiting" in _visible_titles(s)
    _local_result(state, at=NOW + 9 * 3600 + 30)
    s = collect.collect(cfg, projects, NOW + 9 * 3600 + 60)
    assert "local step a-l1 waiting" not in _visible_titles(s)
    assert len(_local_notices(state)) == 1  # log untouched


def test_local_notice_not_for_answered_request(cfg, state, projects, fake):
    _local_request(state)
    _local_result(state, at=NOW + 60)
    s = collect.collect(cfg, projects, NOW + 20 * 3600)
    assert _local_notices(state) == [] and s.local == []


def test_state_local_lists_open_with_last_result(cfg, state, projects, fake):
    _local_request(state)
    _local_result(state, st="failed", text="boom", at=NOW + 60)
    _local_request(state, rid="a-l2", at=NOW + 120)
    s = collect.collect(cfg, projects, NOW + 180)
    assert len(s.local) == 1
    e = s.local[0]
    assert e["id"] == "a-l2" and e["last_result"] == "failed: boom" and e["project"] == "alpha"
    assert e["strand"] == "a" and e["step"] == "build" and e["branch"] == "feature/x"
    assert e["commit"] == "abc1234" and e["since"]


def test_dismissed_notice_hidden_log_untouched(cfg, state, projects, fake):
    events.append(state, "alpha", {"kind": "notice", "strand": "a", "level": "warning",
                                   "title": "keep", "text": "x"}, _at(NOW))
    events.append(state, "alpha", {"kind": "notice", "strand": "a", "level": "warning",
                                   "title": "gone", "text": "x"}, _at(NOW))
    t = of_kind(state, "notice")[0]["time"]
    events.append(state, "alpha", {"kind": "dismiss", "strand": "a", "notice_time": t,
                                   "notice_title": "gone"}, _at(NOW + 1))
    s = collect.collect(cfg, projects, NOW + 2)
    assert _visible_titles(s) == ["keep"]
    assert len(of_kind(state, "notice")) == 2


BROKEN = ("| nr | since | kind | rank | effort | state | version | source | summary |\n"
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
          "| T-1 | 2026-01-01 | bug | normal | S | new | | customer A | one |\n"
          "| T-1 | 2026-01-01 | bug | normal | S | new | | customer A | two |\n")
FIXED = BROKEN.rsplit("| T-1", 1)[0]


def _tickets_file(projects, text):
    from pathlib import Path
    d = Path(projects[0].folder) / "planning"
    d.mkdir(parents=True, exist_ok=True)
    (d / "TICKETS.md").write_text(text, encoding="utf-8")


def _ticket_notices(state):
    return [n for n in of_kind(state, "notice") if n["title"].startswith("ticket ")]


def test_ticket_notice_once(cfg, state, projects, fake):
    _tickets_file(projects, BROKEN)
    collect.collect(cfg, projects, NOW)
    collect.collect(cfg, projects, NOW + 60)
    notes = _ticket_notices(state)
    assert [n["title"] for n in notes] == ["ticket T-1: number-duplicate"]
    assert notes[0]["level"] == "info" and notes[0]["strand"] == "server"
    marker = state / "markers" / "tickets.json"
    assert json.loads(marker.read_text())["noticed"] == ["alpha/T-1/number-duplicate"]
    _tickets_file(projects, FIXED)
    collect.collect(cfg, projects, NOW + 120)
    assert json.loads(marker.read_text())["noticed"] == []
    _tickets_file(projects, BROKEN)
    collect.collect(cfg, projects, NOW + 180)
    assert len(_ticket_notices(state)) == 2


def test_no_ticket_files_no_marker_no_event(cfg, state, projects, fake):
    collect.collect(cfg, projects, NOW)
    assert not (state / "markers" / "tickets.json").exists()
    assert of_kind(state, "notice") == []
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "templates" / "planning"
    d = Path(projects[0].folder) / "planning"
    d.mkdir(parents=True)
    for name in ("TICKETS.md", "RELEASES.md"):
        (d / name).write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8")
    collect.collect(cfg, projects, NOW + 60)
    assert not (state / "markers" / "tickets.json").exists()
    assert of_kind(state, "notice") == []


def test_ticket_checks_without_train(cfg, state, projects, fake):
    _tickets_file(projects, BROKEN)
    collect.collect(cfg, projects, NOW)
    assert len(_ticket_notices(state)) == 1


RELEASES = ("## Versions\n\n| version | line | state |\n| --- | --- | --- |\n"
            "| 2.0.0 | release/2.0 | testing |\n")


def _releases_file(projects, text=RELEASES):
    from pathlib import Path
    d = Path(projects[0].folder) / "planning"
    d.mkdir(parents=True, exist_ok=True)
    (d / "RELEASES.md").write_text(text, encoding="utf-8")


def _backport_notices(state):
    return [n["title"] for n in of_kind(state, "notice") if n["title"].startswith("backport ")]


def test_backport_notice_once_per_commit(cfg, state, projects, fake, monkeypatch):
    _releases_file(projects)
    answer = {"v": ["a" * 40, "b" * 40]}
    monkeypatch.setattr(effects, "git_cherry", lambda *a: answer["v"])
    for i in range(3):
        collect.collect(cfg, projects, NOW + i * 60)
    assert sorted(_backport_notices(state)) == ["backport 2.0.0: " + "a" * 12 + " missing",
                                                "backport 2.0.0: " + "b" * 12 + " missing"]
    answer["v"] = ["b" * 40]
    collect.collect(cfg, projects, NOW + 300)
    assert len(_backport_notices(state)) == 2
    answer["v"] = None  # branch gone or git failed: old keys are kept
    collect.collect(cfg, projects, NOW + 360)
    answer["v"] = ["b" * 40]  # branch is back, b is still missing
    collect.collect(cfg, projects, NOW + 420)
    assert len(_backport_notices(state)) == 2


def test_backport_keys_survive_releases_file_gone_for_one_run(cfg, state, projects, fake, monkeypatch):
    _releases_file(projects)
    monkeypatch.setattr(effects, "git_cherry", lambda *a: ["a" * 40])
    collect.collect(cfg, projects, NOW)
    assert len(_backport_notices(state)) == 1
    from pathlib import Path
    path = Path(projects[0].folder) / "planning" / "RELEASES.md"
    path.rename(path.with_name("RELEASES.md.off"))
    collect.collect(cfg, projects, NOW + 60)
    path.with_name("RELEASES.md.off").rename(path)
    collect.collect(cfg, projects, NOW + 120)
    assert len(_backport_notices(state)) == 1


def test_backport_without_releases_file_no_git_call(cfg, state, projects, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(effects, "git_cherry", lambda *a: calls.append(a) or [])
    collect.collect(cfg, projects, NOW)
    assert calls == []


def test_state_tickets_filled_only_with_file(cfg, state, projects, fake):
    assert collect.collect(cfg, projects, NOW).tickets == []
    _tickets_file(projects, "| nr | since | kind | rank | state | version | summary |\n"
                            "| --- | --- | --- | --- | --- | --- | --- |\n"
                            "| T-1 | 2026-01-01 | bug | critical | new | | boom |\n")
    got = collect.collect(cfg, projects, NOW).tickets
    assert [o["project"] for o in got] == ["alpha"]
    assert got[0]["bugs"][0]["nr"] == "T-1" and got[0]["next"] == []


def test_state_train_only_with_train_on(cfg, state, projects, fake):
    assert collect.collect(cfg, projects, NOW).train == []
    projects[0].train = True
    got = collect.collect(cfg, projects, NOW).train
    assert len(got) == 1 and got[0]["project"] == "alpha"
    assert (got[0]["in"], got[0]["working"], got[0]["waiting"], got[0]["on_test"]) == (0, 0, 0, [])
    assert not (state / "markers" / "train.json").exists()
