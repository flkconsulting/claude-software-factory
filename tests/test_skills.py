import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ["delegate-work", "ship-release", "workflow-retrospective", "pre-check", "error-index"]
UMLAUTS = "\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df"


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"no frontmatter in {path}"
    data = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


def test_skill_frontmatter():
    found = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
    assert found == sorted(SKILLS)
    for name in SKILLS:
        data = frontmatter(ROOT / "skills" / name / "SKILL.md")
        assert data["name"] == name
        assert len(data["description"]) >= 80
        assert data["description"].startswith("Use when")


def test_skills_have_no_umlauts():
    for name in SKILLS:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert not any(c in text for c in UMLAUTS)


def test_delegate_work_contract():
    text = (ROOT / "skills/delegate-work/SKILL.md").read_text(encoding="utf-8")
    assert "<TOPIC> DONE" in text and "<TOPIC> BLOCKED" in text
    assert "model" in text and "worktree" in text


def test_pre_check_contract():
    text = (ROOT / "skills/pre-check/SKILL.md").read_text(encoding="utf-8")
    assert "open" in text
    for heading in [
        "Does it already exist",
        "Does it fit",
        "Official documentation",
        "Prior art",
        "Cause or requirement",
    ]:
        assert heading in text
    lowered = text.lower()
    for forbidden in ["%", "score", "confidence"]:
        assert forbidden not in lowered


def test_error_index_contract():
    text = (ROOT / "skills/error-index/SKILL.md").read_text(encoding="utf-8")
    for needle in ["error_index.py", "search", "add", "${CLAUDE_SKILL_DIR}", "secrets"]:
        assert needle in text
