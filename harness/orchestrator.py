# Runs a task with the team: the lead plans, the specialists work in parallel, the checker
# accepts or sends work back, and the results are merged into one FinalReport.
# Roles, prompts and tools all come from the task profile in config.
import asyncio

from harness import config, tools
from harness.agents import run_agent
from harness.budget import Budget
from harness.schemas import CheckerVerdict, FinalReport, Finding, Plan, Subtask, WorkerResult
from harness.state import Run

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# Build an agent's system prompt: shared rules first, then the role's own instructions.
def system_prompt(role: str, allowed: list[str], instructions: str) -> str:
    return config.BASE_PROMPT.format(role=role, tools=", ".join(allowed) or "none") + "\n" + instructions


# Run one task end to end and return the final report.
async def run_task(task: dict, strict_checker: bool = False) -> FinalReport:
    profile = config.PROFILES[task["profile"]]
    run = Run(task["id"], config.ROOT / task["folder"], "multi")
    run_budget = Budget("run", **config.RUN_LIMITS)
    files = ", ".join(tools.list_files(run))
    roles = list(profile["specialists"])

    # 1. The lead looks at the folder and writes one subtask per specialist.
    lead_task = f"Goal: {task['goal']}\nRoles: {', '.join(roles)}"
    plan = await run_agent(run, "lead", system_prompt("lead", profile["lead_tools"], config.LEAD_PROMPT),
                           lead_task, profile["lead_tools"], [run_budget, Budget("lead", **config.AGENT_LIMITS)], Plan)

    # 2. One specialist works on one subtask; the checker accepts it or sends it back.
    async def work_on(subtask: Subtask) -> WorkerResult:
        spec = profile["specialists"][subtask.role]
        system = system_prompt(subtask.role, spec["tools"], spec["prompt"] + "\n" + config.FINDING_FORMAT)
        checker_system = system_prompt("checker", profile["checker_tools"], config.CHECKER_PROMPT)
        worker_budget = Budget(subtask.role, **config.AGENT_LIMITS)
        checker_budget = Budget(f"checker:{subtask.role}", **config.AGENT_LIMITS)
        feedback = ""
        for loop in range(config.MAX_CHECKER_LOOPS + 1):
            work = f"Goal: {task['goal']}\nSubtask: {subtask.instructions}\nFiles in the folder: {files}"
            if feedback:
                work += f"\nChecker feedback on your last answer: {feedback}"
            result = await run_agent(run, subtask.role, system, work, spec["tools"], [run_budget, worker_budget], WorkerResult)
            result.subtask_id = subtask.id
            check = f"Subtask: {subtask.instructions}\nFindings to check:\n{result.model_dump_json()}"
            verdict = await run_agent(run, f"checker:{subtask.role}", checker_system, check, profile["checker_tools"],
                                      [run_budget, checker_budget], CheckerVerdict)
            if strict_checker:  # test flag: the checker rejects everything
                verdict.accept = False
            run.log(f"checker:{subtask.role}", "verdict", status="ok" if verdict.accept else "rejected", output=verdict.feedback)
            if verdict.accept:
                break
            feedback = verdict.feedback
        else:
            # Loop cap hit: keep the work but label it unverified.
            result.status = "unverified"
            run.notes.append(f"{subtask.id}: unverified, checker still rejected after {config.MAX_CHECKER_LOOPS} revisions")
        run.save_subtask(subtask.id, subtask.role, result.status, loop + 1, result.model_dump_json())
        return result

    # 3. All specialists run at the same time; their results are gathered.
    results = await asyncio.gather(*(work_on(s) for s in plan.subtasks))

    # 4. Merge everything into one report.
    report = FinalReport(run_id=run.run_id, status="COMPLETE", findings=merge(results), notes=run.notes)
    run.finish(report.status, report.model_dump_json())
    return report


# Combine findings from all specialists: drop duplicates, put high severity first.
def merge(results: list[WorkerResult]) -> list[Finding]:
    unique = {}
    for finding in (f for r in results for f in r.findings):
        unique.setdefault((finding.file, finding.line, finding.label), finding)
    return sorted(unique.values(), key=lambda f: SEVERITY_ORDER[f.severity])
