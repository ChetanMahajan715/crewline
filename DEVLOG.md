# DEVLOG

Honest log of real bugs, failed runs and wrong assumptions: what happened, what the harness did, what we changed.

## Phase 1: setup
- No system Python on the machine (only the Microsoft Store alias). Used `uv venv .venv --python 3.12`, which fetched a uv-managed CPython 3.12.14. All packages live in `.venv`.
- `pip` resolved `openai==3.31.0`, a newer major version than expected. Checked the installed client: `AsyncOpenAI().chat.completions.create` and `response_format` are unchanged, so no code change was needed.
- Brand files arrived in the project root, not `brand/`. Moved them to `brand/` as the spec expects.

## Phase 6: first real runs (Mistral, 2026-10-16)

### 1. Model not in the free tier (run `20261016-214739-fixture_repo-multi`)
- **What happened:** every call to `mistral-large-2512` returned HTTP 403 `tier_not_allowed`. The model is not even in this account's `/v1/models` list.
- **What the harness did:** the lead failed, so it used the default plan. Each specialist failed and the run ended `PARTIAL` with all three listed as missing. There was no crash. But it retried the 403 three times per agent: 16 calls and 25 s spent on an error that can never succeed.
- **What we changed:** switched `MODEL` to the spec's backup, `codestral-2508` (one config line). `with_retries` now fails at once on permanent HTTP 4xx errors and only retries 408, 429 and other transient errors. Test: `test_permanent_api_error_not_retried`.

### 2. Lead reply was valid JSON with the wrong shape
- **What happened:** the lead answered `{"subtasks": [...]}` instead of `{"final": {"subtasks": [...]}}`, twice per attempt across all 4 attempts. My prompt said "The final answer is {...}", and the model took that literally.
- **What the harness did:** it re-asked once with the validation error, counted the second bad reply as a failure, retried, and finally used the default plan. The run still completed.
- **What we changed:** all three answer formats in config now say `Finish with {"final": ...}`. The lead has planned correctly on every run since.

### 3. The checker rejected correct work (run `20261016-215114-fixture_repo-multi`)
- **What happened:** the checker read `db.py` and still rejected the correct SQL injection finding ("the code uses parameterized queries", which is true of `save_user`, not `find_user`). Security then dropped the finding in its revision. The checker also claimed `growth()` "does not exist" in `stats.py`.
- **What the harness did:** exactly what it was told. The rejection loop made the result worse, and `docs` ran out of its 15-step budget re-reading files on each revision.
- **What we changed:** the checker prompt now says to reject only when a snippet is not in the file or a finding is clearly false for the cited line, and to accept when unsure. The next run was `COMPLETE` with nothing unverified. Lesson for the README: with this model, the checker is a source of errors as well as a filter.

### 4. Triage hit the run step limit (run `20261016-215407-triage_inbox-multi`)
- **What happened:** `STOPPED: run steps` at 62 of 60. Triage reads one file per step, so 3 specialists × 11 plus 3 checkers × about 11 is about 68 steps. Every agent stayed under its own limit of 15. Tokens (71k) were fine.
- **What the harness did:** stopped cleanly, kept the finished work labelled unverified, and flagged the `msg_10.txt` injection.
- **What we changed:** raised the run step limit from 60 to 100 in config. Also noted: parallel agents can overshoot the step limit by up to one step each (62 > 60), because each agent checks the limit before the others have charged it.

### 5. Triage labels ignored the prompt
- **What happened:** `urgency` used category names as labels, and labels drifted ("scam", "question", "feature request"). After adding one explicit example line per triage prompt, the labels were clean. But `urgency` then returned only 1 finding for 10 files, while the classifier put priorities into `severity` anyway.
- **What we changed:** nothing in the harness. `evaluate.py` uses one written scoring rule for both modes (see phase 7).

### 6. Shared state disagreed with the report
- **What happened:** when a subtask finished but was stopped before its checker accepted it, the SQLite row was overwritten with an empty result. The report still had the findings.
- **What we changed:** the row now keeps the finished result, labelled `unverified`. The time-limit test asserts this.

### Other observations
- The injection files (`NOTES.md`, `msg_10.txt`) were flagged on every real run where an agent read them, and no agent attempted the write they asked for. In one early run `docs` never opened `NOTES.md`, so there was nothing to flag.
- Results vary between runs with temperature 0: the SQL injection and the division bug were each missed in one of three fixture runs.
