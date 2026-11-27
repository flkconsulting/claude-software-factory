"""Pure checks on the TICKETS.md / RELEASES.md tables and the board notices for their findings.

Findings carry fixed words, ticket numbers and versions only, never free text from the tables
(summary, source, notes). `emit_once` writes one notice per project, ticket and finding code.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import effects, events
from .planning import Releases, TicketTable, Version
from .projects import SYSTEM_STRAND, Project

MARKER = "tickets.json"
KINDS = ("bug", "feature")
RANKS = {"bug": ("critical", "high", "normal"), "feature": ("high", "normal", "low")}
EFFORTS = ("S", "M", "L", "")
TICKET_STATES = ("new", "assessed", "planned", "in-progress", "in-train", "shipped", "deferred", "rejected")
NEEDS_VERSION = ("planned", "in-progress", "in-train", "shipped")
UNPLANNED = ("new", "assessed")
VERSION_STATES = ("planned", "testing", "accepted", "released")
WARNING_CODES = ("critical-unplanned", "backport-missing")
_NR = re.compile(r"^T-\d+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

TEXTS = {
    "number-invalid": "ticket number is not of the form T-<number>",
    "number-duplicate": "ticket number is used by more than one row",
    "kind-unknown": "kind is not bug or feature",
    "rank-unknown": "rank is not valid for this kind",
    "effort-unknown": "effort is not S, M or L",
    "state-unknown": "state is not a known ticket state",
    "since-invalid": "since is not a date of the form YYYY-MM-DD",
    "version-missing": "version is empty although the state needs one",
    "version-test-suffix": "version is a test build, use the release version",
    "version-unknown": "version is not listed in RELEASES.md",
    "critical-unplanned": "critical bug is still not planned after the configured hours",
    "line-missing": "line is empty",
    "version-duplicate": "version is listed more than once",
    "delivery-version-unknown": "delivery names a version that is not listed",
    "delivery-version-unreleased": "delivery names a version that is not released yet",
    "backport-missing": "release branch lacks commits of its line",
}


@dataclass(frozen=True)
class Finding:
    key: str
    code: str
    level: str
    title: str
    text: str


def _finding(kind: str, ident: str, code: str, source: str) -> Finding:
    text = TEXTS.get(code)
    if text is None:  # column-missing-<name>
        text = "required column is missing"
    # release keys get a prefix so they never meet a ticket key (both have state-unknown, row<n>)
    key_id = "release-" + ident if kind == "release" and ident != "releases-file" else ident
    return Finding(f"{key_id}/{code}", code, "warning" if code in WARNING_CODES else "info",
                   f"{kind} {ident}: {code}", f"{kind} {ident}: {text}. See {source}.")


def _unique(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    out = []
    for f in findings:
        if f.key not in seen:
            seen.add(f.key)
            out.append(f)
    return out


def _since(value: str) -> datetime | None:
    if not _DATE.match(value):
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def ticket_findings(table: TicketTable, releases: Releases | None, now: datetime,
                    critical_hours: int) -> list[Finding]:
    """Findings of a ticket table; keys are "<id>/<code>" (the project is added by emit_once)."""
    src = "planning/TICKETS.md"
    out = [_finding("ticket", "tickets-file", f"column-missing-{c}", src) for c in table.missing]
    has = lambda c: c not in table.missing  # noqa: E731
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    known = None
    if releases is not None and "versions.version" not in releases.missing:
        known = {v.version for v in releases.versions}
    seen: set[str] = set()
    for n, t in enumerate(table.rows, 1):
        valid_nr = has("nr") and bool(_NR.match(t.nr))
        ident = t.nr if valid_nr else f"row{n}"

        def add(code: str) -> None:
            out.append(_finding("ticket", ident, code, src))
        if has("nr"):
            if not valid_nr:
                add("number-invalid")
            elif t.nr in seen:
                add("number-duplicate")
            seen.add(t.nr)
        if has("kind") and t.kind not in KINDS:
            add("kind-unknown")
        if has("kind") and has("rank") and t.kind in KINDS and t.rank not in RANKS[t.kind]:
            add("rank-unknown")
        if t.effort not in EFFORTS:
            add("effort-unknown")
        if has("state") and t.state not in TICKET_STATES:
            add("state-unknown")
        since = _since(t.since) if has("since") else None
        if has("since") and since is None:
            add("since-invalid")
        if has("state") and has("version"):
            if t.state in NEEDS_VERSION and not t.version:
                add("version-missing")
        if has("version") and t.version:
            if "-test." in t.version:
                add("version-test-suffix")
            if known is not None and t.version not in known:
                add("version-unknown")
        if (since is not None and has("kind") and has("rank") and has("state")
                and t.kind == "bug" and t.rank == "critical" and t.state in UNPLANNED
                and now - since >= timedelta(hours=critical_hours)):
            add("critical-unplanned")
    return _unique(out)


def _safe(value: str, fallback: str) -> str:
    return value if _SAFE.match(value) else fallback


def release_findings(releases: Releases) -> list[Finding]:
    """Findings of RELEASES.md; keys are "release-<version>/<code>"."""
    src = "planning/RELEASES.md"
    out = [_finding("release", "releases-file", f"column-missing-{c}", src) for c in releases.missing]
    has = lambda c: c not in releases.missing  # noqa: E731
    seen: set[str] = set()
    for n, v in enumerate(releases.versions, 1):
        ident = _safe(v.version, f"row{n}") if has("versions.version") else f"row{n}"

        def add(code: str) -> None:
            out.append(_finding("release", ident, code, src))
        if has("versions.line") and not v.line:
            add("line-missing")
        if has("versions.state") and v.state not in VERSION_STATES:
            add("state-unknown")
        if has("versions.version"):
            if v.version in seen:
                add("version-duplicate")
            seen.add(v.version)
    if has("deliveries.version") and has("versions.version"):
        state = {v.version: v.state for v in releases.versions}
        for n, d in enumerate(releases.deliveries, 1):
            ident = _safe(d.version, f"delivery{n}")
            if d.version not in state:
                out.append(_finding("release", ident, "delivery-version-unknown", src))
            elif has("versions.state") and state[d.version] != "released":
                out.append(_finding("release", ident, "delivery-version-unreleased", src))
    return _unique(out)


def missing_backports(folder: Path, version: Version) -> list[str] | None:
    """Commits of release/<version> that are not on its line; None if not checkable.

    Values that fail validation never reach git. The version state is ignored."""
    if not _VERSION.fullmatch(version.version) or not events.BRANCH_RE.fullmatch(version.line):
        return None
    return effects.git_cherry(folder, version.line, f"release/{version.version}")


def backport_findings(project: Project, releases: Releases) -> tuple[list[Finding], tuple[str, ...]]:
    """Missing backports of versions in testing or accepted, one finding per commit.

    The second part lists the marker prefixes of versions that could not be checked, so that
    emit_once keeps their earlier keys (no repeated notice when the branch comes back)."""
    out: list[Finding] = []
    keep: list[str] = []
    if "versions.version" in releases.missing:
        return out, ()
    for v in releases.versions:
        if v.state not in ("testing", "accepted"):
            continue
        commits = missing_backports(Path(project.folder), v)
        if commits is None:
            keep.append(f"{project.name}/backport-{v.version}/")
            continue
        for sha in commits:
            short = sha[:12]
            out.append(Finding(f"backport-{v.version}/{short}/missing", "backport-missing", "warning",
                               f"backport {v.version}: {short} missing",
                               f"backport {v.version}: {short} is on release/{v.version} but not on {v.line}. "
                               "See planning/RELEASES.md."))
    return _unique(out), tuple(keep)


def _load(path: Path) -> set[str]:
    noticed = events.load_json(path).get("noticed")
    return {x for x in noticed if isinstance(x, str)} if isinstance(noticed, list) else set()


def emit_once(state_dir: Path, per_project: dict[str, list[Finding]], when: datetime,
              keep_prefixes: tuple[str, ...] = ()) -> None:
    """One notice per new "<project>/<key>"; the marker keeps the open keys (and, for
    `keep_prefixes`, earlier ones) and is written after the events, only if it changes."""
    path = Path(state_dir) / "markers" / MARKER
    noticed = _load(path)
    current: dict[str, tuple[str, Finding]] = {}
    for project, findings in per_project.items():
        for f in findings:
            current.setdefault(f"{project}/{f.key}", (project, f))
    for key in sorted(current.keys() - noticed):
        project, f = current[key]
        events.append(state_dir, project, {"kind": "notice", "strand": SYSTEM_STRAND, "level": f.level,
                                           "title": f.title, "text": f.text}, when)
    kept = set(current) | {k for k in noticed if keep_prefixes and k.startswith(keep_prefixes)}
    if kept != noticed:
        events.save_json(path, {"noticed": sorted(kept)})
