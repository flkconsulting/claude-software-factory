#!/usr/bin/env python3
"""UserPromptSubmit hook: warns when the session's context load gets large.

Load = input + cache-read + cache-creation tokens of the last transcript line
that carries usage data. Each threshold is reported once per session. In block
mode the first prompt after threshold 2 is held back once; threshold 1 is
always a notice only. A hook never ends with a traceback: any failure is
silent, exit 0.
"""
import json
import os
import re
import sys
from pathlib import Path

TAIL_BYTES = 3_000_000
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

HANDOVER = (
    "Write a handover (current state, open points, where the next session "
    "starts), then suggest starting a new session."
)


def last_load(path: str) -> int:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        lines = f.read().decode("utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            usage = (json.loads(line).get("message") or {}).get("usage") or {}
        except Exception:
            continue
        if isinstance(usage, dict) and usage:
            return sum(
                v for v in (usage.get(k) for k in USAGE_KEYS)
                if type(v) is int and v > 0
            )
    return 0


def main() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sf_config import load_config

        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        path = data.get("transcript_path")
        if not isinstance(path, str) or not path or not os.path.isfile(path):
            return 0
        cfg = load_config()
        load = last_load(path)
        stage = 2 if load >= cfg.thresholds[1] else 1 if load >= cfg.thresholds[0] else 0
        if stage == 0:
            return 0

        session = data.get("session_id")
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session) if isinstance(session, str) and session else "unknown"
        marker = cfg.state_dir / f"context-load-{safe_id}.txt"
        try:
            reported = int(marker.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            reported = 0
        if stage <= reported:
            return 0

        try:
            cfg.state_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(stage), encoding="utf-8")
            written = True
        except OSError:
            written = False

        if stage == 2 and cfg.mode == "block" and written:
            print(json.dumps({
                "decision": "block",
                "reason": (
                    f"Context load is about {load} tokens (threshold 2): every "
                    f"step re-reads that history. {HANDOVER} Send your prompt "
                    "again to continue in this session anyway."
                ),
            }))
            return 0
        text = (
            f"Context load: every step of this session now re-reads about "
            f"{load} tokens of history (threshold {stage}). {HANDOVER}"
        )
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": text}}))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
