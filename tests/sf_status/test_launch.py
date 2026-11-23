import json
from pathlib import Path

import pytest

from sf_status import effects, events, launch
from sf_status.projects import Project


class Fake:
    def __init__(self):
        self.sessions = []  # (name, path)
        self.started = []
        self.sent = []
        self.pane = ""
        self.deliver_ok = True


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(effects, "tmux_sessions", lambda: list(f.sessions))
    monkeypatch.setattr(effects, "tmux_new_session", lambda *a: f.started.append(a) or True)

    def send(session, text):
        f.sent.append((session, text))
        if f.deliver_ok:
            f.pane += text + "\n"
        return True
    monkeypatch.setattr(effects, "tmux_send", send)
    monkeypatch.setattr(effects, "capture_pane", lambda s: f.pane)
    return f


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "repo"
    folder.mkdir()
    return Project(name="demo", title="Demo", folder=str(folder), main_branch="main", supervisor=False,
                   approval_quote=None, wave_plan="planning/wave-plan.md", never_touch=[])


@pytest.fixture
def worktree(tmp_path):
    p = tmp_path / "repo-alpha"
    p.mkdir()
    return p


def start_file(cfg, short="alpha", text="Do the thing.\n"):
    path = Path(cfg.state_dir) / "start" / "demo" / f"{short}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_launch_command_line(cfg, project, worktree, fake):
    sf = start_file(cfg)
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "topic") == 0
    name, cwd, command = fake.started[0]
    assert name == "demo-alpha" and cwd == str(worktree)
    assert command == (f"{launch.CLEAN_ENV}CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000 claude -n alpha --model sonnet "
                       f"--permission-mode auto 'Read {sf} and carry out the task completely.'; exec bash")
    assert "dangerously" not in command
    evs, _ = events.read(Path(cfg.state_dir), "demo")
    assert [e["kind"] for e in evs] == ["start"] and evs[0]["strand"] == "alpha" and evs[0]["topic"] == "topic"


def test_launch_quotes_paths(cfg, project, tmp_path, fake):
    wt = tmp_path / "repo-a b"
    wt.mkdir()
    sf = start_file(cfg)
    assert launch.launch(cfg, project, "alpha", "opus", wt, "t") == 0
    assert fake.started[0][1] == str(wt)


def test_launch_refuses_existing_session(cfg, project, worktree, fake, capsys):
    start_file(cfg)
    fake.sessions = [("demo-alpha", str(worktree))]
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "t") == 1
    assert fake.started == [] and "already exists" in capsys.readouterr().err


def test_launch_refuses_over_max_strands(cfg, project, worktree, fake, tmp_path, capsys):
    import dataclasses
    cfg = dataclasses.replace(cfg, max_strands=2)
    start_file(cfg)
    fake.sessions = [("demo-one", str(tmp_path / "repo-one")), ("demo-two", str(tmp_path / "repo-two")),
                     ("other-x", "/nowhere")]
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "t") == 1
    assert fake.started == [] and "max_strands" in capsys.readouterr().err


def test_launch_refuses_foreign_worktree(cfg, project, fake, tmp_path, capsys):
    start_file(cfg)
    foreign = tmp_path / "elsewhere"
    foreign.mkdir()
    assert launch.launch(cfg, project, "alpha", "sonnet", foreign, "t") == 1
    assert fake.started == [] and "does not belong" in capsys.readouterr().err


@pytest.mark.parametrize("short,model", [("Bad Name", "sonnet"), ("alpha", "gpt"), ("alpha", "")])
def test_launch_refuses_bad_names(cfg, project, worktree, fake, short, model, capsys):
    start_file(cfg)
    assert launch.launch(cfg, project, short, model, worktree, "t") == 1
    assert fake.started == [] and capsys.readouterr().err.count("\n") == 1


def test_launch_refuses_missing_start_file(cfg, project, worktree, fake, capsys):
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "t") == 1
    assert "start file" in capsys.readouterr().err


