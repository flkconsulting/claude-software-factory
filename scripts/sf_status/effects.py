"""All side effects of the server (tmux, git, claude, clock). Tests replace these functions."""
import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def now() -> datetime:
    return datetime.now(timezone.utc)


def _run(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
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


def tmux_new_session(name: str, cwd: str, command: str) -> bool:
    r = _run(["tmux", "new-session", "-d", "-s", name, "-c", cwd, command])
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


def run_claude(prompt: str, cwd: str, model: str, timeout_s: int, env: dict) -> tuple[int, dict | None]:
    """Run one headless claude call, prompt on stdin; returns (exit code, parsed JSON result or None).

    Timeout: the process group gets SIGTERM, then SIGKILL, and the code is 124. Not startable: 127.
    """
    argv = ["claude", "-p", "--model", model, "--output-format", "json", "--permission-mode", "auto"]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, cwd=cwd, env=env, start_new_session=True)
    except OSError:
        return 127, None
    try:
        out, _ = proc.communicate(input=prompt, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _end_group(proc)
        return 124, None
    except (OSError, ValueError):
        _end_group(proc)
        return 1, None
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
