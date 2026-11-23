import json
import multiprocessing
from datetime import datetime, timezone

import pytest

from sf_status import events


def _report(text="hi", strand="a"):
    return {"kind": "report", "strand": strand, "state": "running", "text": text}


def _worker(args):
    state, n = args
    for i in range(50):
        events.append(state, "p", _report(f"w{n}-{i}", strand=f"s{n}"))


def test_append_and_read_roundtrip(state):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    stored = events.append(state, "p", _report("café"), now=now)
    assert stored["time"] == "2026-01-02T03:04:05Z" and stored["project"] == "p"
    got, off = events.read(state, "p")
    assert got == [stored] and off == (state / "events" / "p.jsonl").stat().st_size


def test_partial_line_waits(state):
    events.append(state, "p", _report("one"))
    f = state / "events" / "p.jsonl"
    complete = f.stat().st_size
    with open(f, "ab") as fh:
        fh.write(b'{"kind": "rep')
    got, off = events.read(state, "p")
    assert len(got) == 1 and off == complete


def test_corrupt_line_skipped(state):
    events.append(state, "p", _report("one"))
    with open(state / "events" / "p.jsonl", "ab") as fh:
        fh.write(b"not json\n")
    events.append(state, "p", _report("two"))
    got, _ = events.read(state, "p")
    assert [e["text"] for e in got] == ["one", "two"]


def test_parallel_appends_not_torn(state):
    with multiprocessing.Pool(20) as pool:
        pool.map(_worker, [(state, n) for n in range(20)])
    lines = (state / "events" / "p.jsonl").read_bytes().splitlines()
    assert len(lines) == 1000
    for line in lines:
        json.loads(line)


def test_too_long_rejected(state):
    with pytest.raises(ValueError):
        events.append(state, "p", _report("x" * 4000))
    assert not (state / "events" / "p.jsonl").exists()


@pytest.mark.parametrize("bad", ["A b", "../x"])
def test_invalid_ids_rejected(state, bad):
    with pytest.raises(ValueError):
        events.append(state, bad, _report())
    with pytest.raises(ValueError):
        events.append(state, "p", _report(strand=bad))
    with pytest.raises(ValueError):
        events.append(state, "p", {"kind": "task_done", "strand": "a", "id": bad})


def test_invalid_kind_and_missing_field_rejected(state):
    with pytest.raises(ValueError):
        events.append(state, "p", {"kind": "nope", "strand": "a"})
    with pytest.raises(ValueError):
        events.append(state, "p", {"kind": "report", "strand": "a", "state": "running"})


def test_marker_atomic_roundtrip(state):
    assert events.load_marker(state, "wake") == {}
    events.save_marker(state, "wake", {"p": 12})
    assert events.load_marker(state, "wake") == {"p": 12}
    assert not list((state / "markers").glob("*.tmp"))
    (state / "markers" / "wake.json").write_text("garbage")
    assert events.load_marker(state, "wake") == {}


def test_open_questions(state):
    q = {"kind": "question", "strand": "a", "id": "a-1", "question": "q",
         "background": "b", "recommendation": "r"}
    got = [events.append(state, "p", q)]
    assert set(events.open_questions(got)) == {"a-1"}
    got.append(events.append(state, "p", {"kind": "answer", "strand": "a", "question_id": "a-1", "text": "y"}))
    assert events.open_questions(got) == {}


def test_append_accepts_4000_bytes_rejects_4001(state):
    def line_size(text):
        return len((json.dumps({**_report(text), "time": "2026-01-02T03:04:05Z", "project": "p"},
                               sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))

    n = 4000 - line_size("")
    assert line_size("x" * n) == 4000
    events.append(state, "p", _report("x" * n))
    assert (state / "events" / "p.jsonl").stat().st_size == 4000
    with pytest.raises(ValueError):
        events.append(state, "p", _report("x" * (n + 1)))


def _local_request(strand="a", id="a-l1", **kw):
    return {"kind": "local_request", "strand": strand, "id": id, "step": "extension-install",
            "branch": "feature/x", "commit": "abc1234", **kw}


def test_local_request_roundtrip(state):
    stored = events.append(state, "p", _local_request())
    got, _ = events.read(state, "p")
    assert got == [stored]
    assert (got[0]["id"], got[0]["step"], got[0]["branch"], got[0]["commit"]) == (
        "a-l1", "extension-install", "feature/x", "abc1234")


@pytest.mark.parametrize("field,value", [
    ("branch", "-x"), ("branch", "a;b"), ("branch", "a b"),
    ("commit", "XYZ"), ("commit", "abc"), ("commit", "a" * 41),
    ("step", "Bad Step"), ("branch", "feature/x\n"), ("commit", "abc1234\n"),
    ("step", "extension-install\n"),
])
def test_local_request_rejects_hostile_values(state, field, value):
    with pytest.raises(ValueError):
        events.append(state, "p", _local_request(**{field: value}))
    assert not (state / "events" / "p.jsonl").exists()


def test_local_result_state_must_be_ok_or_failed(state):
    def res(**kw):
        return {"kind": "local_result", "strand": "a", "request_id": "a-l1", "state": "ok", "text": "t", **kw}
    with pytest.raises(ValueError):
        events.append(state, "p", res(state="maybe"))
    with pytest.raises(ValueError):
        events.append(state, "p", res(request_id="A l1"))
    events.append(state, "p", res())
    events.append(state, "p", res(state="failed"))


def test_open_local_and_next_id(state):
    events.append(state, "p", _local_request("a", "a-l1"))
    events.append(state, "p", {"kind": "local_result", "strand": "a", "request_id": "a-l1",
                               "state": "ok", "text": "fine"})
    events.append(state, "p", _local_request("a", "a-l2"))
    events.append(state, "p", _local_request("b", "b-l1"))
    evs, _ = events.read(state, "p")
    got = events.open_local(evs)
    assert list(got) == ["a-l2", "b-l1"]
    assert got["a-l2"]["kind"] == "local_request"
    assert events.next_local_id(evs, "a") == "a-l3"
    assert events.next_local_id(evs, "c") == "c-l1"


def test_valid_id_rejects_trailing_newline():
    assert events.valid_id("a") and not events.valid_id("a\n")


def test_open_local_ignores_malformed_result(state):
    events.append(state, "p", _local_request("a", "a-l1"))
    with open(events.events_file(state, "p"), "a", encoding="utf-8") as f:
        f.write('{"kind": "local_result", "request_id": ["x"], "time": "2026-01-01T00:00:00Z"}\n')
        f.write('{"kind": "answer", "question_id": {"a": 1}, "time": "2026-01-01T00:00:00Z"}\n')
    evs, _ = events.read(state, "p")
    assert list(events.open_local(evs)) == ["a-l1"]
    assert events.open_questions(evs) == {}
