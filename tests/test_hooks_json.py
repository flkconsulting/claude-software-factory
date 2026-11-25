import json
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
PLUGIN_ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"


def _command_script(command):
    # Expected form: python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py"
    parts = shlex.split(command)
    assert parts[0] == "python3", command
    assert len(parts) == 2, command
    return parts[1]


def _resolve(script):
    assert script.startswith(PLUGIN_ROOT_VAR + "/"), script
    return ROOT / script[len(PLUGIN_ROOT_VAR) + 1:]


def test_hooks_registered():
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    hooks = config["hooks"]

    pre = hooks["PreToolUse"]
    assert len(pre) == 1
    assert pre[0]["matcher"] == "Agent|Task"
    pre_cmds = [h for h in pre[0]["hooks"] if h["type"] == "command"]
    assert len(pre_cmds) == 1
    assert pre_cmds[0]["command"] == 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/model_choice.py"'

    ups = hooks["UserPromptSubmit"]
    assert len(ups) == 1
    assert "matcher" not in ups[0]
    ups_cmds = [h for h in ups[0]["hooks"] if h["type"] == "command"]
    assert [h["command"] for h in ups_cmds] == [
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/context_load.py"',
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reminders.py"',
    ]

    for command in [pre_cmds[0]["command"]] + [h["command"] for h in ups_cmds]:
        script = _resolve(_command_script(command))
        assert script.is_file(), script