def test_launch_tmux_failure(cfg, project, worktree, fake, monkeypatch, capsys):
    start_file(cfg)
    monkeypatch.setattr(effects, "tmux_new_session", lambda *a: False)
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "t") == 1
    assert events.read(Path(cfg.state_dir), "demo")[0] == []


def live(fake, worktree):
    fake.sessions = [("demo-alpha", str(worktree))]


def test_deliver_appends_numbered_followup(cfg, project, worktree, fake):
    sf = start_file(cfg)
    live(fake, worktree)
    assert launch.deliver(cfg, project, "alpha", "First text", wait_s=0) == 0
    assert launch.deliver(cfg, project, "alpha", "Second text", wait_s=0) == 0
    body = sf.read_text(encoding="utf-8")
    assert "## Follow-up 1\n\nFirst text" in body and "## Follow-up 2\n\nSecond text" in body
    evs, _ = events.read(Path(cfg.state_dir), "demo")
    assert [(e["kind"], e["seq"]) for e in evs] == [("delivered", 1), ("delivered", 2)]


def test_deliver_sends_only_pointer(cfg, project, worktree, fake):
    sf = start_file(cfg)
    live(fake, worktree)
    secret = "free text <script> rm -rf"
    assert launch.deliver(cfg, project, "alpha", secret, wait_s=0) == 0
    assert fake.sent == [("demo-alpha", f"Read follow-up 1 in {sf}.")]
    assert secret not in fake.sent[0][1]


def test_deliver_unconfirmed_exit_1(cfg, project, worktree, fake, capsys):
    start_file(cfg)
    live(fake, worktree)
    fake.deliver_ok = False
    assert launch.deliver(cfg, project, "alpha", "x", wait_s=0) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "Traceback" not in err
    assert events.read(Path(cfg.state_dir), "demo")[0] == []


def test_deliver_without_session(cfg, project, fake, capsys):
    start_file(cfg)
    assert launch.deliver(cfg, project, "alpha", "x", wait_s=0) == 1
    assert fake.sent == []


def test_launch_refuses_project_folder_itself(cfg, project, fake, capsys):
    start_file(cfg)
    assert launch.launch(cfg, project, "alpha", "sonnet", Path(project.folder), "t") == 1
    assert fake.started == [] and "main checkout" in capsys.readouterr().err


def test_launch_command_drops_supervisor_environment(cfg, project, worktree, fake):
    import os
    import subprocess
    start_file(cfg)
    assert launch.launch(cfg, project, "alpha", "sonnet", worktree, "t") == 0
    command = fake.started[0][2]
    for name in effects.SESSION_ENV_NAMES:
        assert name in command.split(" claude ")[0]
    # run only the cleaning prefix in a real shell with a polluted environment
    prefix = command.split("CLAUDE_CODE_AUTO_COMPACT_WINDOW", 1)[0]
    kept = {"CLAUDE_CODE_OAUTH_TOKEN": "t", "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_FUTURE_THING": "y",
            "KEEP_ME": "z"}
    env = {**os.environ, **{n: "1" for n in effects.SESSION_ENV_NAMES}, **kept}
    out = subprocess.run(["sh", "-c", prefix + "env"], env=env, capture_output=True, text=True).stdout
    lines = out.splitlines()
    for name, value in kept.items():
        assert f"{name}={value}" in lines
    for name in effects.SESSION_ENV_NAMES:
        assert not any(line.startswith(name + "=") for line in lines)


def test_tmux_new_session_env_is_clean(monkeypatch):
    seen = {}

    def run(args, **kw):
        seen["env"] = kw.get("env")

        class R:
            returncode = 0
            stdout = ""
        return R()

    monkeypatch.setattr(effects.subprocess, "run", run)
    for name in effects.SESSION_ENV_NAMES:
        monkeypatch.setenv(name, "1")
    kept = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_FUTURE_THING", "KEEP_ME")
    for name in kept:
        monkeypatch.setenv(name, "z")
    assert effects.tmux_new_session("n", "/tmp", "cmd")
    env = seen["env"]
    assert all(env[name] == "z" for name in kept)
    assert not [k for k in env if k in effects.SESSION_ENV_NAMES]
