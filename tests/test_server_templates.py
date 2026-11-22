import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from sf_status.wave_plan import parse_wave_plan  # noqa: E402

SERVER = ROOT / "templates" / "server"
FILES = ["supervisor-task.md", "wave-plan.md", "strand-start.md", "watcher.sh", "settings.json", "crontab.txt"]
UMLAUTS = "\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df"


def read(name):
    return (SERVER / name).read_text(encoding="utf-8")


def test_server_templates_exist():
    for name in FILES:
        assert (SERVER / name).is_file(), name


def test_no_curly_placeholders_in_server_templates():
    for name in FILES:
        assert "{{" not in read(name), name
        assert not any(c in read(name) for c in UMLAUTS), name


def test_supervisor_task_size_and_triggers():
    text = read("supervisor-task.md")
    assert len(text.encode("utf-8")) <= 6144
    for trigger in ("done:", "blocked:", "answer:", "stall:", "approved:", "retry", "safety"):
        assert trigger in text, trigger
    for command in ("sf-status launch", "sf-status deliver", "sf-status question", "sf-status notice", "notes.md"):
        assert command in text, command


def test_supervisor_task_forbids_dangerous_flag_and_restart():
    text = read("supervisor-task.md")
    assert "--dangerously-skip-permissions" in text
    never = text.split("## Never", 1)[1]
    assert "--dangerously-skip-permissions" in never
    assert "restart" in text.lower()
    assert "force-push" in never.lower()


def test_wave_plan_columns():
    text = read("wave-plan.md")
    header = "| short | strand | approval | starts when | branch | migrations | may change |"
    assert header in text
    rows = parse_wave_plan(text)
    assert len(rows) >= 1
    assert all(not r.approved for r in rows)
    assert "approval" in text.lower() and "quote" in text.lower()


def test_strand_start_parts_and_commands():
    text = read("strand-start.md")
    for needle in ("sf-status report", "sf-status question", "--waiting-for", "heavy-run.sh",
                   "<state-dir>/reports/<project>/<short>.md", "<TOPIC> DONE", "<TOPIC> BLOCKED"):
        assert needle in text, needle
    assert "--dangerously-skip-permissions" in text


def test_settings_json_parses_and_denies_force_push():
    data = json.loads(read("settings.json"))
    deny = " ".join(data["permissions"]["deny"])
    for needle in ("main", "release/", "--force", "reset --hard", "git clean", "rm -rf"):
        assert needle in deny, needle


def test_watcher_has_shebang_and_set_e():
    text = read("watcher.sh")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert re.search(r"^set -e", text, re.M)
    assert "sf-status launch" in text and "sf-status notice" in text and "--level warning" in text


def test_crontab_line():
    text = read("crontab.txt")
    assert text.startswith("PATH=")
    assert ("*/3 * * * * flock -n <state-dir>/run.lock <plugin-dir>/scripts/bin/sf-status run "
            ">> <state-dir>/run.log 2>&1") in text


def test_delegate_work_server_mode():
    text = (ROOT / "skills/delegate-work/SKILL.md").read_text(encoding="utf-8")
    assert "## 5. Server mode" in text and "## 6. Watcher" in text
    for needle in ("sf-status launch", "heavy-run.sh", "reports/", "templates/server/"):
        assert needle in text, needle
    assert len(text.encode("utf-8")) <= 12288
