# The single-agent baseline, for a fair comparison with the team: one agent, one prompt that
# lists every specialist's job, the union of the same tools, the same model, the same run budget.
# No lead, no parallel work, no checker.
from harness import config, tools
from harness.agents import run_agent
from harness.budget import Budget, BudgetExceeded
from harness.orchestrator import merge, system_prompt, with_retries
from harness.schemas import FinalReport, WorkerResult
from harness.state import Run


# Run one task with a single agent and return a report in the same format as the team.
async def run_single(task: dict, limits: dict | None = None) -> FinalReport:
    profile = config.PROFILES[task["profile"]]
    run = Run(task["id"], config.ROOT / task["folder"], "single")
    budget = Budget("run", **{**config.RUN_LIMITS, **(limits or {})})
    run.log("harness", "run_start", input=task)

    # Every tool any team member has, and every specialist's job, in one prompt.
    allowed = sorted({t for spec in profile["specialists"].values() for t in spec["tools"]}
                     | set(profile["lead_tools"]) | set(profile["checker_tools"]))
    jobs = "\n".join(f"- {role}: {spec['prompt']}" for role, spec in profile["specialists"].items())
    work = f"Goal: {task['goal']}\nDo all of these jobs:\n{jobs}\nFiles in the folder: {', '.join(tools.list_files(run))}"
    system = system_prompt("single", allowed, config.SINGLE_PROMPT)

    # Same retries as the team; a hit budget or a final failure is labelled honestly.
    status, findings, missing = "COMPLETE", [], []
    try:
        result = await with_retries(run, "single", lambda: run_agent(run, "single", system, work, allowed, [budget], WorkerResult))
        findings = merge([result])
    except BudgetExceeded as error:
        status, missing = f"STOPPED: {error.limit}", [f"single: {error.limit} limit hit"]
        run.log("harness", "budget_stop", status="error", output=error.limit)
    except Exception as error:
        status, missing = "PARTIAL", [f"single: {type(error).__name__}: {error}"]
    report = FinalReport(run_id=run.run_id, status=status, findings=findings, missing=missing, notes=run.notes)
    run.finish(report.status, report.model_dump_json())
    return report
