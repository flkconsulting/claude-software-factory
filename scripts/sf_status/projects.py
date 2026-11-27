"""Project registry: <state>/projects.json, registration rules, path lookup."""
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import effects, events

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# state keys of markers/wake.json that a valid project name could equal (see wake.STATE_KEYS)
RESERVED_NAMES = ("rows", "seen")
SYSTEM_STRAND = "server"  # strand id used for registry events
TRAIN_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TRAIN_KEYS = ("train", "train_day", "train_time", "train_tz", "train_skip")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ProjectError(Exception):
    pass


@dataclass
class Project:
    name: str
    title: str
    folder: str
    main_branch: str = "main"
    supervisor: bool = False
    approval_quote: str | None = None
    wave_plan: str = "planning/wave-plan.md"
    never_touch: list[str] = field(default_factory=list)
    train: bool = False
    train_day: str = "tue"
    train_time: str = "18:00"
    train_tz: str = "Europe/Berlin"
    train_skip: list[str] = field(default_factory=list)


def _file(state_dir: Path) -> Path:
    return Path(state_dir) / "projects.json"


def _log(state_dir: Path, line: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(Path(state_dir) / "run.log", "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except OSError:
        pass


def _from_dict(d: dict) -> Project:
    if not isinstance(d, dict) or not events.valid_id(d.get("name")) or not isinstance(d.get("folder"), str):
        raise ValueError("every entry needs a valid name and a folder")
    known = Project.__dataclass_fields__
    p = Project(**{k: v for k, v in d.items() if k in known})
    if not isinstance(p.supervisor, bool):
        raise ValueError("supervisor must be true or false")
    if not isinstance(p.train, bool):
        raise ValueError("train must be true or false")
    for key in ("title", "main_branch", "wave_plan", "train_day", "train_time", "train_tz"):
        if not isinstance(getattr(p, key), str):
            raise ValueError(f"{key} must be a string")
    if not isinstance(p.never_touch, list):
        raise ValueError("never_touch must be a list")
    if not isinstance(p.train_skip, list) or not all(isinstance(x, str) for x in p.train_skip):
        raise ValueError("train_skip must be a list of strings")
    return p


def _read(state_dir: Path) -> tuple[list[Project], str | None]:
    """(projects, problem): problem is None when the file is fine or missing."""
    try:
        raw = _file(state_dir).read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], None
    except (OSError, ValueError) as e:  # ValueError covers UnicodeDecodeError
        return [], str(e)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
            raise ValueError('top level must be {"projects": [...]}')
        items = [_from_dict(d) for d in data["projects"]]
    except (ValueError, TypeError) as e:
        return [], str(e)
    seen: set[str] = set()
    for p in items:
        if p.name in seen:
            return [], f"duplicate project name {p.name}"
        seen.add(p.name)
    return items, None


def load(state_dir: Path) -> list[Project]:
    """All registered projects; a missing file is empty, a broken one is empty plus a log line."""
    items, problem = _read(state_dir)
    if problem:
        _log(state_dir, f"projects.json unreadable, treated as empty: {problem}")
    return items


def load_strict(state_dir: Path) -> list[Project]:
    """Like load, but a file that exists and is broken raises ProjectError (for add/remove/list)."""
    items, problem = _read(state_dir)
    if problem:
        raise ProjectError(f"projects.json unreadable: {problem}")
    return items


def _save(state_dir: Path, items: list[Project]) -> None:
    target = _file(state_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"projects": [asdict(p) for p in items]}, ensure_ascii=False,
                              indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def _hooks_dir(folder: Path) -> Path:
    out = effects.git_config(folder, "core.hooksPath")
    if out:
        p = Path(out).expanduser()
        return p if p.is_absolute() else Path(folder) / p
    return Path(folder) / ".git" / "hooks"


def has_gitleaks_pre_push(folder: Path) -> bool:
    hook = _hooks_dir(Path(folder)) / "pre-push"
    try:
        return hook.is_file() and os.access(hook, os.X_OK) and "gitleaks" in hook.read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


def check_train(p: Project) -> None:
    if p.train_day not in TRAIN_DAYS:
        raise ProjectError(f"train day must be one of {', '.join(TRAIN_DAYS)}")
    if not TIME_RE.match(p.train_time):
        raise ProjectError("train time must be HH:MM from 00:00 to 23:59")
    try:
        ZoneInfo(p.train_tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ProjectError(f"train time zone {p.train_tz!r} is unknown (or the system has no time zone data; "
                           "install tzdata)") from None
    for d in p.train_skip:
        try:
            if not DATE_RE.match(d):
                raise ValueError(d)
            date.fromisoformat(d)
        except ValueError:
            raise ProjectError(f"train skip date {d!r} must be a valid date YYYY-MM-DD") from None
    if p.train and not p.supervisor:
        raise ProjectError("train on needs supervisor yes (the supervisor asks the train question)")


def check(project: Project, existing: list[Project]) -> None:
    if not NAME_RE.match(project.name):
        raise ProjectError("name: only a-z, 0-9 and single hyphens (not at the start or end)")
    if project.name in RESERVED_NAMES:
        raise ProjectError(f"name {project.name!r} is reserved (it would collide with a state key of the wake marker)")
    if any(p.name == project.name for p in existing):
        raise ProjectError(f"project {project.name!r} is already registered")
    if not project.title.strip():
        raise ProjectError("title must not be empty")
    folder = Path(project.folder)
    if not folder.is_absolute() or ".." in folder.parts:
        raise ProjectError("folder must be an absolute path without '..'")
    if not folder.is_dir():
        raise ProjectError(f"folder {project.folder} does not exist")
    for p in existing:
        if Path(p.folder) == folder:
            raise ProjectError(f"folder already belongs to project {p.name!r}")
    if not (folder / ".git").exists():
        raise ProjectError(f"folder {project.folder} is not a git repository")
    if project.supervisor and not (project.approval_quote or "").strip():
        raise ProjectError("supervisor yes needs the human approval quoted verbatim (--approval-quote)")
    check_train(project)
    if not has_gitleaks_pre_push(folder):
        raise ProjectError("the repository has no executable pre-push hook containing gitleaks "
                           "(core.hooksPath or .git/hooks); install scripts/git-hooks/pre-push "
                           "from the plugin and enable it first")


def add(state_dir: Path, project: Project) -> None:
    items = load_strict(state_dir)
    check(project, items)
    _save(state_dir, items + [project])
    events.append(state_dir, project.name, {"kind": "project_added", "strand": SYSTEM_STRAND})


def update(state_dir: Path, name: str, changes: dict) -> Project:
    """Change the train settings of a registered project."""
    items = load_strict(state_dir)
    old = next((p for p in items if p.name == name), None)
    if old is None:
        raise ProjectError(f"project {name!r} is not registered")
    extra = set(changes) - set(TRAIN_KEYS)
    if extra:
        raise ProjectError(f"cannot change {', '.join(sorted(extra))}")
    new = replace(old, **changes)
    check_train(new)
    _save(state_dir, [new if p.name == name else p for p in items])
    return new


def remove(state_dir: Path, name: str) -> None:
    items = load_strict(state_dir)
    if name not in [p.name for p in items]:
        raise ProjectError(f"project {name!r} is not registered")
    events.append(state_dir, name, {"kind": "project_removed", "strand": SYSTEM_STRAND})
    _save(state_dir, [p for p in items if p.name != name])


def project_for_path(items: list[Project], path: Path) -> str | None:
    """Project whose folder equals path, contains it, or is a worktree prefix 'folder-'."""
    target = str(path).rstrip("/")
    best: tuple[int, str] | None = None
    for p in items:
        folder = p.folder.rstrip("/")
        if target == folder or target.startswith(folder + "/") or target.startswith(folder + "-"):
            if best is None or len(folder) > best[0]:
                best = (len(folder), p.name)
    return best[1] if best else None
