from pathlib import Path

from sf_status.planning import (
    load_releases, load_tickets, parse_releases, parse_tickets, planning_dir,
)
from sf_status.projects import Project

HEAD = "| nr | since | kind | rank | effort | state | version | source | summary |\n"
SEP = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"


def test_parse_tickets_by_column_name():
    text = ("| nr | x | summary | version | state | rank | kind | since |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| T-1 | extra | broken | 2.1.1 | new | high | bug | 2026-01-01 |\n")
    t = parse_tickets(text)
    assert t.rows[0].nr == "T-1"
    assert t.rows[0].kind == "bug"
    assert t.rows[0].version == "2.1.1"
    assert t.missing == []


def test_parse_tickets_missing_required_column():
    text = ("| nr | kind | rank | state | version |\n| --- | --- | --- | --- | --- |\n"
            "| T-1 | bug | high | new | 2.1.1 |\n")
    t = parse_tickets(text)
    assert t.missing == ["since"]
    assert len(t.rows) == 1 and t.rows[0].since == ""


def test_parse_tickets_tolerates_noise():
    text = ("\ufeff# Tickets\r\n\r\n" + HEAD.replace("\n", "\r\n") + SEP.replace("\n", "\r\n")
            + "\r\n<!-- | T-9 | 2026-01-01 | bug | normal | S | new | | a | example | -->\r\n"
            "<!--\r\n| T-8 | 2026-01-01 | bug | normal | S | new | | a | hidden |\r\n-->\r\n"
            "| T-1 | 2026-01-01 | bug | normal | S | new | | customer A | one |\r\n"
            "| T-2 | 2026-01-02 | idea | low | M | new | | customer A | a | b | c |\r\n")
    t = parse_tickets(text)
    assert [r.nr for r in t.rows] == ["T-1", "T-2"]
    assert t.rows[1].summary == "a"
    assert t.missing == []


def test_parse_tickets_without_header():
    t = parse_tickets("# Tickets\n\nno table here\n")
    assert t.rows == []
    assert t.missing == ["nr", "since", "kind", "rank", "state", "version"]


def test_parse_releases_sections():
    text = ("## Deliveries\n\n| customer | version | planned | done | notes |\n| --- | --- | --- | --- | --- |\n"
            "| customer A | 2.1.0 | 2026-02-01 | | |\n\n"
            "## Notes\n\n| version | line | state |\n| --- | --- | --- |\n| 9.9.9 | x | y |\n\n"
            "## versions\n\n| version | notes | state | line |\n| --- | --- | --- | --- |\n"
            "| 2.1.0 | -test.1 | released | release/2.1 |\n")
    r = parse_releases(text)
    assert [(v.version, v.line, v.state, v.notes) for v in r.versions] == [
        ("2.1.0", "release/2.1", "released", "-test.1")]
    assert [(d.customer, d.version, d.planned) for d in r.deliveries] == [("customer A", "2.1.0", "2026-02-01")]
    assert r.missing == []
    only = parse_releases("## Versions\n\n| version | line | state |\n| --- | --- | --- |\n| 1 | a | planned |\n")
    assert only.deliveries == []
    assert only.missing == ["deliveries.customer", "deliveries.version"]


def _project(tmp_path, **kw):
    return Project(name="demo", title="Demo", folder=str(tmp_path), **kw)


def test_load_missing_file_is_none(tmp_path):
    p = _project(tmp_path)
    assert load_tickets(p) is None
    assert load_releases(p) is None


def test_load_invalid_utf8_does_not_crash(tmp_path):
    p = _project(tmp_path)
    (tmp_path / "planning").mkdir()
    (tmp_path / "planning" / "TICKETS.md").write_bytes(
        HEAD.encode() + SEP.encode() + b"| T-1 | 2026-01-01 | bug | low | S | new | | \xff\xfe | s |\n")
    t = load_tickets(p)
    assert t is not None and t.rows[0].nr == "T-1"
    (tmp_path / "planning" / "RELEASES.md").write_bytes(b"## Versions\n\xff\n")
    assert load_releases(p) is not None


def test_planning_dir_follows_wave_plan_path(tmp_path):
    assert planning_dir(_project(tmp_path, wave_plan="docs/plan/wave-plan.md")) == tmp_path / "docs" / "plan"
    assert planning_dir(_project(tmp_path)) == tmp_path / "planning"
    assert isinstance(planning_dir(_project(tmp_path)), Path)
