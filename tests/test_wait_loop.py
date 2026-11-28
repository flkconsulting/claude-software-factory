import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "wait_loop.py"


def run(payload, home: Path, raw: bool = False):
    stdin = payload if raw else json.dumps(payload)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True,
        text=True, env=env, timeout=30,
    )


def set_mode(home: Path, mode: str) -> None:
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "software-factory.json").write_text(json.dumps({"mode": mode}))


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


SELF_MATCHING_LOOPS = [
    'until ! pgrep -f "playwright test"; do sleep 10; done',
    'while pgrep -f "playwright test" >/dev/null; do sleep 5; done; echo fertig',
    'while pgrep -af uvicorn; do sleep 2; done',
    'while pgrep -u frank -f pytest > /dev/null; do sleep 1; done',
    'while pgrep --full "npm run" ; do sleep 1; done',
    'until [ -z "$(pgrep -f e2e)" ]; do sleep 30; done',
    'while ps aux | grep -v grep | grep -q playwright; do sleep 5; done',
    'until ! ps -ef | grep "[p]ytest"; do sleep 5; done',
    'cd /tmp && for i in 1; do :; done; while ps ax|grep -q node; do sleep 1; done',
    'bash -c \'while pgrep -f vite; do sleep 1; done\'',
    'while true; do\n  pgrep -f "playwright" || break\n  sleep 10\ndone',
]

ALLOWED = [
    "ls -la",
    'pgrep -f "playwright test"',
    "ps aux | grep playwright",
    "while read -r line; do echo \"$line\"; done < liste.txt",
    "while pgrep uvicorn; do sleep 1; done",
    "until docker inspect -f '{{.State.Health.Status}}' db | grep -q healthy; do sleep 2; done",
    "bash scripts/warte-auf.sh --zeit 1800 --datei bericht.md --muster '^FERTIG'",
    "until curl -fsS localhost:8000/health; do sleep 2; done",
]


@pytest.mark.parametrize("command", SELF_MATCHING_LOOPS)
def test_block_mode_rejects_self_matching_loop(tmp_path, command):
    r = run(bash(command), tmp_path)
    assert r.returncode == 2, command
    for word in ("wait-loop rule", "pgrep -f", "warte-auf.sh"):
        assert word in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize("command", ALLOWED)
def test_other_commands_pass(tmp_path, command):
    r = run(bash(command), tmp_path)
    assert r.returncode == 0, command
    assert r.stdout == "" and r.stderr == ""


def test_warn_mode_allows_with_notice(tmp_path):
    set_mode(tmp_path, "warn")
    r = run(bash(SELF_MATCHING_LOOPS[0]), tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    text = out["systemMessage"]
    assert "wait-loop rule" in text
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["additionalContext"] == text


def test_non_bash_tool_passes(tmp_path):
    payload = {"tool_name": "Write", "tool_input": {"content": SELF_MATCHING_LOOPS[0]}}
    r = run(payload, tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", "null", '{"tool_name": 5}',
                                 '{"tool_name": "Bash", "tool_input": "x"}',
                                 '{"tool_name": "Bash", "tool_input": {"command": 5}}'])
def test_garbage_stdin_passes(tmp_path, raw):
    r = run(raw, tmp_path, raw=True)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr
