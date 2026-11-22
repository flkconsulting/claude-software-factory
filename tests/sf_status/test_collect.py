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
