#!/usr/bin/env python3
"""PreToolUse hook: every subagent dispatch must name its model explicitly.

Block mode (default): exit 2 with the reason on stderr.
Warn mode: exit 0 and a JSON notice on stdout.
A hook never ends with a traceback: any failure is silent, exit 0.
"""
import json
import sys
from pathlib import Path

AGENT_TOOLS = ("Agent", "Task")

MESSAGE = (
    "model-choice rule: every subagent dispatch must set `model` explicitly "
    "(haiku, sonnet or opus). Haiku is for mechanical work, sonnet is the "
    "default, opus only for architecture, security and the final review of a "
    "whole effort. Add the `model` parameter and dispatch again."
)


def main() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sf_config import load_config

        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") not in AGENT_TOOLS:
            return 0
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        if tool_input.get("subagent_type") == "fork":
            return 0
        model = tool_input.get("model")
        if isinstance(model, str) and model.strip():
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
