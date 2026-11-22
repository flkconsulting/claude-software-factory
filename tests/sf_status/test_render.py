import json
import re
from datetime import datetime, timezone

from sf_status import render
from sf_status.collect import State, StrandView

NOW = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_state(**kw):
    s = State()
    s.strands["alpha/s1"] = StrandView("alpha", "s1", "running", "2026-11-22T10:00:00Z", "feature/x", "working", False)
    s.questions = [{"id": "s1-1", "question": "Which way?", "background": "Because.",
                    "recommendation": "Way A", "project": "alpha", "strand": "s1", "time": "2026-11-22T10:00:00Z"}]
    s.tasks = [{"id": "t-1", "title": "Do it", "why": "needed", "project": "alpha", "time": "2026-11-22T10:00:00Z"}]
    s.notices = [{"level": "warning", "title": "Careful", "text": "something", "project": "alpha",
                  "time": "2026-11-22T10:00:00Z"}]
    s.runs = [{"start": "2026-11-22T09:00:00Z", "end": "2026-11-22T09:05:00Z", "result": "ok", "triggers": ["safety"]}]
    s.recent = [{"time": "2026-11-22T10:00:00Z", "project": "alpha", "strand": "s1", "kind": "report", "text": "hi"}]
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_sections_in_order():
    md = render.render_markdown(make_state(usage={"day": "2026-11-22"}), NOW)
    heads = [h for h in re.findall(r"^## (.+)$", md, re.M)]
    assert heads == ["Needs you", "Strands", "Stalls", "Supervisor", "Usage", "Recent events"]


def test_answer_line_present():
    md = render.render_markdown(make_state(), NOW)
    assert 'sf-status answer --project alpha --id s1-1 "..."' in md
    assert "Way A" in md and "Because." in md


def test_pipes_and_newlines_escaped_in_table():
    s = make_state()
    s.strands["alpha/s1"].text = "a|b\nc\r\nd"
    md = render.render_markdown(s, NOW)
    row = [ln for ln in md.splitlines() if ln.startswith("| alpha | s1")]
    assert len(row) == 1
    assert "a\\|b c d" in row[0]


def test_html_escapes_script():
    s = make_state()
    s.strands["alpha/s1"].text = "<script>alert(1)</script>"
    s.questions[0]["question"] = "<script>x</script>"
    html = render.render_html(s, NOW)
    assert "<script" not in html
    assert "&lt;script&gt;" in html


def test_html_has_no_external_resources():
    html = render.render_html(make_state(usage={}), NOW)
    assert not re.search(r"(src|href)\s*=\s*[\"']?\s*http", html, re.I)
    assert "<script" not in html and "@import" not in html and "url(" not in html


def test_ansi_escapes_removed():
    s = make_state()
    s.strands["alpha/s1"].text = "\x1b[31mred\x1b[0m\x07 ok"
    for out in (render.render_markdown(s, NOW), render.render_html(s, NOW)):
        assert "\x1b" not in out and "\x07" not in out
        assert "red ok" in out


def test_long_text_truncated_in_table():
    s = make_state()
    s.strands["alpha/s1"].text = "x" * 500
    md = render.render_markdown(s, NOW)
    assert "x" * 201 not in md


def test_deterministic():
    s = make_state(usage={"day": "d"})
    assert render.render_markdown(s, NOW) == render.render_markdown(s, NOW)
    assert render.render_html(s, NOW) == render.render_html(s, NOW)


def test_usage_section_omitted_when_none():
    md = render.render_markdown(make_state(usage=None), NOW)
    assert "## Usage" not in md
    assert "<h2>Usage</h2>" not in render.render_html(make_state(usage=None), NOW)


def test_usage_robust_and_disclaimer():
    md = render.render_markdown(make_state(usage={"by_model": "weird", "by_project": {"a": None}}), NOW)
    assert "list-price equivalent, not an invoice" in md
    assert "unknown" in md


def test_stalled_listed():
    s = make_state()
    s.strands["alpha/s1"].stalled = True
    md = render.render_markdown(s, NOW)
    assert "alpha/s1" in md.split("## Stalls")[1].split("## Supervisor")[0]


def test_triggers_rendered():
    s = make_state(triggers={"open": [{"id": "done:s1", "since": "t", "tries": 1}],
                             "parked": [{"id": "retry", "since": "t", "tries": 3}], "last_run": None})
    md = render.render_markdown(s, NOW)
    assert "done:s1" in md and "retry" in md


def test_write_atomic(tmp_path):
    (tmp_path / "supervisor").mkdir()
    (tmp_path / "supervisor" / "triggers.json").write_text(
        json.dumps({"open": [{"id": "safety", "since": "t", "tries": 0}], "parked": []}))
    render.write(tmp_path, make_state(), NOW)
    assert (tmp_path / "STATUS.md").exists() and (tmp_path / "status.html").exists()
    assert "safety" in (tmp_path / "STATUS.md").read_text()
    assert not list(tmp_path.glob("*.tmp"))


def test_write_without_triggers_file(tmp_path):
    render.write(tmp_path, make_state(), NOW)
    assert (tmp_path / "STATUS.md").exists()
