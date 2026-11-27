"""Command line entry point; each subcommand registers itself in COMMANDS."""
import argparse
import getpass
import json
import os
import re
import sys
from datetime import datetime, timezone
from dataclasses import fields
from pathlib import Path
from typing import Callable

from . import checks, collect, effects, events, launch, planning, projects, render, supervisor, train, wake
from .config import DEFAULT_STATE_DIR, ServerConfig, load_server_config
from .planning import load_releases, load_tickets


def _config() -> ServerConfig | None:
    """Server config, or None after one stderr line when the home folder is unknown."""
    try:
        return load_server_config()
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return None


def _add_config(sub) -> None:
    p = sub.add_parser("config", help="print one server setting")
    p.add_argument("key", choices=[f.name for f in fields(ServerConfig)])


def _run_config(args: argparse.Namespace) -> int:
    cfg = _config()
    if cfg is None:
        return 1
    value = getattr(cfg, args.key)
    print(str(value).lower() if isinstance(value, bool) else value)
    return 0


# ---- event commands -------------------------------------------------------

def _common(p, strand_required: bool = True) -> None:
    p.add_argument("--project", required=True)
    if strand_required:
        p.add_argument("--strand", required=True)


def _text(p, required: bool = True) -> None:
    p.add_argument("text", nargs=None if required else "?")


def _registered(state_dir: Path, name: str) -> bool:
    if any(p.name == name for p in projects.load(state_dir)):
        return True
    print(f"sf-status: project {name!r} is not registered (sf-status project add)", file=sys.stderr)
    return False


def _emit(args, event: dict, reserved_check: bool = True) -> dict | int:
    """Append an event; returns the stored event or an exit code."""
    cfg = _config()
    if cfg is None:
        return 1
    state_dir = cfg.state_dir
    if not _registered(state_dir, args.project):
        return 1
    strand = event["strand"]
    if reserved_check and strand == "supervisor" and os.environ.get("SF_SOURCE") != "supervisor":
        print("sf-status: strand id 'supervisor' is reserved for the supervisor", file=sys.stderr)
        return 2
    if reserved_check and strand == projects.SYSTEM_STRAND:
        print(f"sf-status: strand id '{projects.SYSTEM_STRAND}' is reserved", file=sys.stderr)
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
    cfg = _config()
    if cfg is None:
        return 1
    state_dir = cfg.state_dir
    if _registered(state_dir, args.project):
        try:
            history, _ = events.read(state_dir, args.project)
        except ValueError as e:
            print(f"sf-status: {e}", file=sys.stderr)
            return 2
        if any(e.get("kind") == "question" and e.get("id") == qid for e in history):
            print(f"sf-status: question {qid!r} was already asked in project {args.project!r}",
                  file=sys.stderr)
            return 1
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
    cfg = _config()
    if cfg is None:
        return 1
    state_dir = cfg.state_dir
    if not _registered(state_dir, args.project):
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
    return _finish(_emit(args, ev, reserved_check=False))


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


