import json
import os
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sf_status.cli import main
from sf_status.config import ServerConfig, load_server_config

ROOT = Path(__file__).resolve().parent.parent.parent


def write_cfg(home: Path, content) -> None:
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "software-factory.json").write_text(json.dumps(content))


def test_defaults_without_file(tmp_path):
    c = load_server_config(tmp_path)
    assert c.enabled is False
    assert c.supervisor is False
    assert (c.stall_minutes, c.supervisor_busy_minutes, c.supervisor_timeout_minutes) == (45, 75, 30)
    assert c.supervisor_model == "sonnet"
    assert (c.heavy_slots, c.max_strands, c.safety_pass_hours, c.retry_limit) == (2, 4, 3, 3)
    assert c.usage_report is True
    assert c.auto_compact_window == 200000
    assert c.state_dir == tmp_path / ".claude" / "software-factory" / "server"
    assert not (tmp_path / ".claude").exists()


def test_server_section_overrides(tmp_path):
    write_cfg(tmp_path, {"server": {"enabled": True, "heavy_slots": 3, "state_dir": "~/x"}})
    c = load_server_config(tmp_path)
    assert c.enabled is True and c.heavy_slots == 3
    assert c.state_dir == tmp_path / "x"
    with pytest.raises(FrozenInstanceError):
        c.enabled = False


def test_invalid_values_fall_back_per_field(tmp_path):
    write_cfg(tmp_path, {"server": {"heavy_slots": 0, "stall_minutes": "x", "enabled": 1,
                                    "supervisor_model": "gpt", "max_strands": True, "retry_limit": 5}})
    c = load_server_config(tmp_path)
    assert (c.heavy_slots, c.stall_minutes, c.enabled, c.supervisor_model, c.max_strands) == (2, 45, False, "sonnet", 4)
    assert c.retry_limit == 5
    write_cfg(tmp_path, {"server": []})
    assert load_server_config(tmp_path).heavy_slots == 2


def test_unreadable_file_gives_defaults(tmp_path):
    d = tmp_path / ".claude"
    d.mkdir()
    (d / "software-factory.json").write_text("{not json")
    assert load_server_config(tmp_path).heavy_slots == 2


def test_stage1_keys_ignored(tmp_path):
    write_cfg(tmp_path, {"mode": "warn", "context_thresholds": [1, 2], "server": {"max_strands": 6}})
    c = load_server_config(tmp_path)
    assert c.max_strands == 6 and c.enabled is False


def test_cli_config_prints_value(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["config", "heavy_slots"]) == 0
    assert capsys.readouterr().out.strip() == "2"


def test_cli_bad_args_return_code():
    assert main(["config", "nope"]) == 2


def test_fixtures(cfg, state):
    assert isinstance(cfg, ServerConfig) and cfg.enabled and cfg.state_dir == state


def test_wrapper_runs(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    r = subprocess.run([str(ROOT / "scripts" / "bin" / "sf-status"), "config", "stall_minutes"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout.strip() == "45"


def test_config_without_home_raises_value_error(monkeypatch):
    def boom():
        raise RuntimeError("no home")
    monkeypatch.setattr(Path, "home", staticmethod(boom))
    with pytest.raises(ValueError):
        load_server_config()


def test_local_notice_hours_default_and_validation(monkeypatch, tmp_path, capsys):
    assert load_server_config(tmp_path).local_notice_hours == 8
    write_cfg(tmp_path, {"server": {"local_notice_hours": 2}})
    assert load_server_config(tmp_path).local_notice_hours == 2
    for bad in (0, "x", True):
        write_cfg(tmp_path, {"server": {"local_notice_hours": bad}})
        assert load_server_config(tmp_path).local_notice_hours == 8
    (tmp_path / ".claude" / "software-factory.json").unlink()
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["config", "local_notice_hours"]) == 0
    assert capsys.readouterr().out.strip() == "8"
