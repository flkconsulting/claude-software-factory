"""Tolerant readers for planning/TICKETS.md and planning/RELEASES.md.

Both files hold markdown tables. Cells are read by the names in the header row (lower case),
unknown columns and surplus cells are ignored, separator rows, blank lines and HTML comments
are skipped, a BOM and CRLF line ends are tolerated. A reader never raises on file content:
it returns what it could read plus the names of the required columns that are missing.
RELEASES.md holds two tables, told apart by the headings `## Versions` and `## Deliveries`.
"""
import re
from dataclasses import dataclass, field, fields
from pathlib import Path

from .projects import Project

_SEPARATOR = re.compile(r"^:?-{1,}:?$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^\s*#{1,2}(?!#)\s*(.*)$")

TICKET_REQUIRED = ("nr", "since", "kind", "rank", "state", "version")
VERSION_REQUIRED = ("version", "line", "state")
DELIVERY_REQUIRED = ("customer", "version")


@dataclass(frozen=True)
class Ticket:
    nr: str = ""
    since: str = ""
    kind: str = ""
    rank: str = ""
    effort: str = ""
    state: str = ""
    version: str = ""
    source: str = ""
    summary: str = ""


@dataclass(frozen=True)
class Version:
    version: str = ""
    line: str = ""
    state: str = ""
    train: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Delivery:
    customer: str = ""
    version: str = ""
    planned: str = ""
    done: str = ""
    notes: str = ""


@dataclass(frozen=True)
class TicketTable:
    rows: list[Ticket] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Releases:
    versions: list[Version] = field(default_factory=list)
    deliveries: list[Delivery] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _lines(text: str) -> list[str]:
    return _COMMENT.sub("", text.lstrip("\ufeff")).splitlines()


def _table(lines: list[str], key: str = "nr") -> tuple[list[str] | None, list[list[str]]]:
    """(header, rows): header is the lower-cased cells of the first row whose cell 0 is `key`."""
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(_SEPARATOR.match(c) or not c for c in cells):
            continue
        if header is None:
            if cells[0].lower() == key:
                header = [c.lower() for c in cells]
            continue
        rows.append(cells)
    return header, rows


def _build(cls, header: list[str] | None, rows: list[list[str]]) -> list:
    if header is None:
        return []
    index = {}
    for i, name in enumerate(header):
        index.setdefault(name, i)
    names = [f.name for f in fields(cls)]
    out = []
    for cells in rows:
        out.append(cls(**{n: cells[index[n]] if n in index and index[n] < len(cells) else ""
                          for n in names}))
    return out


def _missing(header: list[str] | None, required: tuple[str, ...], prefix: str = "") -> list[str]:
    return [prefix + r for r in required if header is None or r not in header]


def parse_tickets(text: str) -> TicketTable:
    header, rows = _table(_lines(text), "nr")
    return TicketTable(_build(Ticket, header, rows), _missing(header, TICKET_REQUIRED))


def parse_releases(text: str) -> Releases:
    sections: dict[str, list[str]] = {"versions": [], "deliveries": []}
    current = None
    for line in _lines(text):
        m = _HEADING.match(line)
        if m:  # only level 1 and 2 headings switch sections; deeper ones belong to the section
            current = m.group(1).strip().lower()
            continue
        if current in sections:
            sections[current].append(line)
    vh, vrows = _table(sections["versions"], "version")
    dh, drows = _table(sections["deliveries"], "customer")
    return Releases(
        _build(Version, vh, vrows),
        _build(Delivery, dh, drows),
        _missing(vh, VERSION_REQUIRED, "versions.") + _missing(dh, DELIVERY_REQUIRED, "deliveries."),
    )


def planning_dir(project: Project) -> Path:
    return (Path(project.folder) / project.wave_plan).parent


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_tickets(project: Project) -> TicketTable | None:
    text = _read(planning_dir(project) / "TICKETS.md")
    return None if text is None else parse_tickets(text)


def load_releases(project: Project) -> Releases | None:
    text = _read(planning_dir(project) / "RELEASES.md")
    return None if text is None else parse_releases(text)


_RANK_ORDER = {"critical": 0, "high": 1, "normal": 2}
_CLOSED = ("shipped", "rejected", "deferred")
_IN_VERSION = ("planned", "in-progress", "in-train")
_NUMBER = re.compile(r"^T-(\d+)$")


def _order(items: list[Ticket], rank: bool = False) -> list[Ticket]:
    """Numeric by the number after T-; invalid numbers last in file order (sort is stable)."""
    def key(t: Ticket):
        m = _NUMBER.match(t.nr)
        return ((_RANK_ORDER.get(t.rank.lower(), len(_RANK_ORDER)) if rank else 0),
                0 if m else 1, int(m.group(1)) if m else 0)
    return sorted(items, key=key)


def overview(project: str, table: TicketTable, releases: Releases | None) -> dict:
    """Board and CLI summary of one project's tickets: open bugs, next versions, new tickets."""
    state = lambda t: t.state.lower()  # noqa: E731
    bugs = [t for t in table.rows if t.kind.lower() == "bug" and state(t) not in _CLOSED]
    new = [t for t in table.rows if state(t) == "new"]
    nxt = []
    for v in (releases.versions if releases is not None else []):
        if v.state.lower() in ("planned", "testing"):
            tickets = [t for t in table.rows if t.version == v.version and state(t) in _IN_VERSION]
            nxt.append({"version": v.version, "line": v.line, "state": v.state,
                        "tickets": [t.nr for t in _order(tickets)]})
    return {
        "project": project,
        "bugs": [{"nr": t.nr, "rank": t.rank, "state": t.state, "version": t.version, "summary": t.summary}
                 for t in _order(bugs, rank=True)],
        "next": nxt,
        "new": [{"nr": t.nr, "kind": t.kind, "rank": t.rank, "summary": t.summary}
                for t in _order([t for t in new if t.kind.lower() == "bug"], rank=True)
                + _order([t for t in new if t.kind.lower() != "bug"], rank=True)],
    }
