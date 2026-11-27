"""Server settings from the "server" section of ~/.claude/software-factory.json."""
import json
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT_STATE_DIR = "~/.claude/software-factory/server"
SUPERVISOR_MODELS = ("haiku", "sonnet", "opus")


@dataclass(frozen=True)
class ServerConfig:
    enabled: bool = False
    supervisor: bool = False
    stall_minutes: int = 45
    supervisor_busy_minutes: int = 75
    supervisor_timeout_minutes: int = 30
    supervisor_model: str = "sonnet"
    heavy_slots: int = 2
    max_strands: int = 4
    safety_pass_hours: int = 3
    retry_limit: int = 3
    local_notice_hours: int = 8
    ticket_critical_hours: int = 24
    usage_report: bool = True
    auto_compact_window: int = 200000
    state_dir: Path = Path(DEFAULT_STATE_DIR)


def _expand(value: str, home: Path) -> Path | None:
    if value == "~" or value.startswith("~/"):
        return home / value[2:] if value != "~" else home
    p = Path(value)
    return p if p.is_absolute() else None


def _valid(name: str, value, default, home: Path):
    """Return the validated value or None if it is invalid."""
    if isinstance(default, bool):
        return value if isinstance(value, bool) else None
    if isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool) and value > 0
        return value if ok else None
    if name == "supervisor_model":
        return value if value in SUPERVISOR_MODELS else None
    if name == "state_dir":
        return _expand(value, home) if isinstance(value, str) and value else None
    return None


def load_server_config(home: Path | None = None) -> ServerConfig:
    if home is None:
        try:
            home = Path.home()
        except (RuntimeError, KeyError, OSError) as e:
            raise ValueError("cannot determine the home folder (HOME unset)") from e
    values: dict = {}
    section: dict = {}
    try:
        data = json.loads((home / ".claude" / "software-factory.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("server"), dict):
            section = data["server"]
    except (OSError, ValueError):
        pass
    defaults = ServerConfig()
    for f in fields(ServerConfig):
        default = getattr(defaults, f.name)
        if f.name == "state_dir":
            default = _expand(DEFAULT_STATE_DIR, home)
        value = _valid(f.name, section[f.name], default, home) if f.name in section else None
        values[f.name] = default if value is None else value
    return ServerConfig(**values)
