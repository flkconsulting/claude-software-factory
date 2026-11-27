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
    assert heads == ["Needs you", "Waiting for local step", "Strands", "Stalls", "Supervisor", "Usage", "Recent events"]


def test_answer_line_present():
    md = render.render_markdown(make_state(), NOW)
    assert 'sf-status answer --project alpha --id s1-1 "..."' in md
    assert "Way A" in md and "Because." in md


def test_dismiss_line_present_in_both_formats():
    cmd = 'sf-status dismiss --project alpha --time 2026-11-22T10:00:00Z --title Careful'
    assert cmd in render.render_markdown(make_state(), NOW)
    assert cmd in render.render_html(make_state(), NOW)


def test_dismiss_line_quotes_title_and_skips_invalid_project():
    s = make_state()
    s.notices[0]["title"] = "it's $(x)"
    md = render.render_markdown(s, NOW)
    assert "--title 'it'\"'\"'s $(x)'" in md
    s.notices[0]["project"] = "Bad Project"
    assert "sf-status dismiss" not in render.render_markdown(s, NOW)


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


def test_answer_line_only_for_valid_ids():
    s = make_state()
    s.questions = [{"id": 'x"; rm -rf ~; "', "project": "alpha", "question": "q"},
                   {"project": "alpha", "question": "no id"},
                   {"id": "s1-2", "project": "alpha", "question": "ok"}]
    md = render.render_markdown(s, NOW)
    assert "rm -rf" not in "".join(ln for ln in md.splitlines() if ln.startswith("sf-status"))
    assert md.count("sf-status answer") == 1
    assert 'sf-status answer --project alpha --id s1-2 "..."' in md
    assert md.count("id invalid") == 2


def test_markdown_html_defused():
    s = make_state()
    s.strands["alpha/s1"].text = '<img src=http://x/y> [a](http://z) `c`'
    s.questions[0]["question"] = "<script>x</script> & <a href=http://q>"
    md = render.render_markdown(s, NOW)
    assert "<img" not in md and "<script" not in md and "<a " not in md
    assert "&lt;script&gt;" in md and "&amp;" in md
    assert "\\[a\\](" in md and "[a](" not in md and "\\`c\\`" in md


def test_usage_by_model_row_shows_numbers_and_unknown_usd():
    u = {"day": "d", "by_model": {"m1": {"responses": 2, "usd": 1.5}, "m2": {"responses": 1, "usd": None}}}
    md = render.render_markdown(make_state(usage=u), NOW)
    assert "responses 2" in md and "usd 1.5" in md and "usd unknown" in md


def test_usage_helper_share_and_top_context_readable():
    u = {"day": "d", "helper_share": {"haiku": 0.25, "sonnet": 1.0},
         "top_context": [{"session": "abcd1234", "project": "alpha", "responses": 7, "cache_read": 900}]}
    md = render.render_markdown(make_state(usage=u), NOW)
    assert "Helper share: haiku 25%, sonnet 100%" in md
    assert "| session | project | responses | cache read |" in md
    assert "| abcd1234 | alpha | 7 | 900 |" in md
    assert "{" not in md.split("## Usage", 1)[1].split("## Recent", 1)[0]


def test_usage_helper_share_and_top_context_robust():
    u = {"day": "d", "helper_share": {"haiku": "x"}, "top_context": ["odd", {"session": "s"}]}
    md = render.render_markdown(make_state(usage=u), NOW)
    assert "Helper share: haiku unknown" in md
    assert "| s | unknown | unknown | unknown |" in md


def test_md_escapes_backslash():
    s = make_state()
    s.strands["alpha/s1"].text = "a\\"
    md = render.render_markdown(s, NOW)
    row = [ln for ln in md.splitlines() if ln.startswith("| alpha | s1")]
    assert len(row) == 1 and "a\\\\" in row[0]
    lines = md.splitlines()
    header = lines[lines.index(row[0]) - 2]
    unescaped = re.compile(r"(?<!\\)\|")
    assert len(unescaped.findall(row[0])) == len(unescaped.findall(header))


