import json
from datetime import date, datetime, timedelta, timezone

from sf_status import train
from sf_status.projects import Project


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def mk(**kw):
    base = dict(name="alpha", title="Alpha", folder="/x", supervisor=True, train=True)
    base.update(kw)
    return Project(**base)


def test_cutoff_follows_dst():
    p = mk()
    assert train.cutoff(p, date(2026, 12, 1)) == utc(2026, 12, 1, 17)
    assert train.cutoff(p, date(2026, 3, 31)) == utc(2026, 3, 31, 16)
    assert train.cutoff(mk(train_day="sun"), date(2026, 3, 29)) == utc(2026, 3, 29, 16)


def test_cutoff_in_dst_gap_does_not_crash():
    got = train.cutoff(mk(train_day="sun", train_time="02:30"), date(2026, 3, 29))
    assert got.tzinfo is not None


def test_not_due_before_cutoff_due_after_once():
    p = mk()
    before = {"alpha": {"dates": {"2026-11-24": "due"}}}
    assert train.check(p, before, utc(2026, 12, 1, 16, 59)) is None
    due = train.check(p, before, utc(2026, 12, 1, 17, 1))
    assert due == train.Due("2026-12-01", "due")
    marker = {"alpha": {"dates": {"2026-11-24": "due", "2026-12-01": "due"}}}
    assert train.check(p, marker, utc(2026, 12, 1, 17, 2)) is None


def test_local_date_decides_weekday():
    p = mk(train_time="00:30")
    assert train.check(p, {}, utc(2026, 11, 30, 23, 45)) == train.Due("2026-12-01", "due")


def test_skip_date_gives_skipped_once():
    p = mk(train_skip=["2026-12-01"])
    assert train.check(p, {}, utc(2026, 12, 1, 18)) == train.Due("2026-12-01", "skipped")
    assert train.check(p, {"alpha": {"dates": {"2026-12-01": "skipped"}}}, utc(2026, 12, 1, 19)) is None


def test_catch_up_within_24h_else_missed():
    p = mk()
    c = train.cutoff(p, date(2026, 12, 1))
    assert train.check(p, {}, c + timedelta(hours=23)).kind == "due"
    assert train.check(p, {}, c + timedelta(hours=25)) == train.Due("2026-12-01", "missed")
    marker = {"alpha": {"dates": {"2026-12-01": "missed"}}}
    assert train.check(p, marker, c + timedelta(hours=26)) is None


def test_server_off_for_weeks_only_latest_date():
    p = mk()
    now = utc(2026, 12, 22, 12)
    got = train.check(p, {"alpha": {"dates": {"2026-12-01": "due"}}}, now)
    assert got == train.Due("2026-12-15", "missed")
    marker = {"alpha": {"dates": {"2026-12-01": "due", "2026-12-15": "missed"}}}
    assert train.check(p, marker, now) is None


def test_train_off_gives_none_and_writes_nothing(tmp_path):
    assert train.check(mk(train=False), {}, utc(2026, 12, 1, 18)) is None
    assert not (tmp_path / "markers" / "train.json").exists()


def test_bad_settings_give_none_not_crash():
    now = utc(2026, 12, 1, 18)
    for bad in (dict(train_day="xyz"), dict(train_time="25:00"), dict(train_time="1" + chr(0x663) + ":00"),
                dict(train_tz="Nowhere/Land")):
        assert train.check(mk(**bad), {}, now) is None


def test_marker_roundtrip_and_garbage(tmp_path):
    assert train.load_marker(tmp_path) == {}
    train.save_marker(tmp_path, {"alpha": {"dates": {"2026-12-01": "due"}, "questions": {}}})
    assert train.load_marker(tmp_path)["alpha"]["dates"] == {"2026-12-01": "due"}
    (tmp_path / "markers" / "train.json").write_text("[1]")
    assert train.load_marker(tmp_path) == {}
    (tmp_path / "markers" / "train.json").write_text(json.dumps({"alpha": 5, "beta": {"dates": 3}}))
    assert train.load_marker(tmp_path) == {}
