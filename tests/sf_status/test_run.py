import json

import pytest

from sf_status import cli, effects, events
from sf_status.projects import Project


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    state = tmp_path / "state"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    spawned = []
    monkeypatch.setattr(effects, "tmux_sessions", lambda: [])
    monkeypatch.setattr(effects, "spawn_detached", lambda argv, cwd, env: spawned.append(argv) or True)

    class Env:
        pass

    e = Env()
    e.state, e.spawned, e.home = state, spawned, home

    def configure(**server):
        server.setdefault("state_dir", str(state))
        (home / ".claude" / "software-factory.json").write_text(json.dumps({"server": server}))

    def register(supervisor=True):
        state.mkdir(parents=True, exist_ok=True)
        folder = tmp_path / "work" / "alpha"
        folder.mkdir(parents=True, exist_ok=True)
        (state / "projects.json").write_text(json.dumps({"projects": [
            Project(name="alpha", title="Alpha", folder=str(folder), supervisor=supervisor).__dict__]}))

    e.configure, e.register = configure, register
    return e


def log(env) -> list[str]:
    return (env.state / "run.log").read_text().splitlines()


def test_disabled_does_nothing(env):
    env.configure(enabled=False)
    assert cli.main(["run"]) == 0
    assert "server mode disabled" in log(env)[-1]
    assert not (env.state / "STATUS.md").exists() and env.spawned == []


def test_exception_logged_exit_0(env, monkeypatch):
    env.configure(enabled=True)
    from sf_status import collect

    def boom(*a, **k):
        raise RuntimeError("kaputt\nzweite zeile")

    monkeypatch.setattr(collect, "collect", boom)
    assert cli.main(["run"]) == 0
    lines = log(env)
    assert len(lines) == 1 and "RuntimeError" in lines[0]


def test_config_failure_exit_0_silent(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Could not determine home directory")

    monkeypatch.setattr(cli, "load_server_config", boom)
    assert cli.main(["run"]) == 0


def test_unwritable_log_exit_0(env, monkeypatch):
    env.configure(enabled=False)
    env.state.mkdir(parents=True)
    (env.state / "run.log").mkdir()  # a directory: appending fails
    assert cli.main(["run"]) == 0


def test_supervise_spawned_only_with_triggers_and_enabled(env):
    env.register()
    env.configure(enabled=True, supervisor=False)
    assert cli.main(["run"]) == 0
    assert env.spawned == []
    env.configure(enabled=True, supervisor=True)
    assert cli.main(["run"]) == 0  # safety trigger is open
    assert len(env.spawned) == 1
    assert env.spawned[0][-3:] == ["-m", "sf_status", "supervise"]
    assert (env.state / "STATUS.md").exists()


def test_no_open_triggers_no_spawn(env):
    env.configure(enabled=True, supervisor=True)  # no project: nothing to wake for
    assert cli.main(["run"]) == 0
    assert env.spawned == []


def test_pause_file_blocks(env):
    env.register()
    env.configure(enabled=True, supervisor=True)
    (env.state / "supervisor").mkdir(parents=True)
    (env.state / "supervisor" / "pause").write_text("")
    assert cli.main(["run"]) == 0
    assert env.spawned == []
    assert any("supervisor paused" in ln for ln in (env.state / "run.log").read_text().splitlines())


def test_dry_run_starts_and_commits_nothing(env):
    env.register()
    env.configure(enabled=True, supervisor=True)
    assert cli.main(["run", "--dry-run"]) == 0
    assert env.spawned == []
    assert not (env.state / "supervisor" / "triggers.json").exists()
    assert (env.state / "STATUS.md").exists()


def test_log_rotates_at_1mb(env):
    env.configure(enabled=False)
    env.state.mkdir(parents=True)
    (env.state / "run.log").write_text("x" * (1024 * 1024 + 1))
    assert cli.main(["run"]) == 0
    assert (env.state / "run.log.1").stat().st_size > 1024 * 1024
    assert len(log(env)) == 1


def test_wake_fast_forward_command(env):
    env.register()
    env.configure(enabled=True, supervisor=True)
    events.append(env.state, "alpha", {"kind": "report", "strand": "a", "state": "done", "text": "x"})
    assert cli.main(["wake", "fast-forward"]) == 0
    assert cli.main(["run"]) == 0
    assert env.spawned == []


def test_project_without_train_no_marker(env):
    env.configure()
    env.register()
    assert cli.main(["run"]) == 0
    assert not (env.state / "markers" / "train.json").exists()


def test_full_cycle_due_question_answer_row_trigger(env, tmp_path, monkeypatch):
    import subprocess
    from datetime import datetime, timezone

    folder = tmp_path / "work" / "alpha"
    (folder / "planning").mkdir(parents=True)
    (folder / "planning" / "wave-plan.md").write_text(
        "| short | strand | approval | starts when | branch | base | migrations | may change |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    (folder / "planning" / "RELEASES.md").write_text(
        "## Versions\n\n| version | line | state |\n| --- | --- | --- |\n| 2.1.0 | feature/v2.0 | planned |\n")
    for args in (["init", "-b", "main"], ["add", "."],
                 ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "init"]):
        subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)
    env.state.mkdir(parents=True)
    (env.state / "projects.json").write_text(json.dumps({"projects": [Project(
        name="alpha", title="Alpha", folder=str(folder), supervisor=True, approval_quote="ok",
        train=True).__dict__]}))
    env.configure(enabled=True, supervisor=True)

    clock = {"now": datetime(2026, 12, 1, 17, 30, tzinfo=timezone.utc)}
    monkeypatch.setattr(effects, "now", lambda: clock["now"])
    assert cli.main(["run"]) == 0
    data = json.loads((env.state / "supervisor" / "triggers.json").read_text())
    assert "train:2026-12-01" in [i["id"] for i in data["open"]]

    monkeypatch.setenv("SF_SOURCE", "supervisor")
    assert cli.main(["train", "question", "--project", "alpha", "--date", "2026-12-01", "--background", "bg",
                     "--recommendation", "2.1.0", "Release 2.1.0 on the test environment?"]) == 0
    monkeypatch.delenv("SF_SOURCE")
    assert cli.main(["answer", "--project", "alpha", "--id", "train-2026-12-01", "ja, 2.1.0"]) == 0

    clock["now"] = datetime(2026, 12, 1, 17, 40, tzinfo=timezone.utc)
    assert cli.main(["run"]) == 0
    data = json.loads((env.state / "supervisor" / "triggers.json").read_text())
    ids = [i["id"] for i in data["open"]]
    assert "approved:zug-2-1-0" in ids and "answer:train-2026-12-01" not in ids
    assert 'yes - "ja, 2.1.0"' in (folder / "planning" / "wave-plan.md").read_text()
    assert env.spawned
