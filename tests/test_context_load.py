import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "context_load.py"


def run(payload, home: Path):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30,
    )


def state_dir(home: Path) -> Path:
    return home / ".claude" / "software-factory" / "state"


def set_config(home: Path, **cfg) -> None:
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "software-factory.json").write_text(json.dumps(cfg))


def transcript(tmp_path: Path, load: int, name="t.jsonl") -> Path:
    usage = {"input_tokens": 10, "cache_read_input_tokens": load - 30,
             "cache_creation_input_tokens": 20, "output_tokens": 5}
    lines = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"usage": {"input_tokens": 1}}},
        {"type": "assistant", "message": {"usage": usage}},
        {"type": "user", "message": {"content": "later"}},
    ]
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return p


def call(path, session="s1"):
    return {"session_id": session, "transcript_path": str(path)}


def test_below_threshold_silent(tmp_path):
    r = run(call(transcript(tmp_path, 100000)), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert not state_dir(tmp_path).exists()


def test_stage1_once_per_session(tmp_path):
    t = transcript(tmp_path, 160000)
    r = run(call(t), tmp_path)
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "UserPromptSubmit"
    assert "threshold 1" in out["additionalContext"]
    assert "160000" in out["additionalContext"] or "160,000" in out["additionalContext"]
    r2 = run(call(t), tmp_path)
    assert r2.returncode == 0 and r2.stdout == ""


def test_stage2_warn_mode_context(tmp_path):
    set_config(tmp_path, mode="warn")
    r = run(call(transcript(tmp_path, 310000)), tmp_path)
    data = json.loads(r.stdout)
    assert "decision" not in data
    assert "threshold 2" in data["hookSpecificOutput"]["additionalContext"]


def test_stage2_block_mode_blocks_once(tmp_path):
    t = transcript(tmp_path, 310000)
    r = run(call(t), tmp_path)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["decision"] == "block"
    reason = data["reason"].lower()
    assert "handover" in reason and "new session" in reason
    assert "send" in reason and "again" in reason
    r2 = run(call(t), tmp_path)
    assert r2.returncode == 0 and r2.stdout == ""


def test_stage2_skips_stage1_notice(tmp_path):
    set_config(tmp_path, mode="warn")
    t = transcript(tmp_path, 310000)
    run(call(t), tmp_path)
    r = run(call(transcript(tmp_path, 160000, "u.jsonl")), tmp_path)
    assert r.stdout == ""


def test_stage1_in_block_mode_is_notice_only(tmp_path):
    r = run(call(transcript(tmp_path, 160000)), tmp_path)
    data = json.loads(r.stdout)
    assert "decision" not in data and "hookSpecificOutput" in data


def test_missing_or_empty_transcript_silent(tmp_path):
    r = run(call(tmp_path / "nope.jsonl"), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    empty = tmp_path / "e.jsonl"
    empty.write_text("")
    r = run(call(empty), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    r = run({"session_id": "s"}, tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_transcript_without_usage_silent(tmp_path):
    p = tmp_path / "n.jsonl"
    p.write_text(json.dumps({"type": "user", "message": {"content": "x"}}) + "\nnot json\n")
    r = run(call(p), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_session_id_cannot_escape_state_dir(tmp_path):
    t = transcript(tmp_path, 160000)
    before = {p for p in tmp_path.rglob("*")}
    run(call(t, session="../../x"), tmp_path)
    new = [p for p in tmp_path.rglob("*") if p not in before and p.is_file()]
    assert len(new) == 1
    assert new[0].parent == state_dir(tmp_path)


def test_custom_thresholds_from_config(tmp_path):
    set_config(tmp_path, context_thresholds=[1000, 2000])
    r = run(call(transcript(tmp_path, 1500)), tmp_path)
    assert "threshold 1" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def test_unwritable_marker_never_blocks(tmp_path):
    sd = state_dir(tmp_path)
    sd.parent.mkdir(parents=True)
    sd.write_text("a file, not a directory")
    r = run(call(transcript(tmp_path, 310000)), tmp_path)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "decision" not in data
    assert "threshold 2" in data["hookSpecificOutput"]["additionalContext"]
