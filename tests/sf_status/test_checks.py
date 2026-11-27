import json
from datetime import datetime, timezone

import pytest

from sf_status import checks, events
from sf_status.planning import Delivery, Releases, Ticket, TicketTable, Version

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def T(**kw):
    base = dict(nr="T-1", since="2026-11-01", kind="bug", rank="normal", effort="S", state="new",
                version="", source="customer A", summary="x")
    base.update(kw)
    return Ticket(**base)


def table(*rows, missing=()):
    return TicketTable(list(rows), list(missing))


def rel(*versions, deliveries=(), missing=()):
    return Releases(list(versions), list(deliveries), list(missing))


V = Version("2.1.0", "release/2.1", "released")


def codes(findings):
    return [f.code for f in findings]


def run(t, releases=rel(V), hours=24):
    return checks.ticket_findings(table(*t) if isinstance(t, list) else table(t), releases, NOW, hours)


@pytest.mark.parametrize("rows,code", [
    ([T(), T(nr="T-1")], "number-duplicate"),
    ([T(nr="3")], "number-invalid"),
    ([T(kind="task")], "kind-unknown"),
    ([T(kind="bug", rank="low")], "rank-unknown"),
    ([T(effort="XL")], "effort-unknown"),
    ([T(state="open")], "state-unknown"),
    ([T(since="yesterday")], "since-invalid"),
    ([T(since="2026-13-45")], "since-invalid"),
    ([T(state="planned")], "version-missing"),
    ([T(state="in-train")], "version-missing"),
    ([T(state="planned", version="2.1.0-test.1")], "version-test-suffix"),
    ([T(state="planned", version="9.9.9")], "version-unknown"),
])
def test_ticket_findings_each_rule(rows, code):
    assert code in codes(run(rows))


def test_feature_with_low_rank_is_fine():
    assert run(T(kind="feature", rank="low")) == []


def test_valid_table_has_no_findings():
    rows = [T(), T(nr="T-2", state="planned", version="2.1.0", effort=""),
            T(nr="T-3", state="deferred", rank="critical"), T(nr="T-4", state="rejected", rank="critical"),
            T(nr="T-5", kind="feature", rank="low", state="shipped", version="2.1.0")]
    assert run(rows) == []


def test_critical_unplanned_threshold():
    # since counts from 00:00 UTC of the date; NOW is 12:00
    t = T(rank="critical", since="2026-11-27")
    assert "critical-unplanned" not in codes(run(t, hours=24))
    assert "critical-unplanned" not in codes(run(t, hours=13))
    assert "critical-unplanned" in codes(run(t, hours=12))
    assert "critical-unplanned" in codes(run(t, hours=1))
    day_before = T(rank="critical", since="2026-11-26")
    assert "critical-unplanned" not in codes(run(day_before, hours=37))
    assert "critical-unplanned" in codes(run(day_before, hours=36))
    assert "critical-unplanned" in codes(run(T(rank="critical", since="2026-11-26", state="assessed"), hours=24))
    assert "critical-unplanned" not in codes(run(T(rank="critical", since="2026-11-01", state="planned",
                                                    version="2.1.0")))
    assert "critical-unplanned" not in codes(run(T(kind="feature", rank="high", since="2026-01-01")))
    f = [x for x in run(T(rank="critical", since="2026-11-01")) if x.code == "critical-unplanned"]
    assert f and f[0].level == "warning"


def test_levels_are_info_except_critical():
    assert {f.level for f in run(T(kind="task"))} == {"info"}


def test_version_unknown_skipped_without_releases():
    rows = [T(state="planned", version="9.9.9")]
    assert checks.ticket_findings(table(*rows), None, NOW, 24) == []


def test_missing_required_column_one_finding():
    rows = [T(since=""), T(nr="T-2", since="")]
    out = checks.ticket_findings(table(*rows, missing=["since"]), rel(V), NOW, 24)
    assert codes(out) == ["column-missing-since"]
    assert out[0].key == "tickets-file/column-missing-since"


def test_key_and_title_shape():
    out = run([T(), T(nr="T-1")])
    assert out[0].key == "T-1/number-duplicate" and out[0].title == "ticket T-1: number-duplicate"
    bad = run(T(nr="x y"))
    assert bad[0].key == "row1/number-invalid"


def test_release_findings_each_rule():
    r = rel(Version("1.0.0", "", "planned"), Version("1.0.0", "release/1.0", "live"),
            Version("2.0.0", "release/2.0", "testing"),
            deliveries=[Delivery("customer A", "7.0.0"), Delivery("customer B", "2.0.0"),
                        Delivery("customer C", "2.1.0")])
    out = checks.release_findings(r)
    assert set(codes(out)) == {"line-missing", "state-unknown", "version-duplicate",
                               "delivery-version-unknown", "delivery-version-unreleased"}
    assert all(f.level == "info" for f in out)
    assert {f.title for f in out if f.code == "line-missing"} == {"release 1.0.0: line-missing"}
    assert all(f.key.startswith("release-") for f in out)


