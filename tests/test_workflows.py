from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def test_workflows_exist():
    assert WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "jobs" in data
