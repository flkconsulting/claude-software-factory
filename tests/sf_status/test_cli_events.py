import pytest

from sf_status import cli, events


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SF_SOURCE", raising=False)
    sdir = tmp_path / ".claude" / "software-factory" / "server"
    (sdir / "events").mkdir(parents=True)
    return sdir


def _q(nr="1", strand="a"):
    return ["question", "--project", "p", "--strand", strand, "--nr", nr,
            "--background", "bg", "--recommendation", "rec", "What now?"]


def test_question_prints_id(env, capsys):
    assert cli.main(_q()) == 0
    assert capsys.readouterr().out.strip() == "a-1"
    got, _ = events.read(env, "p")
    assert got[0]["id"] == "a-1" and got[0]["question"] == "What now?"


def test_answer_unknown_question_exit_1(env):
    assert cli.main(["answer", "--project", "p", "--id", "a-9", "yes"]) == 1


def test_answer_twice_exit_1(env):
    cli.main(_q())
    assert cli.main(["answer", "--project", "p", "--id", "a-1", "yes"]) == 0
    assert cli.main(["answer", "--project", "p", "--id", "a-1", "again"]) == 1
    got, _ = events.read(env, "p")
    assert [e["kind"] for e in got] == ["question", "answer"]


def test_report_state_validated(env):
    assert cli.main(["report", "--project", "p", "--strand", "a", "--state", "sleeping", "x"]) == 2
    assert cli.main(["report", "--project", "p", "--strand", "a", "--state", "running",
                     "--progress", "50", "x"]) == 0


def test_text_with_newlines_stored_verbatim(env):
    text = "line one\nline \"two\"\n\ttab \u00e4"
    assert cli.main(["notice", "--project", "p", "--strand", "a", "--level", "info",
                     "--title", "t", text]) == 0
    got, _ = events.read(env, "p")
    assert got[0]["text"] == text


def test_missing_events_dir_exit_1(env):
    (env / "events").rmdir()
    assert cli.main(["start", "--project", "p", "--strand", "a", "--topic", "t", "x"]) == 1


def test_supervisor_strand_reserved(env, monkeypatch):
    args = ["report", "--project", "p", "--strand", "supervisor", "--state", "running", "x"]
    assert cli.main(args) == 2
    monkeypatch.setenv("SF_SOURCE", "supervisor")
    assert cli.main(args) == 0


def test_task_and_done(env):
    assert cli.main(["task", "--project", "p", "--strand", "a", "--id", "t1", "--why", "w", "Title"]) == 0
    assert cli.main(["task", "--project", "p", "--strand", "a", "--done", "t1"]) == 0
    got, _ = events.read(env, "p")
    assert [e["kind"] for e in got] == ["task", "task_done"]


def test_strand_required(env):
    assert cli.main(["report", "--project", "p", "--state", "running", "x"]) == 2
