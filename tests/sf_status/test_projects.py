import json
import subprocess
from pathlib import Path

import pytest

from sf_status import cli, events, projects
from sf_status.projects import Project, ProjectError


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SF_SOURCE", raising=False)
    sdir = tmp_path / ".claude" / "software-factory" / "server"
    sdir.mkdir(parents=True)
    return sdir


def make_repo(path: Path, hook: bool = True) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if hook:
        h = path / ".git" / "hooks" / "pre-push"
        h.write_text("#!/bin/sh\ngitleaks protect --staged\n")
        h.chmod(0o755)
    return path


def proj(folder: Path, name="alpha", **kw) -> Project:
    return Project(name=name, title="Alpha", folder=str(folder), **kw)


def add_args(folder, name="alpha", *extra):
    return ["project", "add", name, "--title", "Alpha", "--folder", str(folder), *extra]


def test_add_requires_git_repo(env, tmp_path, capsys):
    (tmp_path / "plain").mkdir()
    assert cli.main(add_args(tmp_path / "plain")) == 1
    assert "git" in capsys.readouterr().err
    assert projects.load(env) == []


def test_add_requires_gitleaks_hook(env, tmp_path, capsys):
    repo = make_repo(tmp_path / "r", hook=False)
    assert cli.main(add_args(repo)) == 1
    assert "scripts/git-hooks/pre-push" in capsys.readouterr().err
    (repo / ".git" / "hooks" / "pre-push").write_text("#!/bin/sh\necho hi\n")
    (repo / ".git" / "hooks" / "pre-push").chmod(0o755)
    assert cli.main(add_args(repo)) == 1


def test_hook_via_hookspath_and_executable(tmp_path):
    repo = make_repo(tmp_path / "r", hook=False)
    hooks = repo / "myhooks"
    hooks.mkdir()
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", "myhooks"], check=True)
    assert not projects.has_gitleaks_pre_push(repo)
    (hooks / "pre-push").write_text("gitleaks\n")
    assert not projects.has_gitleaks_pre_push(repo)  # not executable
    (hooks / "pre-push").chmod(0o755)
    assert projects.has_gitleaks_pre_push(repo)


def test_add_rejects_duplicate_and_bad_name(env, tmp_path):
    repo = make_repo(tmp_path / "r")
    assert cli.main(add_args(repo)) == 0
    assert cli.main(add_args(repo, "beta")) == 1  # folder already registered
    repo2 = make_repo(tmp_path / "r2")
    assert cli.main(add_args(repo2)) == 1  # name taken
    assert cli.main(add_args(repo2, "Bad_Name")) == 1
    assert cli.main(add_args(repo2, "-x")) in (1, 2)
    assert [p.name for p in projects.load(env)] == ["alpha"]


def test_add_writes_event_and_fields(env, tmp_path, capsys):
    repo = make_repo(tmp_path / "r")
    assert cli.main(add_args(repo, "alpha", "--never-touch", "a,b", "--wave-plan", "x/y.md")) == 0
    p = projects.load(env)[0]
    assert p.never_touch == ["a", "b"] and p.wave_plan == "x/y.md" and p.main_branch == "main"
    assert p.supervisor is False and p.approval_quote is None
    got, _ = events.read(env, "alpha")
    assert got[0]["kind"] == "project_added"
    assert cli.main(["project", "list"]) == 0
    assert "alpha" in capsys.readouterr().out


def test_supervisor_yes_requires_quote(env, tmp_path):
    repo = make_repo(tmp_path / "r")
    assert cli.main(add_args(repo, "alpha", "--supervisor", "yes")) == 1
    assert projects.load(env) == []
    assert cli.main(add_args(repo, "alpha", "--supervisor", "yes", "--approval-quote", "ok go")) == 0
    p = projects.load(env)[0]
    assert p.supervisor is True and p.approval_quote == "ok go"


def test_remove_unknown_exit_1(env):
    assert cli.main(["project", "remove", "nope"]) == 1


def test_remove_registered(env, tmp_path):
    repo = make_repo(tmp_path / "r")
    cli.main(add_args(repo))
    assert cli.main(["project", "remove", "alpha"]) == 0
    assert projects.load(env) == []
    got, _ = events.read(env, "alpha")
    assert [e["kind"] for e in got] == ["project_added", "project_removed"]


def test_project_for_path(tmp_path):
    a = proj(tmp_path / "app")
    b = proj(tmp_path / "other", name="beta")
    ps = [a, b]
    assert projects.project_for_path(ps, tmp_path / "app") == "alpha"
    assert projects.project_for_path(ps, tmp_path / "app" / "sub" / "x") == "alpha"
    assert projects.project_for_path(ps, tmp_path / "app-a") == "alpha"
    assert projects.project_for_path(ps, tmp_path / "apple") is None
    assert projects.project_for_path(ps, tmp_path / "elsewhere") is None


