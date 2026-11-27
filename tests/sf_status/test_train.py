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
    assert got == utc(2026, 3, 29, 1, 30)


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


def test_train_off_gives_none():
    assert train.check(mk(train=False), {}, utc(2026, 12, 1, 18)) is None


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


def test_time_regex_is_shared_and_ascii_strict():
    from sf_status import projects
    assert train.TIME_RE is projects.TIME_RE
    assert projects.TIME_RE.fullmatch("18:00") and not projects.TIME_RE.fullmatch("18:00\n")
    assert not projects.TIME_RE.fullmatch("1" + chr(0x663) + ":00")


# ---- Task 3: candidates, decide, wave_row, process_answers -------------------------------------

import subprocess
from pathlib import Path

import pytest

from sf_status import effects, events, planning, wave_plan
from sf_status.config import ServerConfig

CANDS = ["2.1.0", "3.0.0"]


@pytest.mark.parametrize("text,want", [
    ("ja, 2.1.0", ("approve", "2.1.0")),
    ("2.1.0 bitte", ("approve", "2.1.0")),
    ("ja 3.0.0 und gut", ("approve", "3.0.0")),
    ("ja, 2.1.0.", ("approve", "2.1.0")),
    ("ja", ("unclear", None)),
    ("2.1.0 oder 3.0.0?", ("unclear", None)),
    ("2.1.0 und 3.0.0", ("unclear", None)),
    ("nein, 2.1.0 noch nicht", ("unclear", None)),
    ("2.1.00", ("unclear", None)),
    ("12.1.0", ("unclear", None)),
    ("2.1.0.1", ("unclear", None)),
    ("Zug ausgesetzt", ("skip", None)),
    ("bitte aussetzen", ("skip", None)),
    ("2.1.0 | x", ("unclear", None)),
    ("ausgesetzt, aber 2.1.0?", ("unclear", None)),
    ("do not release 2.1.0", ("unclear", None)),
    ("wait with 2.1.0", ("unclear", None)),
    ("2.1.0 later", ("unclear", None)),
    ("spaeter 2.1.0", ("unclear", None)),
    ("sp\u00e4ter 2.1.0", ("unclear", None)),
    ("2.1.0 abwarten", ("unclear", None)),
    ("hold 2.1.0", ("unclear", None)),
    ("never 2.1.0", ("unclear", None)),
    ("nie 2.1.0", ("unclear", None)),
    ("2.1.0 ohne Test", ("unclear", None)),
    ("don't release 2.1.0", ("unclear", None)),
    ("don\u2019t release 2.1.0", ("unclear", None)),
    ("dont release 2.1.0", ("unclear", None)),
    ("doesn't work, 2.1.0", ("unclear", None)),
    ("won't do 2.1.0", ("unclear", None)),
])
def test_decide_table(text, want):
    assert train.decide(text, CANDS) == want


def test_decide_without_candidates_never_approves():
    assert train.decide("ja 2.1.0", []) == ("unclear", None)
    assert train.decide("Zug ausgesetzt", []) == ("skip", None)


RELEASES = """# Releases

## Versions

| version | line | state | train | notes |
| --- | --- | --- | --- | --- |
| 2.1.0 | feature/v2.0 | planned | | |
| 2.2.0 | feature/v2.0 | planned | | |
| 3.0.0 | feature/v3.0 | testing | | |
| 3.1.0 | feature/v3.0 | planned | | |
| 2.1 | feature/v4.0 | planned | | |
| 1.0.0 | feature/v1.0 | released | | |
"""


def test_candidates_one_per_line_only_planned():
    got = train.candidates(planning.parse_releases(RELEASES))
    assert [(v.version, v.line) for v in got] == [("2.1.0", "feature/v2.0"), ("3.1.0", "feature/v3.0")]


def test_short_for():
    assert train.short_for("2.1.0") == "zug-2-1-0"