def test_ctrl_strips_c1_and_bidi():
    s = make_state()
    s.strands["alpha/s1"].text = "a\x85b\u202ec\u2066d\u2069e\x9ff"
    for md in (render.render_markdown(s, NOW), render.render_html(s, NOW)):
        for ch in ("\x85", "\u202e", "\u2066", "\u2069", "\x9f"):
            assert ch not in md
        assert "abcdef" in md


LOCAL = {"project": "alpha", "id": "s1-l1", "strand": "s1", "step": "build-ext", "branch": "feature/x",
         "commit": "0123456789abcdef0123456789abcdef01234567", "since": "2026-11-22T11:00:00Z",
         "last_result": "failed: boom"}


def test_local_section_table():
    s = make_state(local=[dict(LOCAL)])
    md = render.render_markdown(s, NOW)
    row = [ln for ln in md.splitlines() if ln.startswith("| alpha | s1-l1")]
    assert len(row) == 1
    assert "| s1 | build-ext | feature/x | 0123456789ab | 2026-11-22T11:00:00Z | failed: boom |" in row[0]
    assert "0123456789abc" not in row[0]
    html = render.render_html(s, NOW)
    assert "<td>s1-l1</td>" in html and "<td>0123456789ab</td>" in html and "<td>build-ext</td>" in html
    assert "<td>failed: boom</td>" in html


def test_local_section_empty_says_none():
    md = render.render_markdown(make_state(local=[]), NOW)
    sec = md.split("## Waiting for local step")[1].split("## ")[0]
    assert "None." in sec


def test_local_section_escapes_free_text():
    e = dict(LOCAL, last_result="failed: a|b\nc\r\nd <script>x</script> \x1b[31mred\x1b[0m")
    s = make_state(local=[e])
    md = render.render_markdown(s, NOW)
    row = [ln for ln in md.splitlines() if ln.startswith("| alpha | s1-l1")]
    assert len(row) == 1
    assert "a\\|b c d" in row[0]
    assert "\x1b" not in md
    html = render.render_html(s, NOW)
    assert "<script" not in html and "&lt;script&gt;" in html and "\x1b" not in html


def test_recent_shows_local_request_step():
    s = make_state()
    s.recent = [{"time": "2026-11-22T10:00:00Z", "project": "alpha", "strand": "s1",
                 "kind": "local_request", "step": "build-ext"}]
    assert "build-ext" in render.render_markdown(s, NOW)


def test_attention_lists_what_needs_the_human():
    s = make_state()
    s.strands["alpha/s2"] = StrandView("alpha", "s2", "waiting", "2026-11-22T11:00:00Z", None, "needs answer", False)
    s.strands["beta/s3"] = StrandView("beta", "s3", "blocked", "2026-11-22T11:00:00Z", None, "stuck", False)
    s.notices = s.notices + [{"level": "info", "title": "FYI", "text": "x", "project": "alpha",
                              "time": "2026-11-22T10:01:00Z"},
                             {"level": "approval", "title": "Go?", "text": "y", "project": "beta",
                              "strand": "s3", "time": "2026-11-22T10:02:00Z"}]
    got = render.attention(s)
    assert got["questions"] == [{"project": "alpha", "id": "s1-1", "question": "Which way?"}]
    assert got["tasks"] == [{"project": "alpha", "id": "t-1", "title": "Do it"}]
    assert [n["level"] for n in got["notices"]] == ["warning", "approval"]
    assert got["notices"][1] == {"project": "beta", "strand": "s3", "time": "2026-11-22T10:02:00Z",
                                 "level": "approval", "title": "Go?"}
    assert got["strands"] == [{"project": "alpha", "strand": "s2", "state": "waiting"},
                              {"project": "beta", "strand": "s3", "state": "blocked"}]


def test_attention_is_stable_when_only_volatile_fields_change():
    a = make_state()
    b = make_state()
    b.strands["alpha/s1"].since = "2026-11-22T11:59:00Z"
    b.strands["alpha/s1"].text = "other"
    b.recent = []
    assert render.attention(a) == render.attention(b)


def test_write_writes_attention_json(tmp_path):
    render.write(tmp_path, make_state(), NOW)
    got = json.loads((tmp_path / "attention.json").read_text())
    assert got == render.attention(make_state())
