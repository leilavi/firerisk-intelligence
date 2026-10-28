import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SNAPSHOT = ROOT / "data" / "private" / "snapshot"


@pytest.fixture(autouse=True)
def _no_background_translation(monkeypatch):
    """Background translation is off unless a test turns it on (it would add AI calls that other tests count)."""
    monkeypatch.setenv("FIRERISK_AUTO_TRANSLATE", "0")
