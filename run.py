# Command line entry point for agent-harness: run one task from tasks/tasks.json with the team
# (or the single-agent baseline) and print the final report. The test flags simulate failures.
# Example: python run.py --task myrepo --provider mock   (add tasks in tasks/tasks.json first)
import argparse
import asyncio
import json
import os
import subprocess

from rich.console import Console
from rich.table import Table

from harness import baseline, config, orchestrator

STATUS_COLOURS = {"COMPLETE": "green", "PARTIAL": "yellow", "STOPPED": "red"}
console = Console()


# Find a task by id. If it names a public repo, the harness (not an agent) clones it first.
# A wrong id or an empty folder stops with a clear message instead of a confusing result.
def load_task(task_id: str) -> dict:
    tasks = {t["id"]: t for t in json.loads(config.TASKS_FILE.read_text(encoding="utf-8"))}
    if not tasks:
        raise SystemExit("tasks/tasks.json has no tasks yet. Add one first: see docs/GUIDE.md, part 2.")
    if task_id not in tasks:
        raise SystemExit(f"Unknown task '{task_id}'. Available tasks: {', '.join(tasks)}")
    task = tasks[task_id]
    folder = config.ROOT / task["folder"]
    if "clone_url" in task and not folder.exists():
        subprocess.run(["git", "clone", "--quiet", task["clone_url"], str(folder)], check=True)
        subprocess.run(["git", "-C", str(folder), "checkout", "--quiet", task["commit"]], check=True)
    if not folder.is_dir() or not any(folder.iterdir()):
        raise SystemExit(f"Task folder {folder} is missing or empty. Get the test data first: see docs/GUIDE.md, step 2.")
    return task


# A real-model run needs an API key. Stop at once with a clear message instead of failing every call.
def check_api_key() -> None:
    if config.PROVIDER != "mock" and not os.environ.get(config.API_KEY_ENV):
        raise SystemExit(f"No API key: set {config.API_KEY_ENV} in the .env file (see docs/GUIDE.md, step 1.4), "
                         "or add --provider mock to run offline.")


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
    check_api_key()
    limits = {k: v for k, v in {"max_seconds": args.max_seconds, "max_tokens": args.max_tokens,
                                "max_steps": args.max_steps}.items() if v is not None}
    task = load_task(args.task)
    if args.single:
        report = asyncio.run(baseline.run_single(task, limits=limits))
    else:
        report = asyncio.run(orchestrator.run_task(task, strict_checker=args.strict_checker,
                                                   fail_agent=args.fail_agent, slow_agent=args.slow_agent, limits=limits))
    show(report)


if __name__ == "__main__":
    main()
