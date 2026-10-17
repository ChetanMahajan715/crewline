# Replay a run from its JSONL trace: a coloured timeline of every step, then totals per agent.
# Colours follow brand/BRAND.md and always come with a word, never colour alone.
# Example: python replay.py runs\20261016-215324-fixture_repo-multi.jsonl
import json
import sys
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Trace status -> Rich colour (green ok, yellow retry, red error/denied, magenta injection, cyan approval).
COLOURS = {"ok": "green", "retry": "yellow", "rejected": "yellow", "error": "red", "denied": "red",
           "blocked": "red", "injection": "magenta", "approval": "cyan"}


# Read the trace file into a list of events.
def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# Print one line per event, then a totals table.
def replay(path: Path) -> None:
    console = Console()
    events = load(path)
    start = events[0]["ts"]
    totals = defaultdict(lambda: {"steps": 0, "tokens": 0, "cost": 0.0, "seconds": 0.0})
    for e in events:
        colour = COLOURS.get(e["status"], "white")
        tool = f" {e['tool']}({json.dumps(e['tool_args'])})" if e["tool_args"] else (f" {e['tool']}" if e["tool"] else "")
        detail = (e["output"] or "").replace("\n", " ")[:90]
        console.print(f"[dim]{e['ts'] - start:7.2f}s[/] [{colour}]{e['status'].upper():9}[/] "
                      f"{e['agent']:18} {e['event_type']:19}{tool} [dim]{detail}[/]", highlight=False)
        # Add model calls to the per-agent totals.
        if e["event_type"] == "llm_step":
            t = totals[e["agent"]]
            t["steps"] += 1
            t["tokens"] += e["input_tokens"] + e["output_tokens"]
            t["cost"] += e["est_cost_usd"]
            t["seconds"] += e["seconds"]

    # Totals per agent and for the whole run.
    table = Table("agent", "steps", "tokens", "est. cost USD*", "model seconds", title=f"Totals: {path.stem}")
    for agent, t in totals.items():
        table.add_row(agent, str(t["steps"]), str(t["tokens"]), f"{t['cost']:.4f}", f"{t['seconds']:.1f}")
    table.add_row("ALL", *(str(sum(t[k] for t in totals.values())) for k in ("steps", "tokens")),
                  f"{sum(t['cost'] for t in totals.values()):.4f}", f"{events[-1]['ts'] - start:.1f} wall")
    console.print(table)
    console.print(f"Final status: {events[-1]['status']}   *estimated at paid prices; the free tier costs $0")


if __name__ == "__main__":
    # Needs exactly one trace file; otherwise explain how to call it.
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        raise SystemExit("Usage: python replay.py runs\\<run id>.jsonl  (the id is printed at the end of every run)")
    replay(Path(sys.argv[1]))
