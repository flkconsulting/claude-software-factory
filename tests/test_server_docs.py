import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_setup_offers_variant_b():
    text = (ROOT / "commands" / "setup-workflow.md").read_text(encoding="utf-8")
    assert "not yet available" not in text
    assert "sf-status project add" in text
    assert "crontab" in text
    assert "never installs" in text


def test_server_setup_doc_sections():
    text = (ROOT / "docs" / "05-server-setup.md").read_text(encoding="utf-8")
    headings = [h.lower() for h in re.findall(r"^#{1,3} (.+)$", text, re.M)]
    for word in ("prerequisites", "login", "cron", "answering", "switching off", "security"):
        assert any(word in h for h in headings), word


def test_server_doc_has_no_ip_or_hostname():
    text = (ROOT / "docs" / "05-server-setup.md").read_text(encoding="utf-8")
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text)
    for plugin in ("software-factory@claude-software-factory", "superpowers@claude-plugins-official"):
        text = text.replace(plugin, "")
    assert not re.search(r"\b[\w.-]+@[\w-]+(\.[\w-]+)*\b", text)


def _doc():
    return (ROOT / "docs" / "05-server-setup.md").read_text(encoding="utf-8")


def test_doc_has_supervisor_switch_on_section():
    text = _doc()
    section = text.split("## Switching the supervisor on", 1)[1].split("\n## ", 1)[0]
    for needle in ("--supervisor yes", "--approval-quote", "sf-status project remove", "sf-status wake fast-forward",
                   '"supervisor": true'):
        assert needle in section, needle


def test_doc_security_wording_is_honest():
    text = _doc()
    assert "The real guards are the pre-push hook" not in text
    assert "receive.denyNonFastForwards" in text and "receive.denyDeletes" in text
    assert "refs/heads/main" in text and "--no-verify" in text and "branch protection" in text
    assert "Replace `<state-dir>` replaced" not in text


def test_doc_worktree_trust_note():
    text = _doc()
    assert "folder-trust dialog" in text and "acceptance run" in text


def test_doc_acceptance_fixes():
    text = _doc()
    assert "8.19 or newer" in text and "gitleaks git --help" in text
    assert '"additionalDirectories": ["<state-dir>"]' in text
    assert "claude plugin list" in text and "superpowers@claude-plugins-official" in text
    assert "git merge --ff-only <other-branch>" not in text
    assert "branch, base, migrations" in text and "worktree add -b <branch> <project-folder>-<short> [<base>]" in text


def test_setup_and_skill_wording_consistent():
    setup = (ROOT / "commands" / "setup-workflow.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "delegate-work" / "SKILL.md").read_text(encoding="utf-8")
    assert "are the real guard" not in setup and "are the real guard" not in skill
    assert "the pre-push hook and branch protection are the real guard" not in skill
    assert "project's `.claude/settings.json`" not in skill and "settings.json" in skill
    assert "`<state-dir>`" in setup.split("11. **Wave plan", 1)[1].split("12. **", 1)[0]


def test_doc_local_steps_section():
    text = _doc()
    assert "\n## Local steps" in text
    section = text.split("\n## Local steps", 1)[1].split("\n## ", 1)[0]
    for needle in ("local_notice_hours", "local-watch.sh", "sf-status local pending", "run_in_background",
                   "shared remote", "SF_LOCAL_WATCH_SSH_TIMEOUT", "SF_LOCAL_WATCH_REMOTE=", "withdrawn", "information only", "| ssh <ssh-target> sf-status deliver", "exit code 10", "exit code 11", "exit code 12"):
        assert needle in section, needle


def test_readme_lists_local_watcher():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    table = text.split("## What is in the box", 1)[1].split("\n## ", 1)[0]
    assert "local-watch.sh" in table
