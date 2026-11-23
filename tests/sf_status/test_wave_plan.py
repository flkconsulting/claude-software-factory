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


BASE_HEADER = ("| short | strand | approval | starts when | branch | base | migrations | may change |\n"
               "| --- | --- | --- | --- | --- | --- | --- | --- |\n")


def test_base_column_read_by_header():
    text = BASE_HEADER + "| b | s | yes | after a | feature/b | feature/a | none | src/ |\n"
    r = parse_wave_plan(text)[0]
    assert (r.short, r.branch, r.base) == ("b", "feature/b", "feature/a")


def test_base_empty_without_column_or_value():
    old = parse_wave_plan(HEADER + "| a | s | yes | now | feature/a | none | src |\n")[0]
    assert old.base == "" and old.branch == "feature/a"
    new = parse_wave_plan(BASE_HEADER + "| a | s | yes | now | feature/a |  | none | src |\n")[0]
    assert new.base == ""


def test_columns_follow_header_order():
    text = ("| short | approval | strand | branch | starts when |\n| --- | --- | --- | --- | --- |\n"
            "| x | yes | title | feature/x | now |\n")
    r = parse_wave_plan(text)[0]
    assert (r.short, r.strand, r.approved, r.starts_when, r.branch) == ("x", "title", True, "now", "feature/x")
