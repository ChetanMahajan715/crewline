# Command line entry point for agent-harness: run one task from tasks/tasks.json with the team
# (or the single-agent baseline) and print the final report. The test flags simulate failures.
# Example: python run.py --task fixture_repo --provider mock
import argparse
import asyncio
import json
import subprocess

from rich.console import Console
from rich.table import Table

from harness import config, orchestrator

STATUS_COLOURS = {"COMPLETE": "green", "PARTIAL": "yellow", "STOPPED": "red"}
console = Console()


# Find a task by id. If it names a public repo, the harness (not an agent) clones it first.
def load_task(task_id: str) -> dict:
    task = next(t for t in json.loads(config.TASKS_FILE.read_text(encoding="utf-8")) if t["id"] == task_id)
    folder = config.ROOT / task["folder"]
    if "clone_url" in task and not folder.exists():
        subprocess.run(["git", "clone", "--quiet", task["clone_url"], str(folder)], check=True)
        subprocess.run(["git", "-C", str(folder), "checkout", "--quiet", task["commit"]], check=True)
    return task


# Print the report: status word in its brand colour, then a findings table, missing work and notes.
def show(report) -> None:
    colour = STATUS_COLOURS[report.status.split(":")[0]]
    console.print(f"[bold {colour}]{report.status}[/]  run {report.run_id}")
    table = Table("severity", "label", "file:line", "title")
    for f in report.findings:
        table.add_row(f.severity, f.label, f"{f.file}:{f.line or '-'}", f.title)
    console.print(table)
    for item in report.missing:
        console.print(f"[yellow]MISSING[/] {item}")
    for note in report.notes:
        colour = "magenta" if "injection" in note else "yellow"
        console.print(f"[{colour}]NOTE[/] {note}")
    console.print(f"Replay: python replay.py runs\\{report.run_id}.jsonl")


# Read the flags, apply them to config, run the task.
def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-harness", description="agent-harness: a small multi-agent "
                                     "harness with budgets, retries, safety controls and replayable logs.")
    parser.add_argument("--task", required=True, help="task id from tasks/tasks.json")
    parser.add_argument("--provider", choices=["mistral", "mock"], default=config.PROVIDER)
    parser.add_argument("--max-seconds", type=float, help="run time limit")
    parser.add_argument("--max-tokens", type=int, help="run token limit")
    parser.add_argument("--max-steps", type=int, help="run step limit")
    parser.add_argument("--fail-agent", help="this role always errors (shows retries, then PARTIAL)")
    parser.add_argument("--slow-agent", help="this role sleeps past the timeout")
    parser.add_argument("--strict-checker", action="store_true", help="checker always rejects (shows loop cap)")
    parser.add_argument("--single", action="store_true", help="run the single-agent baseline instead")
    args = parser.parse_args()
    config.PROVIDER = args.provider
    limits = {k: v for k, v in {"max_seconds": args.max_seconds, "max_tokens": args.max_tokens,
                                "max_steps": args.max_steps}.items() if v is not None}
    task = load_task(args.task)
    report = asyncio.run(orchestrator.run_task(task, strict_checker=args.strict_checker,
                                               fail_agent=args.fail_agent, slow_agent=args.slow_agent, limits=limits))
    show(report)


if __name__ == "__main__":
    main()
