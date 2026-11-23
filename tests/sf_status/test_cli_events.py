import io
import json
import sys

import pytest

from sf_status import cli, effects, events, projects


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SF_SOURCE", raising=False)
    sdir = tmp_path / ".claude" / "software-factory" / "server"
    (sdir / "events").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text("gitleaks\n")
    hook.chmod(0o755)
    projects.add(sdir, projects.Project(name="p", title="P", folder=str(repo)))
    return sdir


def _q(nr="1", strand="a"):
    return ["question", "--project", "p", "--strand", strand, "--nr", nr,
            "--background", "bg", "--recommendation", "rec", "What now?"]


def test_question_prints_id(env, capsys):
    assert cli.main(_q()) == 0
    assert capsys.readouterr().out.strip() == "a-1"
    got, _ = events.read(env, "p")
    assert got[1]["id"] == "a-1" and got[1]["question"] == "What now?"


def test_answer_unknown_question_exit_1(env):
    assert cli.main(["answer", "--project", "p", "--id", "a-9", "yes"]) == 1


def test_answer_twice_exit_1(env):
    cli.main(_q())
    assert cli.main(["answer", "--project", "p", "--id", "a-1", "yes"]) == 0
    assert cli.main(["answer", "--project", "p", "--id", "a-1", "again"]) == 1
    got, _ = events.read(env, "p")
    assert [e["kind"] for e in got] == ["project_added", "question", "answer"]


def test_report_state_validated(env):
    assert cli.main(["report", "--project", "p", "--strand", "a", "--state", "sleeping", "x"]) == 2
    assert cli.main(["report", "--project", "p", "--strand", "a", "--state", "running",
                     "--progress", "50", "x"]) == 0


def test_text_with_newlines_stored_verbatim(env):
    text = "line one\nline \"two\"\n\ttab \u00e4"
    assert cli.main(["notice", "--project", "p", "--strand", "a", "--level", "info",
                     "--title", "t", text]) == 0
    got, _ = events.read(env, "p")
    assert got[1]["text"] == text


def test_unregistered_project_exit_1(env):
    (env / "projects.json").unlink()
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
    assert [e["kind"] for e in got] == ["project_added", "task", "task_done"]


def test_strand_required(env):
    assert cli.main(["report", "--project", "p", "--state", "running", "x"]) == 2


def test_cli_without_home_exits_1(env, monkeypatch, capsys):
    def boom():
        raise RuntimeError("no home")
    monkeypatch.setattr(cli.Path, "home", staticmethod(boom))
    for argv in (["wake", "fast-forward"],
                 ["report", "--project", "p", "--strand", "a", "--state", "working", "hi"]):
        assert cli.main(argv) == 1
        assert capsys.readouterr().err.startswith("sf-status:")


def test_emit_rejects_server_strand(env, capsys):
    argv = ["report", "--project", "p", "--strand", "server", "--state", "working", "hi"]
    assert cli.main(argv) == 2
    assert "'server' is reserved" in capsys.readouterr().err


COMMIT = "abc1234"
HEAD = COMMIT + "0" * 33


def _lreq(strand="a", commit=COMMIT, step="build", branch="feature/x"):
    return ["local", "request", "--project", "p", "--strand", strand, "--step", step,
            "--branch", branch, "--commit", commit]


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(effects, "git_remote_head", lambda folder, branch: HEAD)


def _kinds(env):
    got, _ = events.read(env, "p")
    return [e["kind"] for e in got]


def test_local_request_prints_id_and_writes_event(env, remote, capsys):
    assert cli.main(_lreq()) == 0
    assert capsys.readouterr().out.strip() == "a-l1"
    got, _ = events.read(env, "p")
    ev = [e for e in got if e["kind"] == "local_request"][0]
    assert (ev["step"], ev["branch"], ev["commit"]) == ("build", "feature/x", COMMIT)


@pytest.mark.parametrize("head", ["f" * 40, None])
def test_local_request_refuses_commit_not_on_remote(env, monkeypatch, capsys, head):
    monkeypatch.setattr(effects, "git_remote_head", lambda folder, branch: head)
    assert cli.main(_lreq()) == 1
    assert "feature/x" in capsys.readouterr().err
    assert "local_request" not in _kinds(env)


def test_local_request_second_open_refused(env, remote):
    assert cli.main(_lreq()) == 0
    assert cli.main(_lreq()) == 1
    assert _kinds(env).count("local_request") == 1


def test_local_request_after_failed_gets_l2(env, remote, capsys):
    cli.main(_lreq())
    assert cli.main(["local", "result", "--project", "p", "--id", "a-l1",
                     "--state", "failed", "boom"]) == 0
    capsys.readouterr()
    assert cli.main(_lreq()) == 0
    assert capsys.readouterr().out.strip() == "a-l2"


def test_local_request_rejects_reserved_strand(env, remote):
    assert cli.main(_lreq(strand="server")) == 2


def test_local_request_bad_commit_exit_2(env, remote, capsys):
    assert cli.main(_lreq(commit="x;y")) == 2
    assert "sf-status:" in capsys.readouterr().err


def test_local_pending_lists_open_oldest_first(env, remote, capsys):
    assert cli.main(["local", "pending", "--project", "p"]) == 0
    assert capsys.readouterr().out == ""
    cli.main(_lreq(strand="a"))
    cli.main(_lreq(strand="b", step="test"))
    cli.main(_lreq(strand="c"))
    cli.main(["local", "result", "--project", "p", "--id", "c-l1", "--state", "ok", "x"])
    capsys.readouterr()
    assert cli.main(["local", "pending", "--project", "p"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["id"] for r in rows] == ["a-l1", "b-l1"]
    assert rows[1]["strand"] == "b" and rows[1]["step"] == "test"
    assert {"branch", "commit", "time"} <= set(rows[0])


def test_local_pending_unregistered_exit_1(env):
    assert cli.main(["local", "pending", "--project", "nope"]) == 1


def test_local_result_unknown_id_exit_1(env):
    assert cli.main(["local", "result", "--project", "p", "--id", "a-l9",
                     "--state", "ok", "x"]) == 1


def test_local_result_twice_exit_1(env, remote):
    cli.main(_lreq())
    argv = ["local", "result", "--project", "p", "--id", "a-l1", "--state", "ok", "x"]
    assert cli.main(argv) == 0
    assert cli.main(argv) == 1
    assert _kinds(env).count("local_result") == 1


def test_local_result_ok_writes_strand_of_request(env, remote):
    cli.main(_lreq())
    assert cli.main(["local", "result", "--project", "p", "--id", "a-l1",
                     "--state", "ok", "all green"]) == 0
    got, _ = events.read(env, "p")
    ev = [e for e in got if e["kind"] == "local_result"][0]
    assert (ev["strand"], ev["request_id"], ev["state"], ev["text"]) == ("a", "a-l1", "ok", "all green")


def test_local_result_text_from_stdin(env, remote, monkeypatch):
    cli.main(_lreq())
    monkeypatch.setattr(sys, "stdin", io.StringIO("Build 42 ok\n"))
    assert cli.main(["local", "result", "--project", "p", "--id", "a-l1",
                     "--state", "ok", "-"]) == 0
    got, _ = events.read(env, "p")
    assert [e for e in got if e["kind"] == "local_result"][0]["text"] == "Build 42 ok"


def test_local_result_bad_state_exit_2(env):
    assert cli.main(["local", "result", "--project", "p", "--id", "a-l1",
                     "--state", "maybe", "x"]) == 2
