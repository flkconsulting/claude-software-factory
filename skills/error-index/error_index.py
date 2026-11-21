#!/usr/bin/env python3
"""Searchable JSONL index of solved error causes (stdlib only, Python >= 3.10).

Usage:
  error_index.py add --symptom S --cause C --fix F --ref R [--date YYYY-MM-DD] [--file PATH]
  error_index.py search TERM [TERM...] [--file PATH]

Path: --file, else $SF_ERROR_INDEX, else planning/ERRORS.jsonl.
Exit codes: 0 ok / hit, 1 no hit, 2 input error (including sensitive content).

Privacy: the index must never contain secrets, tokens, credentials, names or
personal data. Recognizable cases are rejected; error messages name only the
matching pattern, never the text itself. This does not replace judgment.
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

FIELDS = ("date", "symptom", "cause", "fix", "ref")
MAX_SYMPTOM = 200
DEFAULT_PATH = "planning/ERRORS.jsonl"

PATTERNS = {
    "bearer": re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I),
    "credential-assignment": re.compile(
        r"(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+", re.I
    ),
    "url-credentials": re.compile(r"://[^\s/:@]+:[^\s/@]+@"),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "email": re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}
LONG_RUN = re.compile(r"[A-Za-z0-9+_=-]{32,}")
COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")


def find_sensitive(text: str) -> list[str]:
    hits = [name for name, rx in PATTERNS.items() if rx.search(text)]
    # A token-like run mixes letters and digits; plain identifiers and paths pass.
    if any(
        re.search(r"\d", run) and re.search(r"[A-Za-z]", run)
        for run in LONG_RUN.findall(text)
    ):
        hits.append("long-token")
    return hits


def shorten(text: str, limit: int = MAX_SYMPTOM) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def append_entry(path: Path, entry: dict) -> None:
    for field in FIELDS:
        if not str(entry.get(field, "")).strip():
            raise ValueError(f"field '{field}' must not be empty")
    for field in FIELDS:
        value = str(entry[field])
        hits = find_sensitive(value)
        if field == "ref" and COMMIT_SHA.fullmatch(value):
            hits = [h for h in hits if h != "long-token"]
        if hits:
            raise ValueError(
                f"field '{field}' looks sensitive (pattern: {', '.join(hits)}); "
                "rephrase without secrets, tokens, names or personal data"
            )
    line = json.dumps({f: entry[f] for f in FIELDS}, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.is_file() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            fh.seek(-1, os.SEEK_END)
            needs_newline = fh.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as fh:
        if needs_newline:
            fh.write("\n")
        fh.write(line + "\n")


def search(path: Path, terms: list[str]) -> list[dict]:
    if not path.is_file():
        return []
    wanted = [t.lower() for t in terms]
    hits = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for number, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                print(f"skipping unreadable line {number}", file=sys.stderr)
                continue
            if all(t in raw.lower() for t in wanted):
                hits.append(entry)
    return hits


class _QuietParser(argparse.ArgumentParser):
    """Argument parser whose errors never echo the offending argument values."""

    def error(self, message):
        print(f"error: invalid arguments; see usage in {self.prog} --help", file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str]) -> int:
    parser = _QuietParser(prog="error_index.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    for name in ("symptom", "cause", "fix", "ref"):
        add.add_argument(f"--{name}", required=True)
    add.add_argument("--date", default=None)
    add.add_argument("--file", default=None)
    find = sub.add_parser("search")
    find.add_argument("terms", nargs="+")
    find.add_argument("--file", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    path = Path(args.file or os.environ.get("SF_ERROR_INDEX") or DEFAULT_PATH)
    try:
        if args.command == "add":
            day = args.date or date.today().isoformat()
            try:
                canonical = date.fromisoformat(day).isoformat()
            except ValueError:
                canonical = None
            if canonical != day:
                print("error: --date must be YYYY-MM-DD", file=sys.stderr)
                return 2
            raw_hits = find_sensitive(args.symptom)
            if raw_hits:
                raise ValueError(
                    f"field 'symptom' looks sensitive (pattern: {', '.join(raw_hits)}); "
                    "rephrase without secrets, tokens, names or personal data"
                )
            append_entry(
                path,
                {
                    "date": day,
                    "symptom": shorten(args.symptom),
                    "cause": args.cause,
                    "fix": args.fix,
                    "ref": args.ref,
                },
            )
            return 0
        hits = search(path, args.terms)
        for hit in hits:
            print(json.dumps(hit, ensure_ascii=False))
        return 0 if hits else 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot access {path}: {exc.strerror}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
