"""The kontextlast mod: manifest, marketplace entry and its own test run.

The mod's behaviour is tested by `claude plugin test plugins/kontextlast`
(hooks/register.test.ts); that needs the Claude Code CLI, so here it runs
only where `claude` is installed and is skipped otherwise (e.g. in CI).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "plugins" / "kontextlast"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_and_marketplace_agree():
    plugin = load(MOD / ".claude-plugin" / "plugin.json")
    market = load(ROOT / ".claude-plugin" / "marketplace.json")
    entry = next(e for e in market["plugins"] if e["name"] == "kontextlast")
    assert plugin["name"] == "kontextlast"
    assert plugin["license"] == "MIT"
    assert entry["version"] == plugin["version"]
    assert entry["source"] == "./plugins/kontextlast"


def test_hooks_json_names_existing_module():
    modules = load(MOD / "hooks" / "hooks.json")["modules"]
    assert modules == ["./register.ts"]
    assert (MOD / "hooks" / "register.ts").is_file()


def test_default_thresholds_match_sf_config():
    sys.path.insert(0, str(ROOT / "hooks"))
    from sf_config import DEFAULT_THRESHOLDS

    a, b = DEFAULT_THRESHOLDS
    text = (MOD / "hooks" / "register.ts").read_text(encoding="utf-8")
    assert f"[{a:_}, {b:_}]" in text


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code CLI not installed")
def test_mod_validates_and_its_tests_pass():
    subprocess.run(["claude", "plugin", "validate", str(MOD)], check=True, capture_output=True)
    run = subprocess.run(["claude", "plugin", "test", "."], cwd=MOD, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
