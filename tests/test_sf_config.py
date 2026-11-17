import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import sf_config  # noqa: E402
from sf_config import Config, load_config  # noqa: E402

DEFAULT_THRESHOLDS = (150000, 300000)


def write_cfg(home: Path, content, raw: bool = False) -> None:
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "software-factory.json"
    if raw:
        p.write_bytes(content)
    else:
        p.write_text(json.dumps(content) if not isinstance(content, str) else content)


def test_defaults_without_file(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.mode == "block"
    assert cfg.thresholds == DEFAULT_THRESHOLDS
    assert cfg.state_dir == tmp_path / ".claude" / "software-factory" / "state"
    assert not (tmp_path / ".claude").exists()


def test_default_home_is_path_home(monkeypatch, tmp_path):
    monkeypatch.setattr(sf_config.Path, "home", classmethod(lambda cls: tmp_path))
    assert load_config().state_dir == tmp_path / ".claude" / "software-factory" / "state"


def test_reads_warn_and_thresholds(tmp_path):
    write_cfg(tmp_path, {"mode": "warn", "context_thresholds": [1000, 2000]})
    cfg = load_config(tmp_path)
    assert cfg == Config("warn", (1000, 2000), tmp_path / ".claude" / "software-factory" / "state")


def test_invalid_json_gives_defaults(tmp_path):
    write_cfg(tmp_path, "{not json")
    cfg = load_config(tmp_path)
    assert (cfg.mode, cfg.thresholds) == ("block", DEFAULT_THRESHOLDS)


def test_non_object_json_gives_defaults(tmp_path):
    for content in ("[1, 2]", "42", "null", '"warn"'):
        write_cfg(tmp_path, content)
        cfg = load_config(tmp_path)
        assert (cfg.mode, cfg.thresholds) == ("block", DEFAULT_THRESHOLDS)


def test_bad_encoding_gives_defaults(tmp_path):
    write_cfg(tmp_path, b"\xff\xfe\x00{", raw=True)
    cfg = load_config(tmp_path)
    assert (cfg.mode, cfg.thresholds) == ("block", DEFAULT_THRESHOLDS)


def test_unreadable_path_gives_defaults(tmp_path):
    (tmp_path / ".claude" / "software-factory.json").mkdir(parents=True)
    cfg = load_config(tmp_path)
    assert (cfg.mode, cfg.thresholds) == ("block", DEFAULT_THRESHOLDS)


def test_unknown_mode_gives_default(tmp_path):
    for mode in ("off", "WARN", 3, None, ["warn"]):
        write_cfg(tmp_path, {"mode": mode})
        assert load_config(tmp_path).mode == "block"


def test_bad_thresholds_give_default(tmp_path):
    bad = [
        [150000],
        [300000, 150000],
        [1000, 1000],
        [-5, 100],
        [0, 100],
        ["a", "b"],
        [1.5, 2.5],
        [True, 5],
        [1, 2, 3],
        "1000,2000",
        {"a": 1},
        None,
    ]
    for value in bad:
        write_cfg(tmp_path, {"mode": "warn", "context_thresholds": value})
        cfg = load_config(tmp_path)
        assert cfg.thresholds == DEFAULT_THRESHOLDS, value
        assert cfg.mode == "warn", value


def test_valid_thresholds_with_bad_mode_keeps_thresholds(tmp_path):
    write_cfg(tmp_path, {"mode": "nope", "context_thresholds": [10, 20]})
    cfg = load_config(tmp_path)
    assert cfg.mode == "block"
    assert cfg.thresholds == (10, 20)
