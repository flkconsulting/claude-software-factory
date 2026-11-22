import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from sf_status import usage
from sf_status.projects import Project

FIX = Path(__file__).parent / "fixtures" / "transcripts"
DAY = date(2026, 11, 22)
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "usage-report.py"
PRICES = {"as_of": "2026-11-22", "note": "t", "models": {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.2},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.1},
    "claude-haiku-5-5": {"input": 0.1, "output": 0.5, "cache_read": 0.01}}}


@pytest.fixture
def root(tmp_path):
    dst = tmp_path / "projects"
    shutil.copytree(FIX, dst)
    ts = datetime(2026, 11, 22, 13, tzinfo=timezone.utc).timestamp()
    for f in dst.rglob("*.jsonl"):
        os.utime(f, (ts, ts))
    return dst


@pytest.fixture
def projects():
    return [Project(name="alpha", title="Alpha", folder="/work/alpha")]


def test_dedupe_by_message_id(root, projects):
    r = usage.summarize(root, DAY, PRICES, projects)
    assert r["day"] == "2026-11-22"
    opus = r["by_model"]["claude-opus-5-5"]
    assert opus["responses"] == 1 and opus["input"] == 100 and opus["cache_read"] == 1000
    assert opus["usd"] == pytest.approx((100 * 4 + 50 * 20 + 1000 * 0.2 + 200 * 4 * 1.25) / 1e6)
    assert "<synthetic>" not in r["by_model"]


def test_helper_agents_counted_separately(root, projects):
    r = usage.summarize(root, DAY, PRICES, projects)
    assert r["by_model"]["claude-sonnet-5-5"]["responses"] == 2
    assert r["helper_share"]["claude-haiku-5-5"] == 1.0
    assert r["helper_share"]["claude-sonnet-5-5"] == 0.5
    assert r["helper_share"]["claude-opus-5-5"] == 0.0
    assert [t["session"] for t in r["top_context"]] == ["s1"]
    assert r["top_context"][0]["cache_read"] == 4000


def test_unknown_model_usd_none(root, projects):
    r = usage.summarize(root, DAY, PRICES, projects)
    assert r["by_model"]["claude-future-9"]["usd"] is None
    assert r["by_model"]["claude-future-9"]["responses"] == 1


def test_corrupt_lines_counted_not_raised(root, projects):
    assert usage.summarize(root, DAY, PRICES, projects)["unknown_lines"] == 1


def test_missing_dir_returns_empty(tmp_path, projects):
    r = usage.summarize(tmp_path / "nope", DAY, PRICES, projects)
    assert r["by_model"] == {} and r["by_project"] == {} and r["unknown_lines"] == 0
    assert r["top_context"] == []


def test_by_project_uses_project_for_path(root, projects):
    r = usage.summarize(root, DAY, PRICES, projects)
    assert r["by_project"]["alpha"]["responses"] == 4
    assert r["by_project"]["other"]["responses"] == 1


def test_load_prices_missing_is_empty(tmp_path):
    assert usage.load_prices(tmp_path / "x.json")["models"] == {}
    real = usage.load_prices(Path(usage.__file__).parent / "prices.json")
    assert real["as_of"] and "claude-opus-5-5" in real["models"]


def test_report_cli_json(root, tmp_path):
    out = subprocess.run([sys.executable, str(SCRIPT), "--day", "2026-11-22", "--json", "--root", str(root),
                          "--state-dir", str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["day"] == "2026-11-22" and "by_model" in data
    text = subprocess.run([sys.executable, str(SCRIPT), "--day", "2026-11-22", "--root", str(root),
                           "--state-dir", str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert "list-price equivalent, not an invoice" in text.stdout


def test_collect_fills_usage(cfg, state, root, projects, monkeypatch):
    from sf_status import collect, effects
    monkeypatch.setattr(effects, "tmux_sessions", lambda: [])
    now = datetime(2026, 11, 22, 14, tzinfo=timezone.utc).timestamp()
    from dataclasses import replace
    cfg = replace(cfg, usage_report=True)
    s = collect.collect(cfg, projects, now, transcripts_root=root)
    assert s.usage and s.usage["day"] == "2026-11-22"
    s = collect.collect(cfg, projects, now, transcripts_root=root / "missing")
    assert s.usage is not None and s.usage["by_model"] == {}
    s = collect.collect(replace(cfg, usage_report=False), projects, now, transcripts_root=root)
    assert s.usage is None
