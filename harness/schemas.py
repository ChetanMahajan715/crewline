# The message formats agents hand to each other. Every hand-off is JSON checked by
# Pydantic, so a malformed reply is caught at the border instead of deep in the code.
from typing import Literal

from pydantic import BaseModel, model_validator


# One piece of work the lead gives to one specialist.
class Subtask(BaseModel):
    id: str
    role: str
    instructions: str


# The lead's plan: a list of subtasks.
class Plan(BaseModel):
    subtasks: list[Subtask]


# One reply from an agent: either a tool call or a final answer, never both.
class AgentAction(BaseModel):
    tool: str | None = None
    args: dict = {}
    final: dict | None = None

    # Reject replies that have neither a tool nor a final answer (or both).
    @model_validator(mode="after")
    def one_of_tool_or_final(self) -> "AgentAction":
        if (self.tool is None) == (self.final is None):
            raise ValueError('reply must contain exactly one of "tool" or "final"')
        return self


# One issue or one triage result, the same shape for every task profile.
class Finding(BaseModel):
    title: str
    label: str
    severity: Literal["high", "medium", "low"]
    file: str
    line: int | None = None
    evidence: str
    explanation: str


# What one specialist returns. status: ok, unverified (checker loop cap hit) or failed.
class WorkerResult(BaseModel):
    subtask_id: str = ""
    findings: list[Finding] = []
    status: str = "ok"


# The checker's decision on one WorkerResult.
class CheckerVerdict(BaseModel):
    subtask_id: str = ""
    accept: bool
    feedback: str = ""


# The end result of a run. status: COMPLETE, PARTIAL or "STOPPED: <limit>".
class FinalReport(BaseModel):
    run_id: str = ""
    status: str
    findings: list[Finding] = []
    missing: list[str] = []
    notes: list[str] = []
