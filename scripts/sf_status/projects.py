"""Project registry: <state>/projects.json, registration rules, path lookup."""
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import events

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SYSTEM_STRAND = "server"  # strand id used for registry events


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
    if not isinstance(p.never_touch, list):
        raise ValueError("never_touch must be a list")
    return p


def load(state_dir: Path) -> list[Project]:
    """All registered projects; a missing file is empty, a broken one is empty plus a log line."""
    try:
        raw = _file(state_dir).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as e:
        _log(state_dir, f"projects.json unreadable: {e}")
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
            raise ValueError('top level must be {"projects": [...]}')
        return [_from_dict(d) for d in data["projects"]]
    except (ValueError, TypeError) as e:
        _log(state_dir, f"projects.json invalid, treated as empty: {e}")
        return []


def _save(state_dir: Path, items: list[Project]) -> None:
    target = _file(state_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"projects": [asdict(p) for p in items]}, ensure_ascii=False,
                              indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def _hooks_dir(folder: Path) -> Path:
    try:
        out = subprocess.run(["git", "-C", str(folder), "config", "--get", "core.hooksPath"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
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


def check(project: Project, existing: list[Project]) -> None:
    if not NAME_RE.match(project.name):
        raise ProjectError("name: only a-z, 0-9 and single hyphens (not at the start or end)")
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
    if not has_gitleaks_pre_push(folder):
        raise ProjectError("the repository has no executable pre-push hook containing gitleaks "
                           "(core.hooksPath or .git/hooks); install scripts/git-hooks/pre-push "
                           "from the plugin and enable it first")


def add(state_dir: Path, project: Project) -> None:
    items = load(state_dir)
    check(project, items)
    _save(state_dir, items + [project])
    events.append(state_dir, project.name, {"kind": "project_added", "strand": SYSTEM_STRAND})


def remove(state_dir: Path, name: str) -> None:
    items = load(state_dir)
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
