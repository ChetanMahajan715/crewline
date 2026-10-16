# Runs a task with the team: the lead plans, the specialists work, the results are merged
# into one FinalReport. Roles, prompts and tools all come from the task profile in config.
from harness import config, tools
from harness.agents import run_agent
from harness.budget import Budget
from harness.schemas import FinalReport, Finding, Plan, WorkerResult
from harness.state import Run

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# Build an agent's system prompt: shared rules first, then the role's own instructions.
def system_prompt(role: str, allowed: list[str], instructions: str) -> str:
    return config.BASE_PROMPT.format(role=role, tools=", ".join(allowed) or "none") + "\n" + instructions


# Run one task end to end and return the final report.
async def run_task(task: dict) -> FinalReport:
    profile = config.PROFILES[task["profile"]]
    run = Run(task["id"], config.ROOT / task["folder"], "multi")
    run_budget = Budget("run", **config.RUN_LIMITS)
    files = ", ".join(tools.list_files(run))
    roles = list(profile["specialists"])

    # 1. The lead looks at the folder and writes one subtask per specialist.
    lead_task = f"Goal: {task['goal']}\nRoles: {', '.join(roles)}"
    plan = await run_agent(run, "lead", system_prompt("lead", profile["lead_tools"], config.LEAD_PROMPT),
                           lead_task, profile["lead_tools"], [run_budget, Budget("lead", **config.AGENT_LIMITS)], Plan)

    # 2. Each specialist works on its subtask.
    results = []
    for subtask in plan.subtasks:
        spec = profile["specialists"][subtask.role]
        system = system_prompt(subtask.role, spec["tools"], spec["prompt"] + "\n" + config.FINDING_FORMAT)
        work = f"Goal: {task['goal']}\nSubtask: {subtask.instructions}\nFiles in the folder: {files}"
        result = await run_agent(run, subtask.role, system, work, spec["tools"],
                                 [run_budget, Budget(subtask.role, **config.AGENT_LIMITS)], WorkerResult)
        result.subtask_id = subtask.id
        run.save_subtask(subtask.id, subtask.role, result.status, 1, result.model_dump_json())
        results.append(result)

    # 3. Merge everything into one report.
    report = FinalReport(run_id=run.run_id, status="COMPLETE", findings=merge(results), notes=run.notes)
    run.finish(report.status, report.model_dump_json())
    return report


# Combine findings from all specialists: drop duplicates, put high severity first.
def merge(results: list[WorkerResult]) -> list[Finding]:
    unique = {}
    for finding in (f for r in results for f in r.findings):
        unique.setdefault((finding.file, finding.line, finding.label), finding)
    return sorted(unique.values(), key=lambda f: SEVERITY_ORDER[f.severity])
