"""The termine mod: manifest, marketplace entry, the line rule shared with reminders.py.

The mod's behaviour is tested by `claude plugin test plugins/termine`
(hooks/register.test.ts); that needs the Claude Code CLI, so that run is
skipped where `claude` is not installed (e.g. in CI). The table of shared
example lines inside register.test.ts is checked here against the Python
parser, so both suites prove the same rule.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "plugins" / "termine"
sys.path.insert(0, str(ROOT / "hooks"))
import reminders  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def shared_cases():
    text = (MOD / "hooks" / "register.test.ts").read_text(encoding="utf-8")
    block = text.split("// shared-cases:begin", 1)[1].split("// shared-cases:end", 1)[0]
    array = block[block.index("SHARED: SharedCase[] = [") + len("SHARED: SharedCase[] = "):]
    return json.loads(array.strip())


def test_manifest_and_marketplace_agree():
    plugin = load(MOD / ".claude-plugin" / "plugin.json")
    market = load(ROOT / ".claude-plugin" / "marketplace.json")
    entry = next(e for e in market["plugins"] if e["name"] == "termine")
    assert plugin["name"] == "termine"
    assert plugin["license"] == "MIT"
    assert plugin["version"] == "0.1.0"
    assert entry["version"] == plugin["version"]
    assert entry["source"] == "./plugins/termine"


def test_hooks_json_names_existing_module():
    modules = load(MOD / "hooks" / "hooks.json")["modules"]
    assert modules == ["./register.ts"]
    assert (MOD / "hooks" / "register.ts").is_file()


def test_shared_cases_match_python_parser():
    cases = shared_cases()
    assert len(cases) >= 12
    for c in cases:
        got = reminders.parse(c["line"])
        if c["expect"] is None:
            assert got == [], c["line"]
            continue
        assert len(got) == 1, c["line"]
        e, want = got[0], c["expect"]
        at = e.time.strftime("%H:%M") if e.time else None
        assert (e.day.isoformat(), at, e.project, e.text) == (
            want["day"], want["time"], want["project"], want["text"]), c["line"]


def test_shared_cases_cover_the_time_bounds():
    expect = {c["line"]: c["expect"] for c in shared_cases()}

    def find(token):
        return [v for k, v in expect.items() if f" {token} " in k]

    for token in ("00:00", "23:59"):
        hits = find(token)
        assert hits and all(v is not None for v in hits), token
    for token in ("24:00", "25:99", "9:00"):
        hits = find(token)
        assert hits and all(v is None for v in hits), token


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code CLI not installed")
def test_mod_validates_and_its_tests_pass():
    subprocess.run(["claude", "plugin", "validate", str(MOD)], check=True, capture_output=True)
    run = subprocess.run(["claude", "plugin", "test", "."], cwd=MOD, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
