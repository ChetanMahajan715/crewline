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


# A tiny code folder used as the task in most tests.
def make_task(tmp_path, profile="code_review", **files) -> dict:
    folder = tmp_path / "repo"
    folder.mkdir(exist_ok=True)
    for name, text in (files or {"app.py": "password = 'hunter2'\n"}).items():
        (folder / name).write_text(text, encoding="utf-8")
    return {"id": "t", "profile": profile, "folder": str(folder), "goal": "Review this code."}


# A finding whose evidence really is in app.py.
FINDING = {"title": "Hardcoded password", "label": "hardcoded_secret", "severity": "high",
           "file": "app.py", "line": 1, "evidence": "password = 'hunter2'", "explanation": "Secret in code."}


# Read the JSONL trace of a run back as a list of events.
def trace(report) -> list[dict]:
    path = config.RUNS_DIR / f"{report.run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# Happy path: lead plans, a specialist reads a file and reports, state and trace are saved.
async def test_happy_path_report_state_and_trace():
    from harness import orchestrator, state
    task = make_task(config.SANDBOX_DIR.parent)
    llm.MOCK_SCRIPT["security"] = [{"tool": "read_file", "args": {"path": "app.py"}}, {"final": {"findings": [FINDING]}}]
    report = await orchestrator.run_task(task)
    assert report.status == "COMPLETE" and report.findings[0].title == "Hardcoded password"
    events = trace(report)
    assert {"lead", "security"} <= {e["agent"] for e in events}
    assert any(e["event_type"] == "tool_call" and e["tool"] == "read_file" for e in events)
    row = state.connect().execute("SELECT status FROM runs WHERE run_id = ?", (report.run_id,)).fetchone()
    assert row == ("COMPLETE",)
