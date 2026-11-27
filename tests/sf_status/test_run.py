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
