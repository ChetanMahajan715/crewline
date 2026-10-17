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

## Phase 7: evaluation (2026-10-16)

### 7. The single agent beat the team
- **What happened:** in `results.md`, the single agent scored the same or higher on both auto-scored tasks (fixture 9.1 vs 8.8, triage 10.0 vs 9.6). It used 3 to 5 times fewer tokens and finished 2 to 4 times faster. The team's only win was evidence validity on the fixture repo (3.0 vs 2.6), which is what the checker is there for. This is one run per mode, so it is a small sample.
- **Why, from the traces:** the tasks are small enough to fit in one context. The team pays for a lead, three agents that each re-read files, and three checkers that read them again (58 steps vs 9 on the fixture repo). On the fixture repo the checker rejected work 3 times, and the team found 6/8 bugs against the single agent's 7/8.
- **What we changed:** nothing, and that's deliberate. This is the honest answer for the README.

### 8. The evidence score can be fooled by true quotes behind false claims
- **What happened:** in the manual check of the public repo, both modes scored 3.0/3 on evidence. But only 3 of 10 (team) and 7 of 19 (single) findings were correct. Example: "missing docstring" cited `def isexception(obj):`, a real line whose function does have a docstring.
- **What we changed:** documented the limit in `results.md` and the README. The automated score checks that a quote exists, not that the claim is true.

### 9. Safety layers in real runs (no demo flags)
- Injection text was flagged in every fixture and triage run, both modes. No real agent ever called `write_file`, so the approval gate was only exercised by the tests and the demo.
- Real permission denials: `security` and `quality` asked for `list_files` (public repo), and the lead asked for `read_file` (triage). All were blocked and logged.

### 10. Mistakes I made while building (candidates for README section 10)
- My first check that the baseline test could fail removed a tool the specialists already had, so the test still passed and proved nothing. I caught it because the "should fail" run printed `1 passed`, then used a mutation that really broke it.
- I added an ignore rule to `.gitignore` to keep only 4 example traces, but the files were already tracked, so nothing changed. `git ls-files` showed it, and the fix was `git rm --cached`.
- I wrote the lead prompt as "The final answer is {...}", which caused entry 2 above.
- I skipped two of the spec's required tests (`test_invalid_json_reasked_once`, `test_new_profile_runs_without_core_changes`) and only noticed while writing the README, which cited one of them. Added both, and checked each one fails when the behaviour is broken (re-ask disabled; profile hardcoded to `code_review`).
