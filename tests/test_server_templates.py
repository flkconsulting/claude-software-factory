import json
import os
import re
import subprocess
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


def _denied(command, patterns):
    for pat in patterns:
        inner = pat[len("Bash("):-1]
        if inner.endswith(":*"):
            inner = inner[:-2] + " *"
        regex = ".*".join(re.escape(part) for part in inner.split("*"))
        if re.fullmatch(regex, command):
            return True
    return False


def test_settings_json_parses_and_denies_force_push():
    data = json.loads(read("settings.json"))
    deny = data["permissions"]["deny"]
    blocked = [
        "git push origin main", "git push -u origin main", "git push origin feature:main",
        "git push origin HEAD:refs/heads/main", "git push origin +main", "git push --force origin x",
        "git push --force-with-lease origin", "git push -f origin x", "git push origin x --force",
        "git push origin release/1.0", "git push origin HEAD:release/1.0",
        "git reset --hard HEAD~1", "git clean -fd", "rm -rf x", "rm -fr x", "rm -r -f x",
        "git push --no-verify origin feature/x", "git push origin feature/x --no-verify",
        "git commit -m x --no-verify", "git commit --no-verify -m x",
    ]
    for command in blocked:
        assert _denied(command, deny), command
    for command in ("git push origin feature/x", "git push -u origin feature/y", "git status", "rm x"):
        assert not _denied(command, deny), command


def _run_watcher(tmp_path, now, precondition, timeout=10):
    fake = tmp_path / "sf-status"
    fake.write_text('#!/usr/bin/env bash\necho "$@" >> "$0.log"\n', encoding="utf-8")
    fake.chmod(0o755)
    env = {**os.environ, "SF_STATUS": str(fake), "SF_WATCHER_NOW": now, "SF_WATCHER_POLL": "0.1"}
    cmd = ["bash", str(SERVER / "watcher.sh"), "08:00", "proj", "s1", "sonnet", str(tmp_path), "topic", precondition]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    log = tmp_path / "sf-status.log"
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


def test_watcher_late_start_launches_immediately(tmp_path):
    result, log = _run_watcher(tmp_path, "09:30", "true")
    assert result.returncode == 0
    assert log.startswith("launch --project proj --short s1")


def test_watcher_failed_precondition_notices(tmp_path):
    result, log = _run_watcher(tmp_path, "09:30", "false")
    assert result.returncode == 0
    assert log.startswith("notice --project proj") and "--level warning" in log


def test_watcher_waits_before_the_time(tmp_path):
    import pytest

    with pytest.raises(subprocess.TimeoutExpired):
        _run_watcher(tmp_path, "07:00", "true", timeout=1)
    assert not (tmp_path / "sf-status.log").exists()


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


def test_strand_start_has_model_and_report_order():
    text = read("strand-start.md")
    assert "**Model:** <haiku|sonnet|opus>" in text
    step = text.split("8. **Report:**", 1)[1].split("## Status reporting", 1)[0]
    assert "before" in step and "report --state done" in step
    assert step.index("file") < step.index("report --state done")


def test_supervisor_task_model_worktree_and_answers():
    text = read("supervisor-task.md")
    assert "**Model:**" in text and "start file" in text
    assert "git worktree add -b" in text and "<project-folder>-<short>" in text
    assert "never the project folder" in text
    assert "<state-dir>" in text
    assert "answer:<question-id>" in text and len(text.encode("utf-8")) <= 6144


def test_deny_list_covers_no_verify():
    deny = json.loads(read("settings.json"))["permissions"]["deny"]
    assert "Bash(git push *--no-verify*)" in deny and "Bash(git commit *--no-verify*)" in deny
