"""Wave plan parser: a markdown table with one row per planned strand.

Columns: short | strand | approval | starts when | branch | base | migrations | may change | tickets
Cells are read by the names in the header row, so plans without the `base` column keep working.
The optional `tickets` cell is free text for the human and not part of row_hash (a function of the row text only).
Without a header row the columns are taken in the order above, without `base`.
"""
import hashlib
import re
from dataclasses import dataclass

_SEPARATOR = re.compile(r"^:?-{1,}:?$")
_DEFAULT = ("short", "strand", "approval", "starts when", "branch", "migrations", "may change")


@dataclass(frozen=True)
class WaveRow:
    short: str
    strand: str
    approved: bool
    starts_when: str
    branch: str
    row_hash: str
    base: str = ""  # branch the worktree starts from; empty means the main branch
    tickets: str = ""  # optional cell: ticket numbers the strand works on


def parse_wave_plan(text: str) -> list[WaveRow]:
    rows = []
    columns = {name: i for i, name in enumerate(_DEFAULT)}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3 or all(_SEPARATOR.match(c) or not c for c in cells):
            continue
        if cells[0].lower() == "short":
            columns = {c.lower(): i for i, c in enumerate(cells)}
            continue
        if not cells[0]:
            continue

        def cell(name: str) -> str:
            i = columns.get(name)
            return cells[i] if i is not None and i < len(cells) else ""

        rows.append(WaveRow(
            short=cell("short"),
            strand=cell("strand"),
            approved=cell("approval").lower().startswith("yes"),
            starts_when=cell("starts when"),
            branch=cell("branch"),
            row_hash=hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:12],
            base=cell("base"),
            tickets=cell("tickets"),
        ))
    return rows