def test_wave_row_follows_header_columns():
    header = ["short", "strand", "approval", "starts when", "branch", "migrations", "may change", "tickets"]
    row = train.wave_row(header, {"short": "zug-2-1-0", "strand": "Release train 2.1.0",
                                  "approval": 'yes - "ja, 2.1.0"', "starts when": "immediately",
                                  "branch": "release/2.1.0", "base": "feature/v2.0", "migrations": "none",
                                  "may change": "release/2.1.0"})
    assert row.count("|") == len(header) + 1
    r = wave_plan.parse_wave_plan("| " + " | ".join(header) + " |\n" + row + "\n")[0]
    assert r.approved and r.short == "zug-2-1-0" and r.branch == "release/2.1.0" and r.tickets == ""


PLAN = ("| short | strand | approval | starts when | branch | base | migrations | may change |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| a | Alpha | no | later | feature/a | | none | x |\n")
NOW = datetime(2026, 12, 1, 18, 30, tzinfo=timezone.utc)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


class World:
    def __init__(self, tmp_path):
        self.repo = tmp_path / "repo"
        (self.repo / "planning").mkdir(parents=True)
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.cfg = ServerConfig(enabled=True, state_dir=self.state, usage_report=False)
        self.plan = self.repo / "planning" / "wave-plan.md"
        self.plan.write_text(PLAN)
        (self.repo / "planning" / "RELEASES.md").write_text(RELEASES)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "init")
        self.project = Project(name="alpha", title="Alpha", folder=str(self.repo), supervisor=True, train=True)
        self.n = 0

    def ask(self, qid="train-2026-12-01", cands=("2.1.0", "3.1.0")):
        events.append(self.state, "alpha", {"kind": "question", "strand": "supervisor", "id": qid,
                                            "question": "q", "background": "b", "recommendation": "r"})
        marker = train.load_marker(self.state)
        entry = marker.setdefault("alpha", {})
        entry.setdefault("dates", {})
        entry.setdefault("questions", {})[qid] = {"state": "open", "candidates": list(cands)}
        train.save_marker(self.state, marker)

    def answer(self, text, qid="train-2026-12-01"):
        events.append(self.state, "alpha", {"kind": "answer", "strand": "supervisor", "question_id": qid, "text": text})

    def run(self, project=None):
        train.process_answers(self.cfg, [project or self.project], self.state, NOW)

    def marker(self):
        return train.load_marker(self.state)["alpha"]

    def commits(self):
        return int(git(self.repo, "rev-list", "--count", "HEAD").strip())

    def rows(self):
        return wave_plan.parse_wave_plan(self.plan.read_text())

    def notices(self):
        return [e for e in events.read(self.state, "alpha")[0] if e["kind"] == "notice"]


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_process_answers_approves_and_commits(w):
    w.ask()
    w.answer("ja, 2.1.0")
    before = w.commits()
    w.run()
    row = w.rows()[-1]
    assert row.short == "zug-2-1-0" and row.approved and row.base == "feature/v2.0" and row.branch == "release/2.1.0"
    assert 'yes - "ja, 2.1.0"' in w.plan.read_text()
    assert w.commits() == before + 1
    assert git(w.repo, "show", "--name-only", "--format=%s", "HEAD").split() == [
        "chore(planning):", "approve", "train", "2.1.0", "planning/wave-plan.md"]
    assert git(w.repo, "status", "--porcelain") == ""
    m = w.marker()
    assert m["questions"]["train-2026-12-01"]["state"] == "approved"
    assert m["questions"]["train-2026-12-01"]["version"] == "2.1.0"
    assert m["dates"]["2026-12-01"] == "approved"


def test_process_answers_idempotent(w):
    w.ask()
    w.answer("ja, 2.1.0")
    w.run()
    n = w.commits()
    w.run()
    assert w.commits() == n and [r.short for r in w.rows()].count("zug-2-1-0") == 1


def test_repeat_after_crash_does_not_duplicate_row(w):
    w.ask()
    w.answer("ja, 2.1.0")
    w.run()
    marker = train.load_marker(w.state)
    marker["alpha"]["questions"]["train-2026-12-01"] = {"state": "open", "candidates": ["2.1.0"]}
    train.save_marker(w.state, marker)
    n = w.commits()
    w.run()
    assert w.commits() == n and w.marker()["questions"]["train-2026-12-01"]["state"] == "approved"


