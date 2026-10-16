# Runs a task with the team: the lead plans, the specialists work in parallel, the checker
# accepts or sends work back, and the results are merged into one FinalReport labelled
# COMPLETE, PARTIAL or STOPPED. Roles, prompts and tools come from the task profile in config.
import asyncio

from harness import config, tools
from harness.agents import run_agent
from harness.budget import Budget, BudgetExceeded
from harness.schemas import CheckerVerdict, FinalReport, Finding, Plan, Subtask, WorkerResult
from harness.state import Run

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# Build an agent's system prompt: shared rules first, then the role's own instructions.
def system_prompt(role: str, allowed: list[str], instructions: str) -> str:
    return config.BASE_PROMPT.format(role=role, tools=", ".join(allowed) or "none") + "\n" + instructions


# Try `attempt` with a timeout; on failure wait 1 s, 2 s, 4 s and try again. Budgets are not retried.
async def with_retries(run: Run, name: str, attempt):
    delays = config.BACKOFF_SECONDS
    for number in range(len(delays) + 1):
        try:
            return await asyncio.wait_for(attempt(), config.AGENT_TIMEOUT_SECONDS)
        except BudgetExceeded:
            raise
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            # HTTP 4xx errors (except 408 timeout, 429 rate limit) are permanent: fail at once.
            permanent = 400 <= getattr(error, "status_code", 0) < 500 and error.status_code not in (408, 429)
            if number == len(delays) or permanent:
                run.log(name, "error", status="error", output=f"gave up after {number + 1} attempts: {reason}")
                raise
            run.log(name, "retry", status="retry", output=f"attempt {number + 1} failed ({reason}), retry in {delays[number]}s")
            await asyncio.sleep(delays[number])


