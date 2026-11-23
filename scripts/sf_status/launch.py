"""Start a work strand in tmux and deliver follow-ups to it."""
import dataclasses
import os
import shlex
import sys
import time
from pathlib import Path

from . import collect, effects, events
from .config import ServerConfig
from .projects import Project, project_for_path

MODELS = ("haiku", "sonnet", "opus")
FOLLOWUP_HEADING = "## Follow-up "
# A strand must not inherit the session-identity variables of the supervisor or an outer Claude Code session
# (fixed names, see effects.SESSION_ENV_NAMES); auth, provider and config variables are kept.
CLEAN_ENV = "unset " + " ".join(effects.SESSION_ENV_NAMES) + "; "


def _fail(message: str) -> int:
    print(f"sf-status: {message}", file=sys.stderr)
    return 1


def _start_file(cfg: ServerConfig, project: Project, short: str) -> Path:
    return Path(cfg.state_dir) / "start" / project.name / f"{short}.md"


def launch(cfg: ServerConfig, project: Project, short: str, model: str, worktree: Path, topic: str) -> int:
    if not events.valid_id(short):
        return _fail(f"invalid strand name {short!r}")
    if model not in MODELS:
        return _fail(f"model must be one of {', '.join(MODELS)}")
    start_file = _start_file(cfg, project, short)
    if not start_file.is_file():
        return _fail(f"start file {start_file} does not exist")
    worktree = Path(worktree)
    if not worktree.is_dir():
        return _fail(f"worktree {worktree} does not exist")
    worktree = Path(os.path.realpath(worktree))
    # registrations made before real paths were stored may hold a symlinked folder
    project = dataclasses.replace(project, folder=os.path.realpath(project.folder))
    if worktree == Path(project.folder):
        return _fail(f"worktree {worktree} is the main checkout of project {project.name!r}; "
                     f"use a separate worktree ({project.folder}-{short})")
    if project_for_path([project], worktree) != project.name:
        return _fail(f"worktree {worktree} does not belong to project {project.name!r}")
    session = f"{project.name}-{short}"
    live = effects.tmux_sessions()
    running = collect.running_strand_sessions([project], project.name, Path(cfg.state_dir), live)
    if session in [name for name, _ in live]:
        return _fail(f"tmux session {session} already exists")
    if len(running) >= cfg.max_strands:
        return _fail(f"project {project.name!r} already has {len(running)} running strands (max_strands {cfg.max_strands})")
    prompt = f"Read {start_file} and carry out the task completely."
    command = (f"{CLEAN_ENV}CLAUDE_CODE_AUTO_COMPACT_WINDOW={int(cfg.auto_compact_window)} claude -n {shlex.quote(short)} "
               f"--model {model} --permission-mode auto {shlex.quote(prompt)}; exec bash")
    if not effects.tmux_new_session(session, str(worktree), command):
        return _fail(f"cannot start tmux session {session}")
    try:
        events.append(Path(cfg.state_dir), project.name,
                      {"kind": "start", "strand": short, "topic": topic,
                       "text": f"Strand started in tmux session {session} with model {model}."})
    except (OSError, ValueError) as e:
        return _fail(f"strand started but the start event was not written: {e}")
    return 0


def deliver(cfg: ServerConfig, project: Project, strand: str, text: str, wait_s: float = 20) -> int:
    if not events.valid_id(strand):
        return _fail(f"invalid strand name {strand!r}")
    start_file = _start_file(cfg, project, strand)
    if not start_file.is_file():
        return _fail(f"start file {start_file} does not exist")
    session = f"{project.name}-{strand}"
    if session not in [name for name, _ in effects.tmux_sessions()]:
        return _fail(f"tmux session {session} does not exist")
    try:
        body = start_file.read_text(encoding="utf-8")
        seq = 1 + sum(1 for line in body.splitlines() if line.startswith(FOLLOWUP_HEADING))
        with open(start_file, "a", encoding="utf-8") as f:
            f.write(f"{'' if body.endswith(chr(10)) else chr(10)}\n{FOLLOWUP_HEADING}{seq}\n\n{text.rstrip()}\n")
    except OSError as e:
        return _fail(f"cannot append to {start_file}: {e}")
    pointer = f"Read follow-up {seq} in {start_file}."
    if not effects.tmux_send(session, pointer):
        return _fail(f"cannot send to tmux session {session}")
    if wait_s:
        time.sleep(wait_s)
    pane = effects.capture_pane(session) or ""
    if "".join(pointer.split()) not in "".join(pane.split()):  # the pane may wrap the line
        return _fail(f"follow-up {seq} did not arrive in {session}; it stays in {start_file}")
    try:
        events.append(Path(cfg.state_dir), project.name, {"kind": "delivered", "strand": strand, "seq": seq})
    except (OSError, ValueError) as e:
        return _fail(f"delivered but the event was not written: {e}")
    return 0