def test_unclear_skip_and_unknown_question(w):
    w.ask("train-2026-12-01")
    w.answer("ja", "train-2026-12-01")
    w.ask("train-2026-12-01-2")
    w.answer("Zug ausgesetzt", "train-2026-12-01-2")
    w.answer("ja, 2.1.0", "train-2026-12-08")  # no marker entry
    before = w.plan.read_text()
    w.run()
    q = w.marker()["questions"]
    assert q["train-2026-12-01"]["state"] == "unclear" and q["train-2026-12-01-2"]["state"] == "skipped"
    assert q["train-2026-12-08"]["state"] == "unclear"
    assert w.plan.read_text() == before
    assert w.marker()["dates"]["2026-12-01"] == "skipped"
    assert [(e["level"], e["title"]) for e in w.notices()] == [("info", "Train 2026-12-01 skipped on your answer")]


def test_pipe_and_newline_in_answer(w):
    w.ask()
    w.answer("ja,\n2.1.0\n")
    w.run()
    assert 'yes - "ja, 2.1.0"' in w.plan.read_text()
    w.ask("train-2026-12-01-2")
    w.answer("ja 3.1.0 | x", "train-2026-12-01-2")
    w.run()
    assert w.marker()["questions"]["train-2026-12-01-2"]["state"] == "unclear"


def test_dirty_wave_plan_waits_and_retries(w):
    w.ask()
    w.answer("ja, 2.1.0")
    w.plan.write_text(PLAN + "| human | edit | no | | | | | |\n")
    mine = w.plan.read_text()
    n = w.commits()
    w.run()
    w.run()
    assert w.plan.read_text() == mine and w.commits() == n
    assert [(e["level"]) for e in w.notices()] == ["warning"] and "local changes" in w.notices()[0]["title"]
    assert w.marker()["questions"]["train-2026-12-01"]["state"] == "open"
    git(w.repo, "checkout", "--", "planning/wave-plan.md")
    w.run()
    assert "zug-2-1-0" in [r.short for r in w.rows()]


def test_commit_failure_restores_file(w, monkeypatch):
    w.ask()
    w.answer("ja, 2.1.0")
    before = w.plan.read_bytes()
    monkeypatch.setattr(effects, "git_commit_path", lambda *a, **k: False)
    w.run()
    w.run()
    assert w.plan.read_bytes() == before
    assert len(w.notices()) == 1 and w.notices()[0]["level"] == "warning"
    assert w.marker()["questions"]["train-2026-12-01"]["state"] == "open"


def test_busy_train_strand_defers(w):
    w.plan.write_text(PLAN + '| zug-2-0-0 | Release train 2.0.0 | yes - "ja" | immediately | release/2.0.0 | | none | x |\n')
    git(w.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-am", "row")
    w.ask()
    w.answer("ja, 2.1.0")
    w.run()
    w.run()
    assert "zug-2-1-0" not in [r.short for r in w.rows()]
    notes = w.notices()
    assert len(notes) == 1 and "zug-2-0-0" in notes[0]["title"] + notes[0]["text"]
    events.append(w.state, "alpha", {"kind": "report", "strand": "zug-2-0-0", "state": "done", "text": "x"})
    w.run()
    assert "zug-2-1-0" in [r.short for r in w.rows()]


def test_train_off_project_ignored(w):
    w.ask()
    w.answer("ja, 2.1.0")
    before = w.plan.read_text()
    w.run(Project(name="alpha", title="Alpha", folder=str(w.repo), supervisor=True, train=False))
    assert w.plan.read_text() == before and w.marker()["questions"]["train-2026-12-01"]["state"] == "open"


def test_open_train_strands_helper(w):
    w.plan.write_text(PLAN + '| zug-2-0-0 | Release train 2.0.0 | yes - "ja" | immediately | release/2.0.0 | | none | x |\n'
                      '| other | O | yes | now | b | | none | x |\n')
    assert train.open_train_strands(w.project, w.state) == ["zug-2-0-0"]
    events.append(w.state, "alpha", {"kind": "report", "strand": "zug-2-0-0", "state": "blocked", "text": "x"})
    assert train.open_train_strands(w.project, w.state) == []
