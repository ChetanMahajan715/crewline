# Shared state and trace logging. SQLite (runs.db) is the one inspectable place for shared
# state: runs, subtasks and approvals. The trace runs/<run_id>.jsonl has one line per event,
# which is what replay.py and app.py read.
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from harness import config

# The three tables of shared state.
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, task_id TEXT, mode TEXT, status TEXT, report TEXT);
CREATE TABLE IF NOT EXISTS subtasks (run_id TEXT, subtask_id TEXT, role TEXT, status TEXT, attempts INTEGER,
    result TEXT, PRIMARY KEY (run_id, subtask_id));
CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, agent TEXT,
    action TEXT, status TEXT);
"""

# Every trace line has these keys, so all lines look the same.
EVENT_KEYS = ["input", "tool", "tool_args", "output", "input_tokens", "output_tokens", "est_cost_usd", "seconds"]


# Open the database and create the tables if they are missing.
def connect() -> sqlite3.Connection:
    db = sqlite3.connect(config.DB_PATH)
    db.executescript(SCHEMA)
    return db


# Cut long text so the trace stays readable.
def short(value, limit: int = 600) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


class Run:
    # Start a run: pick an id, open the trace file and record the run in SQLite.
    def __init__(self, task_id: str, folder: Path, mode: str):
        self.run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{task_id}-{mode}"
        self.folder = Path(folder).resolve()
        self.notes: list[str] = []
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.trace_path = config.RUNS_DIR / f"{self.run_id}.jsonl"
        self.db = connect()
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, 'RUNNING', '')", (self.run_id, task_id, mode))
        self.db.commit()

    # Append one event to the JSONL trace.
    def log(self, agent: str, event_type: str, status: str = "ok", **fields) -> None:
        event = {"ts": round(time.time(), 3), "run_id": self.run_id, "agent": agent, "event_type": event_type,
                 **{key: fields.get(key) for key in EVENT_KEYS}, "status": status}
        for key in ("input", "output"):
            if event[key] is not None:
                event[key] = short(event[key])
        with self.trace_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event) + "\n")

    # Save or update one subtask row.
    def save_subtask(self, subtask_id: str, role: str, status: str, attempts: int, result: str = "") -> None:
        self.db.execute("INSERT OR REPLACE INTO subtasks VALUES (?, ?, ?, ?, ?, ?)",
                        (self.run_id, subtask_id, role, status, attempts, result))
        self.db.commit()

    # Record the final status and report.
    def finish(self, status: str, report_json: str) -> None:
        self.db.execute("UPDATE runs SET status = ?, report = ? WHERE run_id = ?", (status, report_json, self.run_id))
        self.db.commit()
        self.log("harness", "run_end", status=status, output=report_json)