def _add_dismiss(sub) -> None:
    p = sub.add_parser("dismiss", help="dismiss notices on the board (the event file keeps them)")
    p.add_argument("--project", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--time", help="time of the notice (ISO, as shown on the board)")
    g.add_argument("--strand", help="dismiss all shown notices of this strand")
    g.add_argument("--all", action="store_true", help="dismiss all shown notices of the project")
    p.add_argument("--title", help="with --time: title, to tell notices of the same time apart")
    p.add_argument("--by", help="who dismisses (default: $SF_SOURCE, else the login name)")


def _login_name() -> str:
    try:
        return getpass.getuser() or "unknown"
    except (OSError, KeyError):
        return "unknown"


def _run_dismiss(args) -> int:
    if args.title is not None and args.time is None:
        print("sf-status: --title only goes with --time", file=sys.stderr)
        return 2
    by = args.by or os.environ.get("SF_SOURCE") or _login_name()
    cfg = _config()
    if cfg is None:
        return 1
    if not _registered(cfg.state_dir, args.project):
        return 1
    try:
        history, _ = events.read(cfg.state_dir, args.project)
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    cutoff = collect.cutoff_iso(datetime.now(timezone.utc).timestamp())
    shown = collect.shown_notices(collect.sort_events(history), cutoff)
    if args.time is not None:
        hits = [n for n in shown if n.get("time") == args.time
                and (args.title is None or n.get("title") == args.title)]
        if not hits:
            print(f"sf-status: no shown notice at {args.time!r}"
                  + (f" with title {args.title!r}" if args.title else "") + f" in project {args.project!r}",
                  file=sys.stderr)
            return 1
        if len(hits) > 1:
            print(f"sf-status: {len(hits)} notices at {args.time!r}; add --title to pick one:", file=sys.stderr)
            for n in hits:
                print(f"  {n.get('title')}", file=sys.stderr)
            return 2
    elif args.strand is not None:
        hits = [n for n in shown if n.get("strand") == args.strand]
    else:
        hits = list(shown)
    if not hits:
        print(f"sf-status: no shown notice to dismiss in project {args.project!r}", file=sys.stderr)
        return 1
    for n in hits:
        ev = {"kind": "dismiss", "strand": n["strand"], "notice_time": n["time"], "notice_title": n["title"],
              "by": by}
        result = _emit(args, ev, reserved_check=False)
        if isinstance(result, int):
            return result
        print(f"{n['time']} {n['title']}")
    return 0


def _add_attention(sub) -> None:
    p = sub.add_parser("attention", help="print what needs the human as JSON (from the last run)")
    p.add_argument("--project", help="only this project")


def _run_attention(args) -> int:
    cfg = _config()
    if cfg is None:
        return 1
    path = Path(cfg.state_dir) / "attention.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"sf-status: cannot read {path}: {e}", file=sys.stderr)
        return 1
    if args.project is not None:
        data = {k: [i for i in v if isinstance(i, dict) and i.get("project") == args.project]
                for k, v in data.items() if isinstance(v, list)}
    print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


def _add_backport(sub) -> None:
    p = sub.add_parser("backport", help="list commits of release/<version> missing on its line (read only)")
    p.add_argument("--project", required=True)
    p.add_argument("--version", required=True)


def _run_backport(args) -> int:
    """Exit 0 nothing missing, 1 something missing (one JSON line each), 2 unknown or not checkable."""
    cfg = _config()
    if cfg is None:
        return 2
    project = _project(args.project, Path(cfg.state_dir))
    if project is None:
        return 2
    releases = load_releases(project)
    version = next((v for v in releases.versions if v.version == args.version), None) if releases else None
    if version is None:
        print(f"sf-status: version {args.version!r} is not listed in planning/RELEASES.md", file=sys.stderr)
        return 2
    commits = checks.missing_backports(Path(project.folder), version)
    if commits is None:
        print(f"sf-status: cannot check release/{version.version} against {version.line!r} "
              "(invalid values, missing branch or git failure)", file=sys.stderr)
        return 2
    for sha in commits:
        print(json.dumps({"version": version.version, "line": version.line, "commit": sha}))
    return 1 if commits else 0


def _add_tickets(sub) -> None:
    p = sub.add_parser("tickets", help="list tickets as JSON lines (read only)")
    p.add_argument("--project", help="only this project")
    p.add_argument("--train", help="only tickets whose version rides this train (YYYY-MM-DD)")


def _run_tickets(args) -> int:
    """One JSON line per ticket; exit 1 unknown project, 2 bad date, 0 otherwise (also without files)."""
    cfg = _config()
    if cfg is None:
        return 1
    if args.train is not None:
        try:
            datetime.strptime(args.train, "%Y-%m-%d")
        except ValueError:
            print(f"sf-status: --train needs a date like 2026-12-01, got {args.train!r}", file=sys.stderr)
            return 2
    state_dir = Path(cfg.state_dir)
    if args.project is not None:
        project = _project(args.project, state_dir)
        if project is None:
            return 1
        chosen = [project]
    else:
        chosen = projects.load(state_dir)
    for p in chosen:
        table = load_tickets(p)
        if table is None:
            continue
        rows = table.rows
        if args.train is not None:
            releases = load_releases(p)
            versions = {v.version for v in releases.versions if v.train == args.train} if releases else set()
            rows = [t for t in rows if t.version in versions]
        for t in rows:
            print(json.dumps({"project": p.name, **{f.name: getattr(t, f.name) for f in fields(t)}},
                             ensure_ascii=False))
    return 0


# ---- project registry -------------------------------------------------------

def _train_options(p) -> None:
    p.add_argument("--train", choices=("on", "off"))
    p.add_argument("--train-day", help="mon|tue|wed|thu|fri|sat|sun")
    p.add_argument("--train-time", help="HH:MM")
    p.add_argument("--train-tz", help="time zone name, e.g. Europe/Berlin")
    p.add_argument("--train-skip", help="comma-separated dates YYYY-MM-DD without a train (empty clears)")


def _train_changes(args) -> dict:
    """Only the train options that were given, as Project field values."""
    out: dict = {}
    if args.train is not None:
        out["train"] = args.train == "on"
    for opt, key in (("train_day", "train_day"), ("train_time", "train_time"), ("train_tz", "train_tz")):
        if getattr(args, opt) is not None:
            out[key] = getattr(args, opt)
    if args.train_skip is not None:
        out["train_skip"] = [x.strip() for x in args.train_skip.split(",") if x.strip()]
    return out


def _add_project(sub) -> None:
    p = sub.add_parser("project", help="register, remove or list projects")
    ps = p.add_subparsers(dest="project_command", required=True)
    a = ps.add_parser("add", help="register a project")
    a.add_argument("name")
    a.add_argument("--title", required=True)
    a.add_argument("--folder", required=True)
    a.add_argument("--main-branch", default="main")
    a.add_argument("--supervisor", choices=("yes", "no"), default="no")
    a.add_argument("--approval-quote")
    a.add_argument("--wave-plan", default="planning/wave-plan.md")
    a.add_argument("--never-touch", default="")
    _train_options(a)
    st = ps.add_parser("set", help="change the train settings of a project")
    st.add_argument("--project", required=True)
    _train_options(st)
    r = ps.add_parser("remove", help="unregister a project (its event file stays)")
    r.add_argument("name")
    ps.add_parser("list", help="list registered projects")


def _run_project(args) -> int:
    cfg = _config()
    if cfg is None:
        return 1
    state_dir = cfg.state_dir
    try:
        if args.project_command == "add":
            projects.add(state_dir, projects.Project(
                name=args.name, title=args.title, folder=os.path.realpath(os.path.expanduser(args.folder)),
                main_branch=args.main_branch, supervisor=args.supervisor == "yes",
                approval_quote=args.approval_quote, wave_plan=args.wave_plan,
                never_touch=[x.strip() for x in args.never_touch.split(",") if x.strip()],
                **_train_changes(args)))
        elif args.project_command == "set":
            changes = _train_changes(args)
            if not changes:
                print("sf-status: project set needs at least one option (--train, --train-day, "
                      "--train-time, --train-tz, --train-skip)", file=sys.stderr)
                return 2
            projects.update(state_dir, args.project, changes)
        elif args.project_command == "remove":
            projects.remove(state_dir, args.name)
        else:
            for p in projects.load_strict(state_dir):
                line = f"{p.name}\t{p.title}\t{p.folder}\tsupervisor={'yes' if p.supervisor else 'no'}"
                if p.train:
                    line += f"\ttrain={p.train_day} {p.train_time} {p.train_tz}"
                print(line)
    except (projects.ProjectError, OSError, ValueError) as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 1
    return 0


# ---- cron run -------------------------------------------------------------

LOG_MAX = 1024 * 1024


def _log(state_dir: Path, line: str) -> None:
    """One line to run.log (rotated at 1 MB, one generation); never raises."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "run.log"
        try:
            if path.stat().st_size >= LOG_MAX:
                os.replace(path, state_dir / "run.log.1")
        except FileNotFoundError:
            pass
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except Exception:
        pass


def _one_line(text: str, limit: int = 300) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()[:limit]


def _add_train(sub) -> None:
    p = sub.add_parser("train", help="release train")
    ts = p.add_subparsers(dest="train_command", required=True)
    q = ts.add_parser("question", help="ask the train question (supervisor only); prints the question id")
    q.add_argument("--project", required=True)
    q.add_argument("--date", required=True, help="cut-off date, YYYY-MM-DD")
    q.add_argument("--background", required=True)
    q.add_argument("--recommendation", required=True)
    q.add_argument("text", metavar="question")


def _run_train(args) -> int:
    if os.environ.get("SF_SOURCE") != "supervisor":
        print("sf-status: the train question is asked by the supervisor only", file=sys.stderr)
        return 2
    if not projects.DATE_RE.fullmatch(args.date):
        print("sf-status: --date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print("sf-status: --date is not a real date", file=sys.stderr)
        return 2
    cfg = _config()
    if cfg is None:
        return 1
    project = _project(args.project, cfg.state_dir)
    if project is None:
        return 1
    if not project.train:
        print(f"sf-status: project {args.project!r} has no release train (sf-status project set --train on)",
              file=sys.stderr)
        return 1
    rel = planning.load_releases(project)
    cands = [v.version for v in train.candidates(rel)] if rel is not None else []
    if not cands:
        print("sf-status: no planned version in RELEASES.md; nothing to ask", file=sys.stderr)
        return 1
    missing = [v for v in cands if not train.names_version(args.text, v)]
    if missing:
        print(f"sf-status: the question must name every candidate version (missing: {', '.join(missing)})",
              file=sys.stderr)
        return 2
    try:
        history, _ = events.read(cfg.state_dir, args.project)
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    marker = train.load_marker(cfg.state_dir)
    entry = marker.setdefault(args.project, {})
    entry.setdefault("dates", {})
    questions = entry.setdefault("questions", {})
    taken = {e.get("id") for e in history if e.get("kind") == "question"} | set(questions)
    qid, n = f"train-{args.date}", 1
    while qid in taken:
        n += 1
        qid = f"train-{args.date}-{n}"
    ev = {"kind": "question", "strand": "supervisor", "id": qid, "question": args.text,
          "background": args.background, "recommendation": args.recommendation}
    result = _emit(args, ev)
    if isinstance(result, int):
        return result
    questions[qid] = {"state": "open", "candidates": cands}
    try:
        train.save_marker(cfg.state_dir, marker)
    except OSError as e:
        print(f"sf-status: question {qid} written but the train marker was not: {e}", file=sys.stderr)
        return 1
    print(qid)
    return 0


def _add_run(sub) -> None:
    p = sub.add_parser("run", help="one cron run: status files, wake triggers, start the supervisor")
    p.add_argument("--dry-run", action="store_true", help="collect and render as usual (this still writes stall/notice events and markers), but adopt no wake triggers and start no supervisor")


def _open_triggers(state_dir: Path) -> int:
    try:
        data = json.loads((state_dir / "supervisor" / "triggers.json").read_text(encoding="utf-8"))
        return len([i for i in data.get("open", []) if isinstance(i, dict)])
    except (OSError, ValueError, AttributeError):
        return 0


def _run_run(args) -> int:
    state_dir = None
    try:
        cfg = load_server_config()
        state_dir = Path(cfg.state_dir)
        if not cfg.enabled:
            _log(state_dir, "server mode disabled")
            return 0
        now = effects.now()
        items = projects.load(state_dir)
        state = collect.collect(cfg, items, now.timestamp())
        render.write(state_dir, state, now)
        if not args.dry_run:
            try:
                train.process_answers(cfg, items, state_dir, now)
            except Exception as e:  # a failing train step must not stop the rest of the run
                _log(state_dir, f"train answers failed: {type(e).__name__}: {_one_line(str(e))}")
        triggers = wake.collect_triggers(cfg, items, state_dir, now)
        if args.dry_run:
            _log(state_dir, f"dry run: would raise {len(triggers)} triggers: {', '.join(triggers) or 'none'}")
            return 0
        wake.commit_triggers(state_dir, triggers, now)
        open_count = _open_triggers(state_dir)
        if not cfg.supervisor:
            return 0
        if (state_dir / "supervisor" / "pause").exists():
            _log(state_dir, f"supervisor paused, {open_count} triggers open")
        elif open_count:
            argv = [sys.executable, "-m", "sf_status", "supervise"]
            if effects.spawn_detached(argv, str(Path(__file__).resolve().parent.parent), dict(os.environ)):
                _log(state_dir, f"supervisor started, {open_count} triggers open")
            else:
                _log(state_dir, f"supervisor not started, {open_count} triggers open")
    except Exception as e:
        if state_dir is None:  # config failed: only a sure absolute default can take the line
            default = os.path.expanduser(DEFAULT_STATE_DIR)
            state_dir = Path(default) if os.path.isabs(default) else None
        if state_dir is not None:
            _log(state_dir, f"run failed: {type(e).__name__}: {_one_line(str(e))}")
    return 0


def _add_supervise(sub) -> None:
    sub.add_parser("supervise", help="one supervisor short run for the open triggers (started by run)")


def _run_supervise(args) -> int:
    state_dir = None
    try:
        cfg = load_server_config()
        state_dir = Path(cfg.state_dir)
        if not (cfg.enabled and cfg.supervisor):
            _log(state_dir, "supervise: server or supervisor mode disabled")
            return 0
        result = supervisor.run_once(cfg, state_dir, effects.now())
        _log(state_dir, f"supervise: {result}")
        return 1 if result in ("failed", "timeout") else 0
    except Exception as e:
        if state_dir is not None:
            _log(state_dir, f"supervise failed: {type(e).__name__}: {_one_line(str(e))}")
            try:
                items = projects.load(state_dir)
                target = next((p.name for p in items if p.supervisor), None)
                if target:
                    events.append(state_dir, target, {"kind": "notice", "strand": "supervisor", "level": "warning",
                                                      "title": "supervisor run failed",
                                                      "text": "The supervisor run stopped on an unexpected error; see run.log."})
            except Exception:
                pass
        return 1


def _add_wake(sub) -> None:
    p = sub.add_parser("wake", help="wake markers")
    ws = p.add_subparsers(dest="wake_command", required=True)
    ws.add_parser("fast-forward", help="set all wake markers to now; afterwards only new things wake")


def _run_wake(args) -> int:
    try:
        cfg = load_server_config()
        wake.fast_forward(cfg, projects.load(cfg.state_dir), Path(cfg.state_dir), effects.now())
    except (OSError, ValueError) as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 1
    return 0


# ---- launch and deliver -----------------------------------------------------

def _project(name: str, state_dir: Path):
    for p in projects.load(state_dir):
        if p.name == name:
            return p
    print(f"sf-status: project {name!r} is not registered (sf-status project add)", file=sys.stderr)
    return None


def _add_launch(sub) -> None:
    p = sub.add_parser("launch", help="start a strand in tmux from its start file")
    p.add_argument("--project", required=True)
    p.add_argument("--short", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--worktree", required=True)
    p.add_argument("--topic", required=True)


def _run_launch(args) -> int:
    cfg = _config()
    if cfg is None:
        return 1
    project = _project(args.project, Path(cfg.state_dir))
    if project is None:
        return 1
    return launch.launch(cfg, project, args.short, args.model,
                         Path(os.path.realpath(os.path.expanduser(args.worktree))), args.topic)


def _add_deliver(sub) -> None:
    p = sub.add_parser("deliver", help="append a follow-up to the start file and point the strand to it")
    _common(p)
    p.add_argument("text", help="follow-up text; '-' reads it from stdin")


def _run_deliver(args) -> int:
    cfg = _config()
    if cfg is None:
        return 1
    project = _project(args.project, Path(cfg.state_dir))
    if project is None:
        return 1
    text = sys.stdin.read().rstrip("\n") if args.text == "-" else args.text
    return launch.deliver(cfg, project, args.strand, text)


def _add_local(sub) -> None:
    p = sub.add_parser("local", help="request or report steps that run on the laptop")
    ls = p.add_subparsers(dest="local_command", required=True)
    r = ls.add_parser("request", help="ask for a local step; prints the request id")
    _common(r)
    r.add_argument("--step", required=True)
    r.add_argument("--branch", required=True)
    r.add_argument("--commit", required=True)
    r.add_argument("--note")
    pe = ls.add_parser("pending", help="print open local requests as JSON lines")
    _common(pe, strand_required=False)
    re_ = ls.add_parser("result", help="record the result of a local step")
    _common(re_, strand_required=False)
    re_.add_argument("--id", required=True)
    re_.add_argument("--state", required=True, choices=events.LOCAL_STATES)
    re_.add_argument("text", help="result text; '-' reads it from stdin")


def _local_history(args) -> tuple[ServerConfig, list[dict]] | int:
    cfg = _config()
    if cfg is None:
        return 1
    if not _registered(cfg.state_dir, args.project):
        return 1
    try:
        history, _ = events.read(cfg.state_dir, args.project)
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    return cfg, history


def _run_local(args) -> int:
    got = _local_history(args)
    if isinstance(got, int):
        return got
    cfg, history = got
    open_requests = events.open_local(history)
    if args.local_command == "pending":
        for e in open_requests.values():
            row = {k: e[k] for k in ("id", "strand", "step", "branch", "commit", "time") if k in e}
            if e.get("note"):
                row["note"] = e["note"]
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if args.local_command == "result":
        request = open_requests.get(args.id)
        if request is None:
            print(f"sf-status: no open local request {args.id!r} in project {args.project!r}",
                  file=sys.stderr)
            return 1
        text = sys.stdin.read().rstrip("\n") if args.text == "-" else args.text
        ev = {"kind": "local_result", "strand": request["strand"], "request_id": args.id,
              "state": args.state, "text": text}
        return _finish(_emit(args, ev, reserved_check=False))
    mine = [e for e in open_requests.values() if e.get("strand") == args.strand]
    if mine:
        print(f"sf-status: strand {args.strand!r} already has an open local request {mine[0]['id']!r}",
              file=sys.stderr)
        return 1
    ev = {"kind": "local_request", "strand": args.strand, "id": events.next_local_id(history, args.strand),
          "step": args.step, "branch": args.branch, "commit": args.commit}
    if args.note:
        ev["note"] = args.note
    try:
        events._validate(args.project, {**ev, "time": "1970-01-01T00:00:00Z"})
    except ValueError as e:
        print(f"sf-status: {e}", file=sys.stderr)
        return 2
    project = _project(args.project, cfg.state_dir)
    head = effects.git_remote_head(Path(project.folder), args.branch) if project else None
    if not head or not head.startswith(args.commit):
        print(f"sf-status: commit {args.commit!r} is not the head of origin/{args.branch}; "
              "push it first", file=sys.stderr)
        return 1
    result = _emit(args, ev)
    if isinstance(result, int):
        return result
    print(ev["id"])
    return 0


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
    "dismiss": (_add_dismiss, _run_dismiss),
    "attention": (_add_attention, _run_attention),
    "backport": (_add_backport, _run_backport),
    "tickets": (_add_tickets, _run_tickets),
    "project": (_add_project, _run_project),
    "train": (_add_train, _run_train),
    "run": (_add_run, _run_run),
    "wake": (_add_wake, _run_wake),
    "supervise": (_add_supervise, _run_supervise),
    "launch": (_add_launch, _run_launch),
    "deliver": (_add_deliver, _run_deliver),
    "local": (_add_local, _run_local),
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
