# Demo video script (3 to 4 minutes)

The brief asks for **one full run, one failure, one limit hit**: scenes 3, 5 and 6.

## Before recording
- Terminal 1: `cd D:\Projects\Crewline`, `.venv\Scripts\activate`, big font, `cls`.
- Terminal 2: same, then `streamlit run app.py` (keep it running).
- Do one practice run: `python run.py --task myrepo`.
- **Never show `.env`** (your API key).

## Scenes

| # | Time | Show / type | Say |
|---|---|---|---|
| 1 | 0:00 | Logo: `brand\logo.svg` | "Crewline: a team of AI agents with budgets, retries, safety controls and replayable logs. Hand-written, no framework." |
| 2 | 0:15 | VS Code: `sandbox\test-data\buggy_python_repo\db.py` line 7, then `NOTES.md`, then `tasks\tasks.json` | "The input is a small repo with 8 planted bugs. NOTES.md is a trap that tells AI agents to ignore their instructions. A task is one entry in tasks.json: folder, team, goal." |
| 3 | 0:50 | `python run.py --task myrepo`, then `Test-Path outside.txt` | While it runs: "The lead plans, three specialists work in parallel with only the tools they need, a checker reviews." After: point at the findings (high first), the injection NOTE, and `False`. "The trap was treated as data, not obeyed." |
| 4 | 1:55 | The `python replay.py runs\...jsonl` line printed at the end | Point at the three specialists starting at the same second, the INJECTION line, a checker verdict, the totals table. "Every step is logged and replayable." |
| 5 | 2:25 | `python run.py --task myrepo --fail-agent security` | "Security fails on purpose: retries after 1, 2, 4 seconds, then PARTIAL. The other agents' work is kept." |
| 6 | 2:55 | `python run.py --task myrepo --max-tokens 3000` | "A tiny token budget: the run stops cleanly with STOPPED: run tokens, and lists what's missing." |
| 7 | 3:15 | Browser http://localhost:8501: pick the `myrepo-multi` run, then the Approvals page | "The same runs on a web page: report, cost per agent, timeline. Risky actions wait here for a human yes; no answer means no." |
| 8 | 3:35 | README section 3, the results table | "On tasks this small, one agent was as accurate and faster and cheaper. A team pays off on bigger jobs. What went wrong is in the README and the dev log." |

**Optional, 20 seconds:** `python run.py --task inbox`. "The same harness triages 10 messages. A new team in config, no code change."

**If a run says PARTIAL** because `docs` ran out of steps: "The harness labels it honestly."