def test_events_require_registered_project(env, tmp_path):
    (env / "events").mkdir()
    start = ["start", "--project", "p", "--strand", "a", "--topic", "t", "x"]
    assert cli.main(start) == 1
    assert cli.main(["answer", "--project", "p", "--id", "a-1", "x"]) == 1
    projects.add(env, proj(make_repo(tmp_path / "r"), name="p"))
    assert cli.main(start) == 0


def test_corrupt_projects_json_is_empty(env):
    (env / "projects.json").write_text("{not json")
    assert projects.load(env) == []
    log = (env / "run.log").read_text()
    assert log.count("\n") == 1 and "projects.json" in log
    (env / "projects.json").write_text(json.dumps({"projects": [{"name": 1}]}))
    assert projects.load(env) == []


def _register(env, tmp_path, name="p"):
    projects.add(env, proj(make_repo(tmp_path / f"r-{name}"), name=name))


def test_human_can_answer_supervisor_question(env, tmp_path, monkeypatch):
    _register(env, tmp_path)
    monkeypatch.setenv("SF_SOURCE", "supervisor")
    q = ["question", "--project", "p", "--strand", "supervisor", "--nr", "1",
         "--background", "b", "--recommendation", "r", "Q?"]
    assert cli.main(q) == 0
    monkeypatch.delenv("SF_SOURCE")
    assert cli.main(["answer", "--project", "p", "--id", "supervisor-1", "yes"]) == 0
    got, _ = events.read(env, "p")
    assert got[-1]["kind"] == "answer" and got[-1]["strand"] == "supervisor"


def test_duplicate_question_id_exit_1(env, tmp_path, capsys):
    _register(env, tmp_path)
    q = ["question", "--project", "p", "--strand", "a", "--nr", "1",
         "--background", "b", "--recommendation", "r", "Q?"]
    assert cli.main(q) == 0
    assert cli.main(q) == 1
    assert "a-1" in capsys.readouterr().err
    cli.main(["answer", "--project", "p", "--id", "a-1", "ok"])
    assert cli.main(q) == 1  # still asked before, even though answered
    got, _ = events.read(env, "p")
    assert [e["kind"] for e in got] == ["project_added", "question", "answer"]


def test_load_marker_ignores_bad_values(state):
    (state / "markers").mkdir()
    (state / "markers" / "wake.json").write_text(
        json.dumps({"a": 5, "b": -1, "c": True, "d": "7", "e": 1.5, "f": 0}))
    assert events.load_marker(state, "wake") == {"a": 5, "f": 0}


def test_non_utf8_projects_json_is_empty(env):
    (env / "projects.json").write_bytes(b"\xff\xfe\x00\x80binary")
    assert projects.load(env) == []
    assert "projects.json" in (env / "run.log").read_text()


@pytest.mark.parametrize("name", ["rows", "seen"])
def test_add_refuses_reserved_names(env, tmp_path, name, capsys):
    repo = make_repo(tmp_path / "r")
    assert cli.main(add_args(repo, name)) == 1
    assert "reserved" in capsys.readouterr().err
    assert projects.load(env) == []


def _write_registry(env, entries):
    (env / "projects.json").write_text(json.dumps({"projects": entries}))


def test_load_rejects_string_supervisor(env):
    _write_registry(env, [{"name": "a", "title": "A", "folder": "/x", "supervisor": "false"}])
    assert projects.load(env) == []
    assert "supervisor" in (env / "run.log").read_text()


def test_load_rejects_duplicate_names(env):
    _write_registry(env, [{"name": "a", "title": "A", "folder": "/x"},
                           {"name": "a", "title": "A", "folder": "/y"}])
    assert projects.load(env) == []
    assert "duplicate project name a" in (env / "run.log").read_text()


def _invalid_registry(env):
    f = env / "projects.json"
    f.write_text(json.dumps({"projects": [
        {"name": "one", "title": "One", "folder": "/x/one"},
        {"name": "two", "title": "Two", "folder": "/x/two", "supervisor": "false"}]}), encoding="utf-8")
    return f, f.read_bytes()


def test_project_add_refuses_invalid_registry(env, tmp_path, capsys):
    f, before = _invalid_registry(env)
    repo = make_repo(tmp_path / "newp")
    assert cli.main(add_args(repo, "newp")) == 1
    assert "sf-status: projects.json unreadable" in capsys.readouterr().err
    assert f.read_bytes() == before


def test_project_list_refuses_invalid_registry(env, capsys):
    _invalid_registry(env)
    assert cli.main(["project", "list"]) == 1
    cap = capsys.readouterr()
    assert "sf-status: projects.json unreadable" in cap.err and cap.out == ""


def test_project_remove_refuses_invalid_registry(env, capsys):
    f, before = _invalid_registry(env)
    assert cli.main(["project", "remove", "one"]) == 1
    assert "sf-status: projects.json unreadable" in capsys.readouterr().err
    assert f.read_bytes() == before


def test_project_list_missing_file_is_empty_ok(env, capsys):
    assert cli.main(["project", "list"]) == 0
    assert capsys.readouterr().out == ""
