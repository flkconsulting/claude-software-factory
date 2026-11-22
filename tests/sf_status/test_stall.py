from sf_status import stall

LIMIT = 45 * 60


def test_unchanged_reports_once():
    entry, report = stall.check(None, "aaa", 1000.0, LIMIT)
    assert report is False
    entry, report = stall.check(entry, "aaa", 1000.0 + LIMIT, LIMIT)
    assert report is True and entry["reported"] is True
    entry, report = stall.check(entry, "aaa", 1000.0 + 2 * LIMIT, LIMIT)
    assert report is False


def test_change_resets():
    entry, _ = stall.check(None, "aaa", 0.0, LIMIT)
    entry, report = stall.check(entry, "aaa", LIMIT, LIMIT)
    assert report is True
    entry, report = stall.check(entry, "bbb", LIMIT + 10, LIMIT)
    assert report is False and entry["reported"] is False and entry["since"] == LIMIT + 10
    entry, report = stall.check(entry, "bbb", 2 * LIMIT + 10, LIMIT)
    assert report is True


def test_tip_lines_ignored():
    a = stall.pane_hash("work\nTip: use /help\n")
    b = stall.pane_hash("work\nTip: something else\nupdate failed\n")
    assert a == b
    assert stall.pane_hash("work\n") == a
    assert stall.pane_hash("other\n") != a
    assert len(a) == 12
