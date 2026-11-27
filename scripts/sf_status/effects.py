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


def git_cherry(folder: Path, line: str, branch: str) -> list[str] | None:
    """Commit ids on `branch` that are not on `line` (lines marked "+" by git cherry, read only).

    Patch-equal commits count as arrived. None if git fails, times out or the branch is missing."""
    r = _run(["git", "-C", str(folder), "cherry", line, branch], timeout=30)
    if not r or r.returncode != 0:
        return None
    return [ln[2:].strip() for ln in r.stdout.splitlines() if ln.startswith("+ ")]


def git_path_clean(folder: Path, path: str) -> bool | None:
    """True if `git status --porcelain -- path` is empty (no change, nothing untracked); None if git fails."""
    r = _run(["git", "-C", str(folder), "status", "--porcelain", "--", path], timeout=30)
    if not r or r.returncode != 0:
        return None
    return r.stdout.strip() == ""


def git_commit_path(folder: Path, path: str, message: str) -> bool:
    """Commit only `path` locally (never pushes); False if adding or committing fails."""
    who = ["-c", "user.name=sf-status", "-c", "user.email=sf-status@localhost"]
    r = _run(["git", "-C", str(folder), "add", "--", path], timeout=30)
    if not r or r.returncode != 0:
        return False
    r = _run(["git", "-C", str(folder), *who, "commit", "-m", message, "--", path], timeout=60)
    if r and r.returncode == 0:
        return True
    _run(["git", "-C", str(folder), "reset", "-q", "--", path], timeout=30)  # leave nothing staged behind
    return False


def git_remote_head(folder: Path, branch: str) -> str | None:
    """Commit id of a branch on the remote origin; None if unreadable or missing."""
    r = _run(["git", "-C", str(folder), "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
             timeout=30, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if not r or r.returncode != 0:
        return None
    lines = r.stdout.strip().splitlines()
    return lines[0].split()[0] if lines and lines[0].split() else None


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


# Variables that identify the running (outer) session; auth, provider and config variables are not listed.
SESSION_ENV_NAMES = ("SF_SOURCE", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID",
                     "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_CHILD_NOTES_DIR", "CLAUDE_CODE_SESSION_ATTENDED",
                     "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN")


def strand_env(environ: dict) -> dict:
    """Environment without the session-identity variables (SESSION_ENV_NAMES, exact names only).

    A strand must not look like it was started from inside another session (it would not save its
    transcript) and must not pass the reserved-strand check as the supervisor. Auth, provider and
    config variables (e.g. CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_CODE_USE_BEDROCK) stay, so the strand can log in.
    """
    return {k: v for k, v in environ.items() if k not in SESSION_ENV_NAMES}


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
    """End the whole process group of proc: SIGTERM, up to 5 s for the leader, then SIGKILL for the group."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.SubprocessError:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.SubprocessError:
        pass
    for pipe in (proc.stdout, proc.stderr):
        try:
            if pipe is not None:
                pipe.close()
        except OSError:
            pass


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
