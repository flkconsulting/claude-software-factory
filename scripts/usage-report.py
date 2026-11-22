#!/usr/bin/env python3
"""Usage and model report for one UTC day: python3 usage-report.py [--day YYYY-MM-DD] [--json]."""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sf_status import projects as projects_mod, usage  # noqa: E402
from sf_status.config import load_server_config  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", help="UTC day YYYY-MM-DD (default: today)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", help="transcripts root (default ~/.claude/projects)")
    ap.add_argument("--state-dir", help="server state dir (default from settings)")
    args = ap.parse_args(argv)
    try:
        day = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
    except ValueError:
        print("invalid --day", file=sys.stderr)
        return 2
    state_dir = Path(args.state_dir) if args.state_dir else load_server_config().state_dir
    root = Path(args.root) if args.root else usage.DEFAULT_ROOT
    prices = usage.load_prices(Path(usage.__file__).parent / "prices.json")
    result = usage.summarize(root, day, prices, projects_mod.load(state_dir))
    print(json.dumps(result, sort_keys=True) if args.json else usage.format_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
