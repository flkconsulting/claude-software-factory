"""Command line entry point; each subcommand registers itself in COMMANDS."""
import argparse
import os
import sys
from dataclasses import fields
from typing import Callable

from . import events
from .config import ServerConfig, load_server_config


def _add_config(sub) -> None:
    p = sub.add_parser("config", help="print one server setting")
    p.add_argument("key", choices=[f.name for f in fields(ServerConfig)])


def _run_config(args: argparse.Namespace) -> int:
    value = getattr(load_server_config(), args.key)
    print(str(value).lower() if isinstance(value, bool) else value)
    return 0


# ---- event commands -------------------------------------------------------

def _common(p, strand_required: bool = True) -> None:
    p.add_argument("--project", required=True)
    if strand_required:
        p.add_argument("--strand", required=True)


def _text(p, required: bool = True) -> None:
    p.add_argument("text", nargs=None if required else "?")


def _emit(args, event: dict) -> dict | int:
    """Append an event; returns the stored event or an exit code."""
    state_dir = load_server_config().state_dir
    # Until the project registry exists (task 3) only the event folder is checked.
    if not (state_dir / "events").is_dir():
        print("sf-status: server state folder not found; run the server setup first", file=sys.stderr)
        return 1
    strand = event["strand"]
    if strand == "supervisor" and os.environ.get("SF_SOURCE") != "supervisor":
        print("sf-status: strand id 'supervisor' is reserved for the supervisor", file=sys.stderr)
        return 2
    try:
        return events.append(state_dir, args.project, event)
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"sf-status: cannot write event: {e}", file=sys.stderr)
        return 1


def _finish(result) -> int:
    return result if isinstance(result, int) else 0


def _add_report(sub) -> None:
    p = sub.add_parser("report", help="report the state of a strand")
    _common(p)
    p.add_argument("--state", required=True)
    p.add_argument("--progress", type=int)
    p.add_argument("--branch")
    p.add_argument("--waiting-for", dest="waiting_for")
    _text(p)


def _run_report(args) -> int:
    ev = {"kind": "report", "strand": args.strand, "state": args.state, "text": args.text}
    for name in ("progress", "branch", "waiting_for"):
        if getattr(args, name) is not None:
            ev[name] = getattr(args, name)
    return _finish(_emit(args, ev))


def _add_start(sub) -> None:
    p = sub.add_parser("start", help="announce that a strand started")
    _common(p)
    p.add_argument("--topic", required=True)
    p.add_argument("--wave")
    _text(p)


def _run_start(args) -> int:
    ev = {"kind": "start", "strand": args.strand, "topic": args.topic, "text": args.text}
    if args.wave is not None:
        ev["wave"] = args.wave
    return _finish(_emit(args, ev))


def _add_question(sub) -> None:
    p = sub.add_parser("question", help="ask a question; prints the question id")
    _common(p)
    p.add_argument("--nr", type=int, required=True)
    p.add_argument("--background", required=True)
    p.add_argument("--recommendation", required=True)
    p.add_argument("text", metavar="question")


def _run_question(args) -> int:
    if args.nr < 1:
        print("sf-status: --nr must be at least 1", file=sys.stderr)
        return 2
    qid = f"{args.strand}-{args.nr}"
    ev = {"kind": "question", "strand": args.strand, "id": qid, "question": args.text,
          "background": args.background, "recommendation": args.recommendation}
    result = _emit(args, ev)
    if isinstance(result, int):
        return result
    print(qid)
    return 0


def _add_answer(sub) -> None:
    p = sub.add_parser("answer", help="answer an open question")
    _common(p, strand_required=False)
    p.add_argument("--id", required=True)
    _text(p)


def _run_answer(args) -> int:
    state_dir = load_server_config().state_dir
    if not (state_dir / "events").is_dir():
        print("sf-status: server state folder not found; run the server setup first", file=sys.stderr)
        return 1
    try:
        history, _ = events.read(state_dir, args.project)
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    question = events.open_questions(history).get(args.id)
    if question is None:
        print(f"sf-status: no open question {args.id!r} in project {args.project!r}", file=sys.stderr)
        return 1
    ev = {"kind": "answer", "strand": question["strand"], "question_id": args.id, "text": args.text}
    return _finish(_emit(args, ev))


def _add_task(sub) -> None:
    p = sub.add_parser("task", help="record a task for the human, or mark one done")
    _common(p)
    p.add_argument("--id")
    p.add_argument("--why")
    p.add_argument("--done", metavar="ID")
    _text(p, required=False)


def _run_task(args) -> int:
    if args.done is not None:
        ev = {"kind": "task_done", "strand": args.strand, "id": args.done}
    else:
        if not (args.id and args.why and args.text):
            print("sf-status: task needs --id, --why and a title (or --done ID)", file=sys.stderr)
            return 2
        ev = {"kind": "task", "strand": args.strand, "id": args.id, "title": args.text, "why": args.why}
    return _finish(_emit(args, ev))


def _add_notice(sub) -> None:
    p = sub.add_parser("notice", help="leave a notice for the human")
    _common(p)
    p.add_argument("--level", required=True)
    p.add_argument("--title", required=True)
    _text(p)


def _run_notice(args) -> int:
    ev = {"kind": "notice", "strand": args.strand, "level": args.level, "title": args.title,
          "text": args.text}
    return _finish(_emit(args, ev))


# name -> (function adding the subparser, function running it with parsed args)
# Later tasks append their own entries here.
COMMANDS: dict[str, tuple[Callable, Callable[[argparse.Namespace], int]]] = {
    "config": (_add_config, _run_config),
    "report": (_add_report, _run_report),
    "start": (_add_start, _run_start),
    "question": (_add_question, _run_question),
    "answer": (_add_answer, _run_answer),
    "task": (_add_task, _run_task),
    "notice": (_add_notice, _run_notice),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sf-status")
    sub = parser.add_subparsers(dest="command", required=True)
    for add, _ in COMMANDS.values():
        add(sub)
    return parser


def main(argv: list[str]) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    return COMMANDS[args.command][1](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
