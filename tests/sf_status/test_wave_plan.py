import hashlib

from sf_status.wave_plan import parse_wave_plan

HEADER = ("| short | strand | approval | starts when | branch | migrations | may change |\n"
          "| --- | --- | --- | --- | --- | --- | --- |\n")


def test_parse_columns():
    row = "| w1 | api | yes | after w0 | feature/api | none | src/api |"
    rows = parse_wave_plan(HEADER + row + "\n")
    assert len(rows) == 1
    r = rows[0]
    assert (r.short, r.strand, r.approved, r.starts_when, r.branch) == ("w1", "api", True, "after w0", "feature/api")
    assert r.row_hash == hashlib.sha1(row.encode()).hexdigest()[:12]


def test_approval_yes_with_quote():
    text = HEADER + '| a | s | yes ("go ahead") | now | b | - | - |\n| b | s | no | now | b | - | - |\n'
    rows = parse_wave_plan(text)
    assert [r.approved for r in rows] == [True, False]


def test_header_and_separator_skipped():
    text = "# Plan\n\nSome prose | with a pipe\n" + HEADER + "|:--|:-:|--:|---|---|---|---|\n"
    assert parse_wave_plan(text) == []
