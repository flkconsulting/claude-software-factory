import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parent.parent / "skills" / "error-index" / "error_index.py"
spec = importlib.util.spec_from_file_location("error_index", MODULE)
ei = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ei)


def add_args(path, **over):
    vals = {
        "symptom": "Timeout while connecting",
        "cause": "Wrong port in config",
        "fix": "Corrected the port",
        "ref": "config/app.cfg",
    }
    vals.update(over)
    argv = ["add", "--file", str(path)]
    for key, value in vals.items():
        argv += [f"--{key}", value]
    return argv


def test_add_writes_one_json_line_with_all_fields(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path)) == 0
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert tuple(data) == ei.FIELDS
    assert data["date"] == date.today().isoformat()


def test_add_creates_missing_folder(tmp_path):
    path = tmp_path / "a" / "b" / "ERRORS.jsonl"
    assert ei.main(add_args(path)) == 0
    assert path.exists()


def test_add_second_entry_appends(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    ei.main(add_args(path))
    first = path.read_text(encoding="utf-8").splitlines()[0]
    ei.main(add_args(path, symptom="Import failed"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == first


def test_add_accepts_commit_sha_as_ref(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    sha = "0123456789abcdef" * 2 + "01234567"
    assert len(sha) == 40
    assert ei.main(add_args(path, ref=sha)) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["ref"] == sha


def test_add_rejects_long_token_in_other_fields_even_if_hex(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path, cause="0123456789abcdef" * 2 + "01234567")) == 2


SENSITIVE = [
    ("Authorization: " + "Bea" + "rer abc" + ".def" + ".ghi", "bearer"),
    ("pass" + "word" + "=hunter2", "credential-assignment"),
    ("tok" + "en: " + "0123456789" + "abcdef" * 2 + "0123456789", "long-token"),
    ("login failed for postgres://admin" + ":hunter2" + "@db/app", "url-credentials"),
    ("-----BEGIN RSA " + "PRIVATE KEY-----", "private-key"),
    ("jane@example.com", "email"),
    (".".join(["10", "1", "2", "3"]), "ipv4"),
]


@pytest.mark.parametrize("text,pattern", SENSITIVE)
def test_add_rejects_sensitive_values(tmp_path, capsys, text, pattern):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path, symptom=text)) == 2
    assert not path.exists()
    err = capsys.readouterr().err
    assert pattern in err
    assert text not in err


def test_add_requires_all_fields(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path, cause="")) == 2
    assert not path.exists()


def test_shorten_collapses_lines_and_limits_length():
    text = "line one\n\nline   two " + "x" * 500
    out = ei.shorten(text)
    assert "\n" not in out
    assert len(out) <= 200
    assert out.endswith("...")


def write_entries(path, *symptoms):
    for s in symptoms:
        ei.append_entry(
            path,
            {"date": "2026-01-01", "symptom": s, "cause": "c", "fix": "f", "ref": "r"},
        )


def test_search_all_terms_case_insensitive(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    write_entries(path, "Timeout while connecting", "Import failed")
    assert len(ei.search(path, ["TIMEOUT", "connecting"])) == 1


def test_search_missing_or_empty_file_returns_no_match(tmp_path, capsys):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(["search", "x", "--file", str(path)]) == 1
    path.write_text("", encoding="utf-8")
    assert ei.main(["search", "x", "--file", str(path)]) == 1
    assert "Traceback" not in capsys.readouterr().err


def test_search_hit_returns_zero(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    write_entries(path, "Timeout")
    assert ei.main(["search", "timeout", "--file", str(path)]) == 0


def test_search_skips_corrupt_line(tmp_path, capsys):
    path = tmp_path / "ERRORS.jsonl"
    write_entries(path, "Timeout one")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{not json timeout\n")
    write_entries(path, "Timeout two")
    assert len(ei.search(path, ["timeout"])) == 2
    assert capsys.readouterr().err.strip()


def test_default_path_from_env(tmp_path, monkeypatch):
    path = tmp_path / "env" / "E.jsonl"
    monkeypatch.setenv("SF_ERROR_INDEX", str(path))
    argv = [a for a in add_args(path) if a not in ("--file", str(path))]
    assert ei.main(argv) == 0
    assert path.exists()


def test_add_accepts_deep_repo_path_as_ref(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    ref = "src/components/dashboard/UserProfileSettings.vue"
    assert ei.main(add_args(path, ref=ref)) == 0


def test_add_accepts_long_snake_case_identifier_without_digits(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    cause = "user_profile_settings_default_value_missing_in_config"
    assert ei.main(add_args(path, cause=cause)) == 0


def test_add_rejects_mixed_letter_digit_token_in_fix(tmp_path, capsys):
    path = tmp_path / "ERRORS.jsonl"
    token = "Ab12" * 5 + "Cd34" * 5
    assert len(token) == 40
    assert ei.main(add_args(path, fix="used " + token)) == 2
    assert token not in capsys.readouterr().err


def test_add_rejects_sensitive_text_cut_off_by_shortening(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    text = "x " * 150 + "pass" + "word=hunter2"
    assert ei.main(add_args(path, symptom=text)) == 2
    assert not path.exists()


def test_append_adds_newline_if_file_lacks_trailing_newline(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    write_entries(path, "One")
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    write_entries(path, "Two")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line) for line in lines)


def test_add_rejects_non_canonical_date(tmp_path):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path) + ["--date", "20260115"]) == 2
    assert not path.exists()
    assert ei.main(add_args(path) + ["--date", "2026-01-15"]) == 0


def test_argparse_error_does_not_echo_values(tmp_path, capsys):
    path = tmp_path / "ERRORS.jsonl"
    assert ei.main(add_args(path) + ["--bogus", "valueXYZ"]) == 2
    assert "valueXYZ" not in capsys.readouterr().err
