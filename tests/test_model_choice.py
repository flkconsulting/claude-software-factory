import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "model_choice.py"


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


def call(tool, **tool_input):
    return {"tool_name": tool, "tool_input": tool_input}


def test_non_agent_tool_passes(tmp_path):
    r = run(call("Bash", command="ls"), tmp_path)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_agent_with_model_passes(tmp_path, tool):
    r = run(call(tool, prompt="x", model="sonnet"), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_fork_passes(tmp_path, tool):
    r = run(call(tool, prompt="x", subagent_type="fork"), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_block_mode_rejects_agent_without_model(tmp_path, tool):
    r = run(call(tool, prompt="x"), tmp_path)
    assert r.returncode == 2
    for word in ("model", "haiku", "sonnet", "opus"):
        assert word in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize("model", ["", "   ", None, 5])
def test_blank_or_invalid_model_counts_as_missing(tmp_path, model):
    r = run(call("Agent", prompt="x", model=model), tmp_path)
    assert r.returncode == 2


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_warn_mode_allows_with_notice(tmp_path, tool):
    set_mode(tmp_path, "warn")
    r = run(call(tool, prompt="x"), tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    text = out["systemMessage"]
    assert text and "haiku" in text
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["additionalContext"] == text


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", "null", '{"tool_name": 5}',
                                 '{"tool_name": "Agent", "tool_input": "x"}'])
def test_garbage_stdin_passes(tmp_path, raw):
    r = run(raw, tmp_path, raw=True)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr
