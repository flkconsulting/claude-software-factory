"""All side effects of the server (tmux, git, claude, clock). Tests replace these functions."""
import json
import os
import re
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def now() -> datetime:
    return datetime.now(timezone.utc)


def _run(args: list[str], timeout: int = 10, env: dict | None = None) -> subprocess.CompletedProcess | None:
    try:
        kw = {} if env is None else {"env": env}
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)
    except (OSError, subprocess.SubprocessError):
        return None


def git_config(folder: Path, key: str) -> str | None:
    """Value of a git config key in a repository; None if unset or git is missing."""
    r = _run(["git", "-C", str(folder), "config", "--get", key])
    out = r.stdout.strip() if r and r.returncode == 0 else ""
    return out or None


def tmux_sessions() -> list[tuple[str, str]]:
    """(session name, current path of its first pane); empty if tmux is missing or has no server."""
    r = _run(["tmux", "list-panes", "-a", "-F", "#{session_name}|#{pane_current_path}"])
    if r is None or r.returncode != 0:
        return []
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        name, sep, path = line.partition("|")
        if sep and name and name not in out:
            out[name] = path
    return list(out.items())


def capture_pane(session: str) -> str | None:
    r = _run(["tmux", "capture-pane", "-p", "-t", f"{session}:"])
    return r.stdout if r and r.returncode == 0 else None


def strand_env(environ: dict) -> dict:
    """Environment without the supervisor marker and the variables of a running Claude Code session.

    A strand must not look like it was started from inside another session (it would not save its
    transcript) and must not pass the reserved-strand check as the supervisor.
    """
    return {k: v for k, v in environ.items()
            if k not in ("SF_SOURCE", "CLAUDECODE", "CLAUDE_PID") and not k.startswith("CLAUDE_CODE_")}


def tmux_new_session(name: str, cwd: str, command: str) -> bool:
    r = _run(["tmux", "new-session", "-d", "-s", name, "-c", cwd, command], env=strand_env(dict(os.environ)))
    return bool(r and r.returncode == 0)


def tmux_send(session: str, text: str) -> bool:
    r = _run(["tmux", "send-keys", "-t", f"{session}:", "-l", text])
    if not (r and r.returncode == 0):
        return False
    r = _run(["tmux", "send-keys", "-t", f"{session}:", "Enter"])
    return bool(r and r.returncode == 0)


def _end_group(proc) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
            return
        except subprocess.SubprocessError:
            continue


def _one_line(text: str, limit: int = 300) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)).strip()[:limit]


def run_claude(prompt: str, cwd: str, model: str, timeout_s: int, env: dict, log=None) -> tuple[int, dict | None]:
    """Run one headless claude call, prompt on stdin; returns (exit code, parsed JSON result or None).

    Timeout: the process group gets SIGTERM, then SIGKILL, and the code is 124. Not startable: 127.
    A failed call (exit not 0) hands one sanitized line of at most 300 characters of stderr to `log`.
    """
    argv = ["claude", "-p", "--model", model, "--output-format", "json", "--permission-mode", "auto"]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, cwd=cwd, env=env, start_new_session=True)
    except OSError:
        return 127, None
    try:
        out, err = proc.communicate(input=prompt, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _end_group(proc)
        return 124, None
    except (OSError, ValueError):
        _end_group(proc)
        return 1, None
    if log is not None and proc.returncode != 0 and isinstance(err, str) and err.strip():
        try:
            log(f"claude stderr: {_one_line(err)}")
        except Exception:
            pass
    try:
        data = json.loads(out)
    except (TypeError, ValueError):
        data = None
    return proc.returncode, data if isinstance(data, dict) else None


def spawn_detached(argv: list[str], cwd: str, env: dict) -> bool:
    """Start a process in its own session without waiting for it; False if it cannot be started."""
    try:
        subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True
