import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import gate  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_logs(tmp_path, monkeypatch):
    """Keep test runs out of the real logs/."""
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "RUNS_LOG", tmp_path / "logs" / "runs.jsonl")
    monkeypatch.setattr(gate, "GATE_LOG", tmp_path / "logs" / "gate.jsonl")
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path / "logs"
