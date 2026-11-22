import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from sf_status.config import ServerConfig  # noqa: E402


@pytest.fixture
def state(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def cfg(tmp_path) -> ServerConfig:
    return ServerConfig(enabled=True, state_dir=tmp_path)
