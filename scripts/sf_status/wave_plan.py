"""Wave plan parser: a markdown table with one row per planned strand.

Columns: short | strand | approval | starts when | branch | migrations | may change
"""
import hashlib
import re
from dataclasses import dataclass

_SEPARATOR = re.compile(r"^:?-{1,}:?$")


@dataclass(frozen=True)
class WaveRow:
    short: str
    strand: str
    approved: bool
    starts_when: str
    branch: str
    row_hash: str


def parse_wave_plan(text: str) -> list[WaveRow]:
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3 or all(_SEPARATOR.match(c) or not c for c in cells):
            continue
        if cells[0].lower() == "short" or not cells[0]:
            continue
        cells += [""] * (5 - len(cells))
        rows.append(WaveRow(
            short=cells[0],
            strand=cells[1],
            approved=cells[2].lower().startswith("yes"),
            starts_when=cells[3],
            branch=cells[4],
            row_hash=hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:12],
        ))
    return rows
