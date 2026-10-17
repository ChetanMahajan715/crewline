<p align="center"><img src="brand/logo.svg" width="96" alt="agent-harness logo"></p>

# agent-harness

A small multi-agent harness with budgets, retries, safety controls and replayable logs.

Run states, as shown in the terminal: **COMPLETE** (green), **PARTIAL** (yellow), **STOPPED** (red), **INJECTION SUSPECTED** (magenta), **APPROVAL NEEDED** (cyan).

## 1. What I built

A team of agents working on a folder of files. A **lead** plans one subtask per specialist. The **specialists** work in parallel, each with its own prompt and its own tools. A **checker** accepts each result or sends it back. The lead's merge step removes duplicates and sorts by severity. Every hand-off is JSON validated by Pydantic.

There are two task types, and both run through the same core code. `code_review` uses security, quality and docs specialists. `file_triage` uses classifier, urgency and extractor specialists. A task type is just a profile in `harness/config.py`.

```
            goal (plain English) + task profile
                        │
                   ┌────▼────┐
                   │  LEAD   │  plans subtasks (structured JSON)
                   └────┬────┘
        ┌───────────────┼───────────────┐   run in parallel (asyncio.gather)
  ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
  │SPECIALIST1│   │SPECIALIST2│   │SPECIALIST3│   roles come from the task profile
  └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
        └───────────────┼───────────────┘
                   ┌────▼────┐
                   │ CHECKER │  accept / reject + feedback (max 2 loops)
                   └────┬────┘
                   ┌────▼────┐
                   │  LEAD   │  merges → COMPLETE / PARTIAL / STOPPED
                   └─────────┘
  Shared state: SQLite (runs.db)        Trace: runs/<run_id>.jsonl
```

| File | Job |
|---|---|
| `harness/config.py` | All settings: model, limits, retries, prices, task profiles (roles, prompts, tools) |
| `harness/schemas.py` | Pydantic message formats passed between agents |
| `harness/llm.py` | One `call_llm()` for the real provider and the offline mock; rate limiter; 429 backoff |
| `harness/budget.py` | Step, time, token and cost limits for the run and for each agent |
| `harness/tools.py` | `list_files`, `read_file`, `grep`, `write_file`, plus permissions, sandbox, approval and untrusted-data wrapping |
| `harness/agents.py` | The think → tool → observe loop every agent runs |
| `harness/orchestrator.py` | Lead → parallel specialists → checker loop → merge; retries, timeouts, status labels |
| `harness/state.py` | SQLite shared state and the JSONL trace |
| `harness/baseline.py` | The single-agent version for comparison |
| `run.py` / `replay.py` / `evaluate.py` | Run a task / replay a trace / compare team vs single agent |

## 2. How to run (Windows, PowerShell)

```powershell
uv venv .venv
.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env        # then put your key after MISTRAL_API_KEY= in .env
# or, for this terminal only: $env:MISTRAL_API_KEY="your-key-here"

python run.py --task fixture_repo                  # the team, real model
python run.py --task fixture_repo --single         # the single-agent baseline
python run.py --task triage_inbox --provider mock  # offline, no key needed
python replay.py runs\20261016-220223-fixture_repo-multi.jsonl
python evaluate.py                                 # 3 tasks x 2 modes, writes results.md
pytest                                             # 18 tests, mock provider, about 4 s
```

**Test flags:** `--fail-agent security` (always errors, then retries, then PARTIAL), `--slow-agent quality` (sleeps past the timeout), `--strict-checker` (rejects everything, shows the loop cap), and `--max-tokens 3000` / `--max-seconds` / `--max-steps` (run limits).

**Switching provider or key.** Only three lines in `harness/config.py` change: `BASE_URL`, `MODEL` and `API_KEY_ENV`. The `openai` package is used only as an OpenAI-compatible HTTP client, so with the defaults every request goes to `api.mistral.ai` and nothing is sent to OpenAI. Any compatible endpoint works, for example Groq, DeepSeek, OpenRouter or a local Ollama server.

