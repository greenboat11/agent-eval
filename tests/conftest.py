import pytest
from pathlib import Path


@pytest.fixture
def tmp_workspace(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "reports").mkdir()
    return tmp_path
