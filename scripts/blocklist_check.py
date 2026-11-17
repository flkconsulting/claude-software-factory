#!/usr/bin/env python3
"""Check files against a private blocklist without ever printing the terms.

Usage: blocklist_check.py [--all | --history <rev-args...> | <files...>]
--history scans commit messages, author and committer names and e-mails, file
names and full patches (including removed lines) of the given git revisions,
for example "--history origin/main..HEAD" or "--history --all".
Terms come from $SF_BLOCKLIST_FILE (default: .blocklist), one per line,
'#' starts a comment. Matching is a case-insensitive substring test.
Exit codes: 0 clean, 1 hit, 2 blocklist missing or empty.
"""
import os
import subprocess
import sys
from pathlib import Path

BLOCKLIST_NAME = ".blocklist"


def load_terms(path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return None
    terms = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line.lower())
    return terms or None


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    names = [n for n in out.decode("utf-8", "surrogateescape").split("\0") if n]
    return [n for n in names if Path(n).name != BLOCKLIST_NAME]


def scan(path, terms):
    """Return (line, term_index) hits for one file, or None if unreadable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return []
    hits = []
    text = data.decode("utf-8", "replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        for idx, term in enumerate(terms, start=1):
            if term in low:
                hits.append((lineno, idx))
    return hits


def scan_history(revs, terms):
    """Scan git log output for revs. Return hits as (label, term_index), or None."""
    fmt = "%x01%h%n%an <%ae>%n%cn <%ce>%n%B"
    try:
        out = subprocess.run(
            ["git", "log", "-p", "--cc", "-M", "--no-color", "--format=" + fmt, *revs, "--"],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    hits = []
    commit = "?"
    area = "meta"
    for line in out.decode("utf-8", "replace").splitlines():
        if line.startswith("\x01"):
            commit = line[1:]
            area = "meta"
            continue
        if line.startswith("diff --git "):
            area = "diff"
        low = line.lower()
        for idx, term in enumerate(terms, start=1):
            if term in low:
                hits.append((f"commit {commit} ({area})", idx))
    return hits


def main(argv):
    terms = load_terms(os.environ.get("SF_BLOCKLIST_FILE", BLOCKLIST_NAME))
    if terms is None:
        print("blocklist missing or empty", file=sys.stderr)
        return 2
    if argv and argv[0] == "--history":
        if len(argv) < 2:
            print("usage: blocklist_check.py --history <rev-args...>", file=sys.stderr)
            return 2
        hits = scan_history(argv[1:], terms)
        if hits is None:
            print("cannot read git history", file=sys.stderr)
            return 2
        for label, idx in hits:
            print(f"{label}: blocklist hit (term #{idx})")
        return 1 if hits else 0
    if not argv or (argv != ["--all"] and any(a.startswith("-") for a in argv)):
        print("usage: blocklist_check.py [--all | --history <rev-args...> | <files...>]", file=sys.stderr)
        return 2
    explicit = argv != ["--all"]
    if argv == ["--all"]:
        try:
            files = tracked_files()
        except (OSError, subprocess.CalledProcessError):
            print("cannot list tracked files", file=sys.stderr)
            return 2
    else:
        files = argv
    found = False
    unreadable = False
    for f in files:
        hits = scan(f, terms)
        if hits is None:
            if explicit:
                print(f"cannot read {f}", file=sys.stderr)
                unreadable = True
            continue  # tracked but deleted in --all mode
        for lineno, idx in hits:
            print(f"{f}:{lineno}: blocklist hit (term #{idx})")
            found = True
    if unreadable:
        return 2
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