def test_release_missing_column():
    out = checks.release_findings(rel(Version("1.0.0", "", "planned"), missing=["versions.line"]))
    assert codes(out) == ["column-missing-versions.line"]
    assert out[0].key == "releases-file/column-missing-versions.line"


def test_findings_carry_no_free_text():
    t = T(summary="<script>x</script>", source="Kunde A", kind="task", state="open", effort="XL")
    r = rel(Version("<b>x</b>", "", "live", notes="Kunde A"), deliveries=[Delivery("Kunde A", "<i>")])
    out = checks.ticket_findings(table(t), rel(V), NOW, 24) + checks.release_findings(r)
    assert out
    for f in out:
        for s in (f.title, f.text, f.key):
            assert "script" not in s and "Kunde" not in s and "<" not in s


def test_emit_once_marker_and_notices(tmp_path):
    f = checks.Finding("T-1/kind-unknown", "kind-unknown", "info", "ticket T-1: kind-unknown", "x")
    checks.emit_once(tmp_path, {"alpha": []}, NOW)
    assert not (tmp_path / "markers" / "tickets.json").exists()
    checks.emit_once(tmp_path, {"alpha": [f]}, NOW)
    checks.emit_once(tmp_path, {"alpha": [f]}, NOW)
    evs = events.read(tmp_path, "alpha")[0]
    assert [e["title"] for e in evs] == ["ticket T-1: kind-unknown"]
    marker = tmp_path / "markers" / "tickets.json"
    assert json.loads(marker.read_text())["noticed"] == ["alpha/T-1/kind-unknown"]
    checks.emit_once(tmp_path, {"alpha": []}, NOW)
    assert json.loads(marker.read_text())["noticed"] == []
    checks.emit_once(tmp_path, {"alpha": [f]}, NOW)
    assert len(events.read(tmp_path, "alpha")[0]) == 2


def test_emit_once_keeps_prefixes(tmp_path):
    marker = tmp_path / "markers" / "tickets.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"noticed": ["alpha/T-1/backport-missing:abc", "alpha/T-2/kind-unknown"]}))
    checks.emit_once(tmp_path, {}, NOW, keep_prefixes=("alpha/T-1/backport-missing:",))
    assert json.loads(marker.read_text())["noticed"] == ["alpha/T-1/backport-missing:abc"]


def test_release_keys_do_not_collide_with_ticket_keys(tmp_path):
    tf = checks.ticket_findings(table(T(nr="x y", state="open")), rel(V), NOW, 24)
    rf = checks.release_findings(rel(Version("a b", "release/x", "live")))
    assert "row1/state-unknown" in [f.key for f in tf]
    assert "release-row1/state-unknown" in [f.key for f in rf]
    assert {f.title for f in tf + rf if f.code == "state-unknown"} == {
        "ticket row1: state-unknown", "release row1: state-unknown"}
    checks.emit_once(tmp_path, {"alpha": tf + rf}, NOW)
    titles = [e["title"] for e in events.read(tmp_path, "alpha")[0]]
    assert titles.count("ticket row1: state-unknown") == 1
    assert titles.count("release row1: state-unknown") == 1


@pytest.fixture
def cherry(monkeypatch):
    calls = []
    answer = {"value": []}

    def fake(folder, line, branch):
        calls.append((folder, line, branch))
        return answer["value"]
    monkeypatch.setattr(checks.effects, "git_cherry", fake)
    fake.calls, fake.answer = calls, answer
    return fake


@pytest.mark.parametrize("version,line", [
    ("1.0.0", "-x"), ("1.0.0", "a;b"), ("1.0.0", "a b"), ("1.0", "release/1.0"), ("1.0.0;x", "release/1.0"),
])
def test_missing_backports_rejects_hostile_values(cherry, tmp_path, version, line):
    assert checks.missing_backports(tmp_path, Version(version, line, "testing")) is None
    assert cherry.calls == []


def test_missing_backports_calls_git_for_valid_values(cherry, tmp_path):
    cherry.answer["value"] = ["abc"]
    assert checks.missing_backports(tmp_path, Version("1.0.0", "release/1.0", "released")) == ["abc"]
    assert cherry.calls == [(tmp_path, "release/1.0", "release/1.0.0")]


def _proj(tmp_path):
    from sf_status.projects import Project
    return Project(name="alpha", title="A", folder=str(tmp_path))


