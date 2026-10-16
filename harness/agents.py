# The small loop every agent runs: think (ask the model), act (call a tool), observe (read the
# result), until the model gives a final answer or a budget runs out. Each step is logged.
from pydantic import BaseModel, ValidationError

from harness import llm, tools
from harness.budget import Budget, estimate_cost
from harness.schemas import AgentAction
from harness.state import Run


# Raised when an agent cannot produce a usable answer (e.g. invalid JSON twice in a row).
class AgentFailed(Exception):
    pass


# Run one agent until it returns a final answer that matches `schema`.
async def run_agent(run: Run, name: str, system: str, task: str, allowed: list[str],
                    budgets: list[Budget], schema: type[BaseModel]) -> BaseModel:
    messages = [{"role": "user", "content": task}]
    run.log(name, "agent_start", input=task)
    bad_replies = 0
    while True:
        # Stop before the call if this agent or the whole run is out of budget.
        for budget in budgets:
            budget.check()
        text, in_tokens, out_tokens, seconds = await llm.call_llm(
            system, messages, name, on_retry=lambda msg: run.log(name, "retry", status="retry", output=msg))
        cost = estimate_cost(in_tokens, out_tokens)
        for budget in budgets:
            budget.charge(in_tokens + out_tokens, cost)
        run.log(name, "llm_step", input=messages[-1]["content"], output=text, input_tokens=in_tokens,
                output_tokens=out_tokens, est_cost_usd=cost, seconds=seconds)
        messages.append({"role": "assistant", "content": text})

        # Parse the reply. If it is invalid, re-ask once with the error; twice in a row = failure.
        try:
            action = AgentAction.model_validate_json(text)
            if action.final is not None:
                answer = schema.model_validate(action.final)
                run.log(name, "agent_end", output=text)
                return answer
            bad_replies = 0
        except ValidationError as error:
            bad_replies += 1
            run.log(name, "invalid_json", status="error", output=str(error))
            if bad_replies > 1:
                raise AgentFailed(f"{name} sent invalid JSON twice")
            messages.append({"role": "user", "content": f"Invalid reply: {str(error)[:500]}\nReply again with one valid JSON object."})
            continue

        # Run the tool and give the result back to the model.
        observation = await tools.run_tool(run, name, action.tool, action.args, allowed)
        messages.append({"role": "user", "content": observation})