**Model used.** The spec's first choice, `mistral-large-2512`, returns HTTP 403 `tier_not_allowed` on this free-tier account. Every result below uses the spec's backup, `codestral-2508`, for every agent.

## 3. Results: team vs single agent

All numbers are from real runs with `codestral-2508`, one run per task and mode (`results.md`). The rubric is the same for both modes, out of 10: evidence valid /3, accuracy /4, false positives /2, prioritization /1. Cost is **estimated at paid prices**; the free tier cost $0.

| task | mode | score /10 | seconds | steps | tokens | est. cost USD |
|---|---|---|---|---|---|---|
| fixture repo (8 planted bugs) | team | 8.8 (found 6/8) | 65 | 58 | 49,111 | 0.0166 |
| fixture repo (8 planted bugs) | single | **9.1** (found 7/8) | **15** | 9 | **9,033** | **0.0032** |
| public repo `records` | team | manual: 3/10 findings correct | 31 | 22 | 63,116 | 0.0198 |
| public repo `records` | single | manual: 7/19 findings correct | **18** | 6 | **40,088** | **0.0129** |
| triage inbox (10 messages) | team | 9.6 (18/20 labels) | 61 | 53 | 59,253 | 0.0196 |
| triage inbox (10 messages) | single | **10.0** (20/20 labels) | **30** | 12 | **14,773** | **0.0060** |

The public repo has no answer file, so I checked every finding by hand against the source (details in `results.md`). **Limit of the rubric:** both public-repo runs scored 3.0/3 on evidence, because every quoted line really exists. The evidence check proves a quote is real, not that the claim about it is true.

## 4. Where multi-agent was NOT worth it

On these tasks, almost nowhere. The single agent matched or beat the team on quality, and was 2 to 4 times faster and 3 to 5 times cheaper in tokens.

