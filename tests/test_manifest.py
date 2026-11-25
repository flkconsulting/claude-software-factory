import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UMLAUTS = "\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df"


def load(name):
    return json.loads((ROOT / ".claude-plugin" / name).read_text(encoding="utf-8"))


def test_version_0_4_0():
    assert load("plugin.json")["version"] == "0.4.1"
    assert load("marketplace.json")["plugins"][0]["version"] == "0.4.1"


def test_plugin_and_marketplace_agree():
    plugin = load("plugin.json")
    market = load("marketplace.json")
    assert plugin["name"] == "software-factory"
    assert plugin["version"] == "0.4.1"
    assert plugin["license"] == "MIT"
    assert len(market["plugins"]) == 1
    entry = market["plugins"][0]
    assert entry["name"] == plugin["name"]
    assert entry["version"] == plugin["version"]
    assert entry["source"] == "./"


def test_no_umlauts_in_tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    offenders = []
    for rel in filter(None, out.split("\0")):
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        if any(ch in text for ch in UMLAUTS):
            offenders.append(rel)
    assert not offenders, offenders
