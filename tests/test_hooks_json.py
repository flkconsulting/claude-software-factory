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
    assert [e["matcher"] for e in pre] == ["Agent|Task", "Bash"]
    pre_cmds = []
    for entry, name in zip(pre, ("model_choice.py", "wait_loop.py")):
        cmds = [h for h in entry["hooks"] if h["type"] == "command"]
        assert len(cmds) == 1
        assert cmds[0]["command"] == f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}"'
        pre_cmds += cmds

    ups = hooks["UserPromptSubmit"]
    assert len(ups) == 1
    assert "matcher" not in ups[0]
    ups_cmds = [h for h in ups[0]["hooks"] if h["type"] == "command"]
    assert [h["command"] for h in ups_cmds] == [
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/context_load.py"',
        'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reminders.py"',
    ]

    for command in [h["command"] for h in pre_cmds + ups_cmds]:
        script = _resolve(_command_script(command))
        assert script.is_file(), script