- **The tasks fit in one context.** Five small files or ten short messages don't need to be split up. Splitting means three agents each re-read the same files, and three checkers read them again.
- **The checker costs a lot and can make results worse.** On the fixture repo it rejected work 3 times. In an earlier run it rejected a correct SQL injection finding and the specialist removed it (DEVLOG entry 3). With this model, the checker adds errors as well as removing them.
- **Where the team helped:** evidence validity on the fixture repo (3.0 vs 2.6, because the single agent quoted one line that isn't in the file). On the public repo the team covered more kinds of issue (security, quality, docs), while the single agent only reported docstrings. Most of the team's findings there were wrong too, though.
- **When it would pay off:** folders too big for one context, or truly independent subtasks that need different tools or permissions. On tasks this size, use one agent.

## 5. A run that went wrong

Run `runs/20261016-214739-fixture_repo-multi.jsonl` (try `python replay.py` on it):

- **What happened:** every call returned HTTP 403 `tier_not_allowed`. The configured model, `mistral-large-2512`, isn't in this account's free tier.
- **What the harness did:** the lead failed, so the harness fell back to the default plan. All three specialists failed. The run finished cleanly as **PARTIAL**, listing every missing subtask and the error. But it also retried a permanent error 3 times per agent: 16 useless calls and 25 seconds.
- **What I changed:**
  - Switched to the backup model with one config line.
  - Made `with_retries` fail immediately on permanent HTTP 4xx errors, while still retrying 408 and 429 (test `test_permanent_api_error_not_retried`).

`DEVLOG.md` has 9 more real problems, including the checker rejecting correct work and triage hitting the step limit.

## 6. Decisions and trade-offs

- **No agent framework.** The loop is about 50 lines (`agents.py`), so every step is visible and explainable.
- **One model for all agents.** A fair comparison with the baseline, and simpler.
- **Tool calls as JSON replies** (`{"tool": ...}` or `{"final": ...}`). This works with any provider, not just ones with native tool calling. An invalid reply is re-asked once with the validation error, then counted as a failure.
- **SQLite for shared state, JSONL for the trace.** `runs.db` is the one inspectable place for runs, subtasks and approvals. The JSONL trace is append-only and easy to replay.
- **The regex is not the real defence.** The injection regex only raises a flag. The protection is three layers that don't depend on the model obeying:
  - each role gets only its tools;
  - every path must stay inside the task folder or `sandbox/`;
  - writing outside `sandbox/` needs a human yes, and no answer means deny.

  `write_file` paths are relative to `sandbox/`. Note that the public repo is cloned inside `sandbox/repos/`, so agents could write there without approval.
- **Mock provider for tests, real model for evaluation.** The tests are fast and deterministic; the results are real.
- **Free tier, so cost is estimated.** Tokens are the real cost measure. USD comes from the price table in config.
- **The merge is plain code, not a model call.** Removing duplicates and sorting by severity doesn't need a model, and doing it in code saves tokens.
- **The step limit is soft under parallelism.** Each parallel agent checks the limit before the others charge it, so a run can overshoot by up to one step per parallel agent (62 of 60 in DEVLOG entry 4).

## 7. How to add a new task type

1. In `harness/config.py`, add an entry to `PROFILES`: `lead_tools`, `checker_tools`, and for each specialist, `tools` and a `prompt`. Findings use the shared format `Finding(title, label, severity, file, line, evidence, explanation)`.
2. In `tasks/tasks.json`, add `{"id", "profile", "folder", "goal"}`, plus `"answers"` if you want automatic scoring.
3. Run `python run.py --task <id>`. No core code changes; `test_new_profile_runs_without_core_changes` proves this.

## 8. What I cut for time

- More than one run per task and mode. Results vary between runs, so the comparison above is a small sample.
- A deterministic evidence pre-check fed to the checker.
- Automatic scoring for the public repo (it's a manual check instead).
- A tool or service call other than `write_file` that goes through the approval gate. `request_approval()` is generic, but only `write_file` uses it today.
- The Streamlit approval screen is optional and built last (see `app.py` if present).

## 9. Hours spent

`TODO: fill in`

## 10. How I used AI, including one place it was wrong

`TODO: fill in`

Candidates from DEVLOG:
- the lead prompt wording that made the model drop the `{"final": ...}` wrapper (entry 2);
- a test "mutation" that didn't break anything (entry 10);
- a `.gitignore` rule that couldn't untrack files that were already tracked (entry 10);
- assuming `mistral-large-2512` was in the free tier (entry 1).

## 11. Demo video script (3 to 4 min)

1. **Title card (10 s):** logo, "agent-harness", "A team of agents, kept in check." on `#0F172A`.
2. **A full real run (60 s):** `python run.py --task fixture_repo`. Point out:
   - the findings table, high severity first;
   - the magenta **INJECTION SUSPECTED** note for `NOTES.md`;
   - no `outside.txt` was created.

   Then `python replay.py runs\<id>.jsonl`: point at the parallel specialists' start times, the checker verdicts, and the per-agent totals.
3. **A failure (40 s):** `python run.py --task fixture_repo --fail-agent security`. Yellow **RETRY** lines with 1 s, 2 s, 4 s waits, then **PARTIAL** listing `security` as missing, while the other findings are kept.
4. **A limit hit (30 s):** `python run.py --task fixture_repo --max-tokens 3000`. A red **STOPPED: run tokens**, with the finished work still returned.
5. **The risky write being denied (30 s):** `pytest -k risky_write -v`. It shows that writing in the sandbox works, but writing into the task folder triggers **APPROVAL NEEDED**; no answer means **DENIED**, and the file isn't created. Optionally run `pytest -k injection -v`.
6. **Honest result (30 s):** show the table from section 3. On tasks this small, one agent was as good, faster and cheaper.