def test_backport_findings_only_testing_and_accepted(cherry, tmp_path):
    cherry.answer["value"] = ["a" * 40, "b" * 40]
    r = rel(Version("1.0.0", "release/1.0", "planned"), Version("1.1.0", "release/1.1", "released"),
            Version("2.0.0", "release/2.0", "testing"))
    found, keep = checks.backport_findings(_proj(tmp_path), r)
    assert [c[2] for c in cherry.calls] == ["release/2.0.0"]
    assert [f.key for f in found] == ["backport-2.0.0/" + "a" * 12 + "/missing",
                                      "backport-2.0.0/" + "b" * 12 + "/missing"]
    f = found[0]
    assert (f.code, f.level, f.title) == ("backport-missing", "warning", "backport 2.0.0: " + "a" * 12 + " missing")
    assert keep == ()


def test_backport_unreachable_returns_keep_prefix(cherry, tmp_path):
    cherry.answer["value"] = None
    found, keep = checks.backport_findings(_proj(tmp_path), rel(Version("2.0.0", "release/2.0", "accepted")))
    assert found == [] and keep == ("alpha/backport-2.0.0/",)


def test_empty_nr_is_invalid_and_critical_unplanned():
    f = run(T(nr="", kind="bug", rank="critical", since="2026-11-01"))
    assert {"number-invalid", "critical-unplanned"} <= set(codes(f))
    assert {x.key for x in f} >= {"row1/number-invalid"}


def test_empty_version_and_delivery_ids_use_fallback():
    r = rel(Version("", "release/1.0", "bogus"), deliveries=[Delivery("customer A", "", "", "", "")])
    keys = [f.key for f in checks.release_findings(r)]
    assert "release-row1/state-unknown" in keys
    assert any(k.startswith("release-delivery1/") for k in keys)


def test_backport_missing_version_column_keeps_prefix(cherry, tmp_path):
    found, keep = checks.backport_findings(_proj(tmp_path), rel(missing=["versions.version"]))
    assert found == [] and keep == ("alpha/backport-",)


def test_release_empty_version_and_customer():
    r = rel(Version("", "release/1.0", "planned"), Version("1.0.0", "release/1.0", "planned"),
            deliveries=[Delivery("", "1.0.0")])
    out = checks.release_findings(r)
    by = {f.code: f for f in out}
    assert by["version-invalid"].key == "release-row1/version-invalid"
    assert by["version-invalid"].text == "release row1: version is empty. See planning/RELEASES.md."
    assert by["customer-missing"].key == "release-delivery1/customer-missing"
    assert "delivery has no customer" in by["customer-missing"].text
    # other formats are not flagged; missing columns switch the rules off
    odd = checks.release_findings(rel(Version("v1", "release/1.0", "planned")))
    assert "version-invalid" not in codes(odd)
    off = checks.release_findings(rel(Version("", "l", "planned"), deliveries=[Delivery("", "1.0.0")],
                                      missing=["versions.version", "deliveries.customer"]))
    assert "version-invalid" not in codes(off) and "customer-missing" not in codes(off)


def test_emit_once_caps_notices(tmp_path):
    fs = [checks.Finding(f"T-{i:02d}/kind-unknown", "kind-unknown", "info", f"ticket T-{i:02d}: kind-unknown", "x")
          for i in range(25)]
    checks.emit_once(tmp_path, {"alpha": fs}, NOW)
    evs = events.read(tmp_path, "alpha")[0]
    assert len(evs) == 21
    assert [e["title"] for e in evs[:20]] == [f.title for f in fs[:20]]
    assert evs[20]["title"] == "5 more findings" and evs[20]["level"] == "info"
    assert evs[20]["text"] == ("5 more findings in planning/TICKETS.md and planning/RELEASES.md "
                               "are not shown one by one.")
    assert len(json.loads((tmp_path / "markers" / "tickets.json").read_text())["noticed"]) == 25
    checks.emit_once(tmp_path, {"alpha": fs}, NOW)
    assert len(events.read(tmp_path, "alpha")[0]) == 21


def test_emit_once_cap_shows_warning_first(tmp_path):
    fs = [checks.Finding(f"T-{i:02d}/kind-unknown", "kind-unknown", "info", f"ticket T-{i:02d}: kind-unknown", "x")
          for i in range(25)]
    w = checks.Finding("T-99/critical-unplanned", "critical-unplanned", "warning", "ticket T-99: critical", "x")
    checks.emit_once(tmp_path, {"alpha": fs + [w]}, NOW)
    evs = events.read(tmp_path, "alpha")[0]
    assert evs[0]["title"] == "ticket T-99: critical"
    assert len(evs) == 21 and evs[20]["title"] == "6 more findings"