# Run one task end to end and return the final report. The flags simulate failures for demos/tests.
async def run_task(task: dict, strict_checker: bool = False, fail_agent: str | None = None,
                   slow_agent: str | None = None, limits: dict | None = None) -> FinalReport:
    profile = config.PROFILES[task["profile"]]
    run = Run(task["id"], config.ROOT / task["folder"], "multi")
    run_budget = Budget("run", **{**config.RUN_LIMITS, **(limits or {})})
    run.log("harness", "run_start", input=task)
    files = ", ".join(tools.list_files(run))
    roles = list(profile["specialists"])
    done: dict[str, WorkerResult] = {}  # finished specialist work, kept even if the run stops later
    reasons: dict[str, str] = {}  # why a subtask is missing
    stopped = None

    # One specialist works on one subtask; the checker accepts it or sends it back.
    async def work_on(subtask: Subtask) -> None:
        spec = profile["specialists"][subtask.role]
        system = system_prompt(subtask.role, spec["tools"], spec["prompt"] + "\n" + config.FINDING_FORMAT)
        checker = f"checker:{subtask.role}"
        checker_system = system_prompt("checker", profile["checker_tools"], config.CHECKER_PROMPT)
        worker_budget = Budget(subtask.role, **config.AGENT_LIMITS)
        checker_budget = Budget(checker, **config.AGENT_LIMITS)
        feedback = ""

        # One attempt by the specialist, including the simulated failures.
        async def specialist_attempt() -> WorkerResult:
            if subtask.role == fail_agent:
                raise RuntimeError("simulated failure (--fail-agent)")
            if subtask.role == slow_agent:
                await asyncio.sleep(config.AGENT_TIMEOUT_SECONDS + 1)
            work = f"Goal: {task['goal']}\nSubtask: {subtask.instructions}\nFiles in the folder: {files}"
            if feedback:
                work += f"\nChecker feedback on your last answer: {feedback}"
            return await run_agent(run, subtask.role, system, work, spec["tools"], [run_budget, worker_budget], WorkerResult)

        for loop in range(config.MAX_CHECKER_LOOPS + 1):
            result = await with_retries(run, subtask.role, specialist_attempt)
            result.subtask_id, result.status = subtask.id, "unverified"  # unverified until the checker accepts
            done[subtask.id] = result
            check = f"Subtask: {subtask.instructions}\nFindings to check:\n{result.model_dump_json()}"
            verdict = await with_retries(run, checker, lambda: run_agent(
                run, checker, checker_system, check, profile["checker_tools"], [run_budget, checker_budget], CheckerVerdict))
            if strict_checker:  # test flag: the checker rejects everything
                verdict.accept = False
            run.log(checker, "verdict", status="ok" if verdict.accept else "rejected", output=verdict.feedback)
            if verdict.accept:
                result.status = "ok"
                break
            feedback = verdict.feedback
        else:
            run.notes.append(f"{subtask.id}: unverified, checker still rejected after {config.MAX_CHECKER_LOOPS} revisions")
        run.save_subtask(subtask.id, subtask.role, result.status, loop + 1, result.model_dump_json())

    try:
        # 1. The lead looks at the folder and plans. If it fails, use a default plan.
        lead_task = f"Goal: {task['goal']}\nRoles: {', '.join(roles)}"
        lead_system = system_prompt("lead", profile["lead_tools"], config.LEAD_PROMPT)
        lead_budget = Budget("lead", **config.AGENT_LIMITS)
        try:
            plan = await with_retries(run, "lead", lambda: run_agent(
                run, "lead", lead_system, lead_task, profile["lead_tools"], [run_budget, lead_budget], Plan))
        except BudgetExceeded:
            raise
        except Exception:
            plan = Plan(subtasks=[])
            run.notes.append("lead failed, used the default plan")
        # Exactly one subtask per profile role, whatever the lead returned.
        by_role = {s.role: s for s in plan.subtasks if s.role in roles}
        subtasks = [Subtask(id=r, role=r, instructions=by_role[r].instructions if r in by_role else f"Do the {r} job.")
                    for r in roles]

        # 2. All specialists run at the same time; failures come back as exceptions, not crashes.
        outcomes = await asyncio.gather(*(work_on(s) for s in subtasks), return_exceptions=True)
        for subtask, outcome in zip(subtasks, outcomes):
            if isinstance(outcome, BudgetExceeded) and outcome.limit.startswith("run "):
                stopped = outcome.limit
            if isinstance(outcome, BaseException):
                reasons[subtask.id] = f"{type(outcome).__name__}: {outcome}"
                finished = done.get(subtask.id)
                run.save_subtask(subtask.id, subtask.role, "unverified" if finished else "failed", 0,
                                 finished.model_dump_json() if finished else reasons[subtask.id])
                if finished:
                    run.notes.append(f"{subtask.id}: unverified, stopped before the checker accepted ({reasons[subtask.id]})")
    except BudgetExceeded as error:
        stopped = error.limit

    # 3. Merge what finished and label the run honestly.
    if stopped:
        run.log("harness", "budget_stop", status="error", output=stopped)
    missing = [f"{role}: {reasons.get(role, 'not started, run stopped')}" for role in roles if role not in done]
    status = f"STOPPED: {stopped}" if stopped else "PARTIAL" if missing else "COMPLETE"
    report = FinalReport(run_id=run.run_id, status=status, findings=merge(list(done.values())),
                         missing=missing, notes=run.notes)
    run.finish(report.status, report.model_dump_json())
    return report


# Combine findings from all specialists: drop duplicates, put high severity first.
# A duplicate has the same file and line plus the same label or title. Findings without a
# line (triage) only match on label, so one file can hold a category, a priority and facts.
def merge(results: list[WorkerResult]) -> list[Finding]:
    seen, unique = set(), []
    for f in (f for r in results for f in r.findings):
        keys = {(f.file, f.line, f.label)} | ({(f.file, f.line, f.title.lower())} if f.line is not None else set())
        if not keys & seen:
            unique.append(f)
        seen |= keys
    return sorted(unique, key=lambda f: SEVERITY_ORDER[f.severity])
