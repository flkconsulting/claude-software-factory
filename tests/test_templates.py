import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
SETUP = ROOT / "commands" / "setup-workflow.md"
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def test_each_rule_has_why_line():
    rules = sorted((TEMPLATES / "rules").glob("*.md"))
    assert len(rules) == 5
    for rule in rules:
        lines = rule.read_text(encoding="utf-8").splitlines()
        assert any(line.startswith("**Why:**") for line in lines), rule.name


def test_placeholders_declared():
    used = set()
    for f in TEMPLATES.rglob("*.md"):
        used |= set(PLACEHOLDER.findall(f.read_text(encoding="utf-8")))
    table = {
        m.group(1)
        for line in SETUP.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("|")
        for m in PLACEHOLDER.finditer(line)
    }
    assert used and used <= table, used - table


def test_claude_md_has_header_placeholders():
    text = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
    for name in ("USER_NAME", "REPLY_LANGUAGE", "ADDRESS_FORM", "PUSH_POLICY", "AUTONOMY_LIMITS"):
        assert "{{" + name + "}}" in text


def test_planning_ids_documented():
    text = (TEMPLATES / "planning" / "README.md").read_text(encoding="utf-8")
    for ident in ("D-", "Q-", "F-"):
        assert ident in text
    assert "agents never write a D-entry themselves" in text


def test_setup_command_references_templates_via_plugin_root():
    text = SETUP.read_text(encoding="utf-8")
    root = "${CLAUDE_PLUGIN_ROOT}/templates/"
    assert "in the plugin directory under" not in text
    for ref in ("AGENTS.md", "project-CLAUDE.md", "planning/", "CLAUDE.md", "rules/"):
        assert root + ref in text, ref
    # no bare relative template paths remain
    assert not re.search(r"(?<!/)`templates/", text)


def test_setup_forbids_copying_example_lines():
    text = SETUP.read_text(encoding="utf-8")
    assert "Lines starting with `Example:`" in text
    assert "never copy them into a written file" in text


def test_planning_push_rule_is_a_declared_placeholder_in_both_templates():
    setup = SETUP.read_text(encoding="utf-8")
    row = next(l for l in setup.splitlines() if l.startswith("| `{{PLANNING_PUSH_RULE}}`"))
    assert "Separate planning repository" in row and "follow the push policy" in row
    for rel in ("AGENTS.md", "planning/README.md"):
        text = (TEMPLATES / rel).read_text(encoding="utf-8")
        assert "{{PLANNING_PUSH_RULE}}" in text, rel
        assert "push to the planning folder without asking" not in text
        assert "pull first, then commit and push" not in text


def test_push_policy_split_and_autonomy_default_consistent():
    setup = SETUP.read_text(encoding="utf-8")
    push = next(l for l in setup.splitlines() if l.startswith("| `{{PUSH_POLICY}}`"))
    assert "Default:" in push and "Alternative:" in push
    auton = next(l for l in setup.splitlines() if l.startswith("| `{{AUTONOMY_LIMITS}}`"))
    assert "except as allowed by the push policy" in auton


def test_no_source_product_domain_in_templates_and_docs():
    for f in list(TEMPLATES.rglob("*.md")) + list((ROOT / "docs").glob("*.md")):
        low = f.read_text(encoding="utf-8").lower()
        assert "obligations from contracts" not in low, f
        assert "real contract" not in low, f
        assert "price per contract" not in low, f


def test_error_index_template_listed_and_empty():
    index = TEMPLATES / "planning" / "ERRORS.jsonl"
    assert index.exists()
    assert index.read_text(encoding="utf-8") == ""
    readme = (TEMPLATES / "planning" / "README.md").read_text(encoding="utf-8")
    assert "ERRORS.jsonl" in readme


def test_agents_template_points_to_pre_check_and_error_index():
    text = (TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")
    assert "pre-check" in text
    assert "error-index" in text


def test_definition_of_done_covers_every_requirement():
    text = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
    section = text.split("## 13. Definition of done", 1)[1].split("\n## ", 1)[0]
    assert (
        "Every requirement checked off against the implementation; no unverified assumption"
        in section
    )


def test_setup_mentions_error_index():
    text = SETUP.read_text(encoding="utf-8")
    assert "ERRORS.jsonl" in text
    assert "error-index" in text


def test_agents_template_local_commands():
    text = (TEMPLATES / "AGENTS.md").read_text(encoding="utf-8")
    assert "| Name | Where | Command | Result |" in text
    assert "server" in text and "local" in text
    assert "must be repeatable" in text
    assert "Example: extension-install | local |" in text
    assert set(PLACEHOLDER.findall(text)) == {
        "PROJECT_NAME", "PROJECT_PURPOSE", "PLANNING_LOCATION", "PLANNING_PUSH_RULE", "BUILD_COMMANDS",
    }


def test_launchd_plist_valid():
    import plistlib

    raw = (TEMPLATES / "launchd" / "reminders.plist").read_text(encoding="utf-8")
    filled = raw.replace("{{PYTHON}}", "/usr/bin/python3").replace("{{HOME}}", "/Users/someone")
    assert not PLACEHOLDER.search(filled)
    data = plistlib.loads(filled.encode("utf-8"))
    assert data["Label"] == "software-factory.reminders"
    args = data["ProgramArguments"]
    assert args[0] == "/usr/bin/python3"
    assert args[1] == "/Users/someone/.claude/software-factory/bin/reminders.py"
    assert "--notify" in args
    assert data["StartCalendarInterval"] == {"Hour": 9, "Minute": 7}
    assert data["RunAtLoad"] is True
    assert data["StandardErrorPath"].endswith("/state/reminders-launchd.log")


def test_setup_mentions_reminders():
    text = SETUP.read_text(encoding="utf-8")
    for needle in (
        "reminders.md",
        "templates/launchd/reminders.plist",
        "launchctl bootstrap",
        "launchctl bootout",
    ):
        assert needle in text, needle


def test_global_rule_reminders():
    text = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
    assert "~/.claude/reminders.md" in text
    assert "CronCreate" in text
    assert "across sessions" in text
