# Tests for agent-harness. They use only the mock provider: no network, no API key, fast.
# Each test sends files, logs and the database to a temporary folder.
import json

import pytest

from harness import config, llm


# Before every test: mock provider, temp folders, tiny backoff, empty mock script.
@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROVIDER", "mock")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "runs.db")
    monkeypatch.setattr(config, "SANDBOX_DIR", tmp_path / "sandbox")
    monkeypatch.setattr(config, "BACKOFF_SECONDS", [0.01, 0.02, 0.04])
    monkeypatch.setattr(llm, "MOCK_SCRIPT", {})
    monkeypatch.setattr(llm, "MOCK_DELAY_SECONDS", 0.0)
    (tmp_path / "sandbox").mkdir()
    return tmp_path


# The mock replays scripted replies first, then falls back to a default per role.
async def test_mock_scripted_then_default():
    llm.MOCK_SCRIPT["security"] = [{"tool": "read_file", "args": {"path": "a.py"}}]
    text, in_tokens, out_tokens, _ = await llm.call_llm("sys", [{"role": "user", "content": "go"}], "security")
    assert json.loads(text)["tool"] == "read_file" and in_tokens > 0 and out_tokens > 0
    text, *_ = await llm.call_llm("sys", [{"role": "user", "content": "go"}], "security")
    assert json.loads(text) == {"final": {"findings": []}}
