#!/usr/bin/env python3
"""PreToolUse hook: no shell wait loops that search process command lines.

`until ! pgrep -f "playwright test"; do sleep 10; done` finds itself: the
command line of the shell running the loop contains the search pattern, so
the loop never ends. The same holds for `ps ... | grep`. The hook rejects a
Bash command that has an `until`/`while` loop together with `pgrep -f`
(also `--full` or combined flags such as `-af`) or `ps ... | grep`.

Block mode (default): exit 2 with the reason on stderr.
Warn mode: exit 0 and a JSON notice on stdout.
A hook never ends with a traceback: any failure is silent, exit 0.
"""
import json
import re
import sys
from pathlib import Path

LOOP = re.compile(r"(?:^|[\s;&|(`{'\"])(?:until|while)\s")
PGREP = re.compile(r"\bpgrep\b([^;&|\n)`]*)")
PGREP_FULL = re.compile(r"(?:^|\s)(?:-[A-Za-z]*f[A-Za-z]*|--full)(?=\s|$)")
PS_GREP = re.compile(r"\bps\b[^;&|\n]*\|[^;&\n]*\bgrep\b")

MESSAGE = (
    "wait-loop rule: a loop with `pgrep -f` or `ps ... | grep` finds its own "
    "shell, because that command line contains the search pattern, and never "
    "ends. Wait for one concrete condition with a time limit instead: the "
    "project's wait helper (for example `bash scripts/warte-auf.sh --zeit "
    "<sec> --datei <report> --muster '^DONE'`, `--container-gesund <name>`, "
    "`--pid-beendet <pid>`), or start the command with run_in_background and "
    "wait for its notification. Rewrite the command and run it again."
)


def is_self_matching_loop(command: str) -> bool:
    if not LOOP.search(command):
        return False
    if PS_GREP.search(command):
        return True
    return any(PGREP_FULL.search(m.group(1)) for m in PGREP.finditer(command))


def main() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sf_config import load_config

        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return 0
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not isinstance(command, str) or not is_self_matching_loop(command):
            return 0

        if load_config().mode == "warn":
            print(json.dumps({
                "systemMessage": MESSAGE,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": MESSAGE,
                },
            }))
            return 0
        print(MESSAGE, file=sys.stderr)
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
