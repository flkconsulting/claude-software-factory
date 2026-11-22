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
    text = text.replace("software-factory@claude-software-factory", "")
    assert not re.search(r"\b[\w.-]+@[\w-]+(\.[\w-]+)*\b", text)
