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
