# Evaluate the team against the single-agent baseline: 3 tasks x 2 modes, real model runs.
# Every run is scored with the same rubric (out of 10) and written to results.md with time,
# tokens and estimated cost. Pauses between runs to respect the free-tier rate limit.
import asyncio
import json
import re

from harness import baseline, config, orchestrator
from run import load_task

CATEGORIES = {"support", "bug", "feature", "spam"}
PAUSE_SECONDS = 10


# Collapse whitespace so a snippet still matches if the model changed indentation.
def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Evidence valid (0-3): share of findings whose snippet really is in the cited file.
def evidence_score(task: dict, findings: list) -> tuple[float, int]:
    folder = config.ROOT / task["folder"]
    valid = 0
    for f in findings:
        path = folder / f.file
        if path.is_file() and squash(f.evidence) and squash(f.evidence) in squash(path.read_text(encoding="utf-8", errors="replace")):
            valid += 1
    return (3 * valid / len(findings) if findings else 0.0), len(findings) - valid


# Fixture repo: a finding matches a planted bug if it is in the same file and names it.
def matches(finding, bug: dict) -> bool:
    text = f"{finding.label} {finding.title}".lower()
    return finding.file == bug["file"] and any(k in text for k in bug["keywords"])


# Accuracy (0-4), false positives (0-2) and prioritization (0-1) for the fixture repo.
def score_fixture(findings: list, answers: dict) -> tuple[float, float, float, str]:
    bugs = answers["bugs"]
    found = [b for b in bugs if any(matches(f, b) for f in findings)]
    unmatched = [f for f in findings if not any(matches(f, b) for b in bugs)]
    high = [b for b in found if b.get("high")]
    high_ok = [b for b in high if any(matches(f, b) and f.severity == "high" for f in findings)]
    accuracy = 4 * len(found) / len(bugs)
    false_pos = 2 * (1 - len(unmatched) / len(findings)) if findings else 0.0
    priority = len(high_ok) / len(high) if high else 0.0
    return accuracy, false_pos, priority, f"found {len(found)}/{len(bugs)}, {len(unmatched)} unmatched"


# Triage rule, the same for both modes: category = the first finding for the file whose label is
# a category; priority = severity of its "priority" finding, or else of that category finding.
def score_triage(findings: list, answers: dict) -> tuple[float, float, float, str]:
    truth = answers["files"]
    right, invented = 0, 0
    true_high = [name for name, t in truth.items() if t["priority"] == "high"]
    high_hit = 0
    for name, t in truth.items():
        mine = [f for f in findings if f.file == name]
        category = next((f for f in mine if f.label.lower() in CATEGORIES), None)
        prio = next((f for f in mine if f.label.lower() == "priority"), category)
        right += bool(category and category.label.lower() == t["category"])
        right += bool(prio and prio.severity == t["priority"])
        high_hit += bool(name in true_high and prio and prio.severity == "high")
    invented = sum(1 for f in findings if f.file not in truth)
    false_pos = 2 * (1 - invented / len(findings)) if findings else 0.0
    return 4 * right / (2 * len(truth)), false_pos, high_hit / len(true_high), f"{right}/{2 * len(truth)} labels right"


# Score one report. The public repo has no answer file: accuracy is a manual sample (README).
def score(task: dict, report) -> dict:
    evidence, invalid = evidence_score(task, report.findings)
    if "answers" not in task:
        false_pos = 2 * (1 - invalid / len(report.findings)) if report.findings else 0.0
        return {"evidence": evidence, "accuracy": None, "false_pos": false_pos, "priority": None,
                "detail": f"{invalid} invalid snippets; accuracy checked by hand"}
    answers = json.loads((config.ROOT / task["answers"]).read_text(encoding="utf-8"))
    rubric = score_fixture if task["profile"] == "code_review" else score_triage
    accuracy, false_pos, priority, detail = rubric(report.findings, answers)
    return {"evidence": evidence, "accuracy": accuracy, "false_pos": false_pos, "priority": priority,
            "detail": f"{detail}, {invalid} invalid snippets"}


# Time, tokens and estimated cost come from the run's own trace.
def usage(run_id: str) -> dict:
    events = [json.loads(line) for line in (config.RUNS_DIR / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()]
    steps = [e for e in events if e["event_type"] == "llm_step"]
    return {"seconds": events[-1]["ts"] - events[0]["ts"], "steps": len(steps),
            "tokens": sum(e["input_tokens"] + e["output_tokens"] for e in steps),
            "cost": sum(e["est_cost_usd"] for e in steps)}


# Run every task in both modes, then write results.md.
async def main() -> None:
    rows = []
    for task_id in ("fixture_repo", "public_repo", "triage_inbox"):
        task = load_task(task_id)
        for mode in ("multi", "single"):
            print(f"running {task_id} {mode} ...", flush=True)
            report = await (orchestrator.run_task(task) if mode == "multi" else baseline.run_single(task))
            rows.append({"task": task_id, "mode": mode, "status": report.status, "run_id": report.run_id,
                         "findings": len(report.findings), **score(task, report), **usage(report.run_id)})
            print(f"  {report.status}, {len(report.findings)} findings", flush=True)
            await asyncio.sleep(PAUSE_SECONDS)

    # One table row per run. A None score is a manual check, shown as "manual".
    num = lambda v, d=1: "manual" if v is None else f"{v:.{d}f}"
    lines = [f"# Results\n\nModel `{config.MODEL}` for every agent. Cost is **estimated at paid prices**; "
             "the free tier cost $0.\n",
             "| task | mode | status | evidence /3 | accuracy /4 | false pos. /2 | priority /1 | total /10 | "
             "findings | seconds | steps | tokens | est. cost USD | run | detail |",
             "|" + "---|" * 15]
    for r in rows:
        parts = [r["evidence"], r["accuracy"], r["false_pos"], r["priority"]]
        total = "manual" if None in parts else f"{sum(parts):.1f}"
        lines.append(f"| {r['task']} | {r['mode']} | {r['status']} | {num(r['evidence'])} | {num(r['accuracy'])} | "
                     f"{num(r['false_pos'])} | {num(r['priority'])} | {total} | {r['findings']} | {r['seconds']:.0f} | "
                     f"{r['steps']} | {r['tokens']} | {r['cost']:.4f} | `{r['run_id']}` | {r['detail']} |")
    (config.ROOT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote results.md")


if __name__ == "__main__":
    asyncio.run(main())
