import json
from pathlib import Path

import pytest

from vw.ir import SceneIR

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(autouse=True)
def _cpu_only(monkeypatch):
    """Make device detection deterministic regardless of the test machine."""
    monkeypatch.setenv("VW_DEVICES", "cpu")


@pytest.fixture
def example_path() -> Path:
    return EXAMPLES / "remove_support.json"


@pytest.fixture
def example_dict(example_path) -> dict:
    return json.loads(example_path.read_text(encoding="utf-8"))


@pytest.fixture
def example_ir(example_path) -> SceneIR:
    return SceneIR.load(example_path)
