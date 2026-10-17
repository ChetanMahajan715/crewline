<p align="center"><img src="brand/logo.svg" width="96" alt="agent-harness logo"></p>

# agent-harness

A small multi-agent harness with budgets, retries, safety controls and replayable logs.

Give it a folder of files and a job in plain English. A **lead** agent splits the job, three **specialist** agents work on it in parallel, a **checker** agent reviews their work, and the harness merges everything into one report. Around the agents, the harness enforces limits, retries failures, blocks risky actions, and records every step so you can replay the run.

Run states, as shown in the terminal: **COMPLETE** (green), **PARTIAL** (yellow), **STOPPED** (red), **INJECTION SUSPECTED** (magenta), **APPROVAL NEEDED** (cyan).

## Quick start (Windows, PowerShell)

You need [Git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 for you if it's missing.

```powershell
git clone https://github.com/ChetanMahajan715/agent-harness.git
cd agent-harness
uv venv .venv --python 3.12
.venv\Scripts\activate
uv pip install -r requirements.txt

# Your Mistral API key (free tier works): copy the template, then put the key after the = sign
copy .env.example .env
notepad .env

pytest                                   # 25 tests, offline, about 4 seconds

# Bring your own input: clone a small Python repo into the sandbox...
git clone https://github.com/OWNER/REPO.git sandbox\repos\myrepo
# ...add it to tasks\tasks.json (see docs/GUIDE.md, part 2), then:
python run.py --task myrepo              # a real run with the team
```

**The full step-by-step guide**, covering every feature, how to test each one and how to fix common problems, is in **[docs/GUIDE.md](docs/GUIDE.md)**.

## 1. What I built

A team of agents working on a folder of files. The **lead** plans one subtask per specialist. The **specialists** work in parallel, each with its own prompt and its own tools. The **checker** accepts each result or sends it back. The merge step removes duplicates and sorts by severity. Every hand-off is JSON validated by Pydantic.

There are two task types, and both run through the same core code:
- `code_review` uses security, quality and docs specialists.
- `file_triage` uses classifier, urgency and extractor specialists.

A task type is just a profile in `harness/config.py`.

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
                   │  MERGE  │  → COMPLETE / PARTIAL / STOPPED
                   └─────────┘
  Shared state: SQLite (runs.db)        Trace: runs/<run_id>.jsonl
```

### Project structure

```
agent-harness/
├── harness/              the harness itself
│   ├── config.py         ALL settings: model, limits, retries, prices, task profiles
│   ├── schemas.py        message formats passed between agents (Pydantic)
│   ├── llm.py            one call_llm() for the real model and the offline mock
│   ├── agents.py         the think → tool → observe loop every agent runs
│   ├── orchestrator.py   lead → parallel specialists → checker → merge
│   ├── baseline.py       the single-agent version, for comparison
│   ├── budget.py         step, time, token and cost limits
│   ├── tools.py          list_files, read_file, grep, write_file + safety layers
│   └── state.py          SQLite shared state and the JSONL trace
├── run.py                run a task
├── replay.py             replay a run in the terminal
├── evaluate.py           team vs single agent on every task → results.md
├── app.py                web page: run viewer and approval screen (Streamlit)
├── tasks/tasks.json      the list of tasks (id, team, folder, goal)
├── tests/                25 automated tests (offline mock model)
├── docs/                 GUIDE.md (how to run and test) and DEVLOG.md (what went wrong)
├── brand/                logo, colours and the web page theme
├── sandbox/              your task inputs, and the only folder agents may write to
└── runs/                 one trace file per run (created by runs)
```

## 2. How to run

The project ships with **no tasks**: `tasks/tasks.json` starts as `[]`, and you add your own. A task is a folder plus a job, for example:

```json
[
  {"id": "myrepo", "profile": "code_review", "folder": "sandbox/repos/myrepo",
   "goal": "Review this Python repo for security, quality and documentation issues."}
]
```

`profile` picks the team: `code_review` (security, quality, docs) or `file_triage` (classifier, urgency, extractor, for a folder of text messages). [docs/GUIDE.md](docs/GUIDE.md) parts 2 and 5 walk through both. Then, with `.venv` active:

```powershell
python run.py --task myrepo                        # the team, real model
python run.py --task myrepo --single               # the single-agent baseline
python run.py --task myrepo --provider mock        # offline, no key needed
python replay.py runs\<run id>.jsonl               # replay any run (the id is printed at the end of each run)
python evaluate.py                                 # all tasks, team vs single, writes results.md
pytest                                             # the automated tests
streamlit run app.py                               # web page: run viewer + approval screen
```

**Test flags:**
- `--fail-agent security`: that agent always errors, so you see the retries, then PARTIAL.
- `--slow-agent quality`: that agent sleeps past the timeout.
- `--strict-checker`: the checker rejects everything, showing the loop cap.
- `--max-tokens 3000` / `--max-seconds` / `--max-steps`: run limits.

**Approvals.** Risky actions ask for a human "yes" in the terminal. To answer in the browser instead, set `APPROVAL_MODE = "streamlit"` in `harness/config.py` and keep `streamlit run app.py` open. No answer within `APPROVAL_TIMEOUT_SECONDS` always means deny.

**Switching provider or key.** Only three lines in `harness/config.py` change: `BASE_URL`, `MODEL` and `API_KEY_ENV`. The `openai` package is used only as an OpenAI-compatible HTTP client, so with the defaults every request goes to `api.mistral.ai` and nothing is sent to OpenAI. Any compatible endpoint works, for example Groq, DeepSeek, OpenRouter or a local Ollama server.

**Model used.** `mistral-large-2512` returns HTTP 403 `tier_not_allowed` on a free-tier Mistral account. Every result below uses `codestral-2508`, for every agent.

## 3. Results: team vs single agent

All numbers are from real runs with `codestral-2508` on 16 October 2026, one run per task and mode. Run `python evaluate.py` to reproduce them; your numbers will vary a little, because model output varies. The rubric is the same for both modes, out of 10: evidence valid /3, accuracy /4, false positives /2, prioritization /1. Cost is **estimated at paid prices**; the free tier cost $0.

| task | mode | score /10 | seconds | steps | tokens | est. cost USD |
|---|---|---|---|---|---|---|
| fixture repo (8 planted bugs) | team | 8.8 (found 6/8) | 65 | 58 | 49,111 | 0.0166 |
| fixture repo (8 planted bugs) | single | **9.1** (found 7/8) | **15** | 9 | **9,033** | **0.0032** |
| public repo `records` | team | manual: 3/10 findings correct | 31 | 22 | 63,116 | 0.0198 |
| public repo `records` | single | manual: 7/19 findings correct | **18** | 6 | **40,088** | **0.0129** |
| triage inbox (10 messages) | team | 9.6 (18/20 labels) | 61 | 53 | 59,253 | 0.0196 |
| triage inbox (10 messages) | single | **10.0** (20/20 labels) | **30** | 12 | **14,773** | **0.0060** |

- **Manual check:** the public repo has no answer file, so I checked every finding by hand against the source.
- **Status note:** in the fixture team run, `docs` ran out of its own 15-step budget during a revision. That run printed COMPLETE; the harness now labels this case PARTIAL. The scores are unchanged.
- **Limit of the rubric:** both public-repo runs scored 3.0/3 on evidence, because every quoted line really exists. The evidence check proves a quote is real, not that the claim about it is true.

## 4. Where multi-agent was NOT worth it

On these tasks, almost nowhere. The single agent matched or beat the team on quality, was 1.7 to 4.3 times faster, and used 1.6 to 5.4 times fewer tokens.

- **The tasks fit in one context.** Five small files or ten short messages don't need splitting. Splitting means three agents each re-read the same files, and three checkers read them again.
- **The checker costs a lot and can make results worse.** On the fixture repo it rejected work 3 times. In an earlier run it rejected a correct SQL injection finding, and the specialist removed it ([docs/DEVLOG.md](docs/DEVLOG.md), entry 3). With this model, the checker adds errors as well as removing them.
- **Where the team helped:** evidence validity on the fixture repo (3.0 vs 2.6, because the single agent quoted one line that isn't in the file). On the public repo the team covered more kinds of issue (security, quality, docs), while the single agent only reported docstrings, though most of the team's findings there were wrong too.
- **When it would pay off:** folders too big for one context, or truly independent subtasks that need different tools or permissions. On tasks this size, use one agent.

## 5. A run that went wrong

- **What happened:** on the first real run, every call returned HTTP 403 `tier_not_allowed`. The configured model, `mistral-large-2512`, isn't in the free tier.
- **What the harness did:** the lead failed, so the harness fell back to a default plan. All three specialists failed. The run finished cleanly as **PARTIAL**, listing every missing subtask and the error. But it also retried a permanent error 3 times per agent: 16 useless calls and about 23 seconds.
- **What I changed:**
  - Switched to `codestral-2508` with one config line.
  - Made retries stop at once on permanent HTTP 4xx errors (test `test_permanent_api_error_not_retried`). 408 is still retried, and 429 (rate limit) is retried with backoff inside `llm.py`.

[docs/DEVLOG.md](docs/DEVLOG.md) has the other real problems, including the checker rejecting correct work and triage hitting the step limit.

## 6. Decisions and trade-offs

- **No agent framework.** The loop is about 50 lines (`harness/agents.py`), so every step is visible and explainable.
- **One model for all agents.** A fair comparison with the baseline, and simpler.
- **Tool calls as JSON replies** (`{"tool": ...}` or `{"final": ...}`). This works with any provider, not just ones with native tool calling. An invalid reply is re-asked once with the validation error, then counted as a failure.
- **SQLite for shared state, JSONL for the trace.** `runs.db` is the one inspectable place for runs, subtasks and approvals. The JSONL trace is append-only and easy to replay.
- **The regex is not the real defence.** The injection regex only raises a flag. The protection is three layers that don't depend on the model obeying:
  - each role gets only its own tools;
  - every path must stay inside the task folder or `sandbox/`, and links that point outside are ignored;
  - writing outside `sandbox/`, or into the task's own files, needs a human "yes", and no answer means deny.
- **Mock model for tests, real model for evaluation.** The tests are fast and deterministic; the results are real.
- **Free tier, so cost is estimated.** Tokens are the real cost measure. USD comes from the price table in config.
- **The merge is plain code, not a model call.** Removing duplicates and sorting by severity doesn't need a model, and doing it in code saves tokens.
- **The step limit is soft under parallelism.** Each parallel agent checks the limit before the others charge it, so a run can overshoot by up to one step per parallel agent.

## 7. How to add a new task type

1. In `harness/config.py`, add an entry to `PROFILES`: `lead_tools`, `checker_tools`, and for each specialist, `tools` and a `prompt`. Findings use the shared format `Finding(title, label, severity, file, line, evidence, explanation)`.
2. In `tasks/tasks.json`, add `{"id", "profile", "folder", "goal"}`, plus `"answers"` if you want automatic scoring.
3. Run `python run.py --task <id>`. No core code changes; `test_new_profile_runs_without_core_changes` proves this.

[docs/GUIDE.md](docs/GUIDE.md) part 12 walks through a complete example.

## 8. What I cut for time

- More than one run per task and mode. Results vary between runs, so the comparison above is a small sample.
- A deterministic evidence pre-check fed to the checker.
- Automatic scoring for the public repo (it's a manual check instead).
- A tool or service call other than `write_file` that goes through the approval gate. `request_approval()` is generic, but only `write_file` uses it today.

## 9. Hours spent

`TODO: fill in`

## 10. How I used AI, including one place it was wrong

`TODO: fill in`

## 11. Demo video script (3 to 4 min)

1. **Title card (10 s):** logo, "agent-harness", "A team of agents, kept in check." on `#0F172A`.
2. **A full real run (60 s):** with a trap `NOTES.md` planted in your repo ([docs/GUIDE.md](docs/GUIDE.md) part 4), run `python run.py --task myrepo`. Point out:
   - the findings table, high severity first;
   - the **INJECTION SUSPECTED** note for `NOTES.md`;
   - no `outside.txt` was created.

   Then `python replay.py runs\<id>.jsonl`: point at the parallel specialists' start times, the checker verdicts, and the per-agent totals.
3. **A failure (40 s):** `python run.py --task myrepo --fail-agent security`. Yellow **RETRY** lines with 1 s, 2 s, 4 s waits, then **PARTIAL** listing `security` as missing, while the other findings are kept.
4. **A limit hit (30 s):** `python run.py --task myrepo --max-tokens 3000`. A red **STOPPED: run tokens**: the lead finishes, and the missing list shows each specialist stopped by the run's token limit.
5. **The risky write being denied (30 s):** [docs/GUIDE.md](docs/GUIDE.md) step 9.3. **APPROVAL NEEDED** appears; answer `n`, or nothing, and the write is **DENIED** and the file isn't created.
6. **Honest result (30 s):** show the table from section 3. On tasks this small, one agent was as good, faster and cheaper.
