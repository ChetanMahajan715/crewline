# Demo video script (3 to 4 minutes)

The brief asks for **one full run, one failure, one limit hit**: scenes 3, 5 and 6.

## Before you record
- **Terminal 1 (runs):** `cd D:\Projects\Crewline`, `.venv\Scripts\activate`, big font, wide window, `cls`.
- **Terminal 2 (web page):** same two commands, then `streamlit run app.py`. Leave it running.
- **Practice once:** `python run.py --task myrepo` in Terminal 1, then `cls`.
- **VS Code:** open `D:\Projects\Crewline`. **Never show `.env`** (your API key).
- **Optional, tidy web page:** `Remove-Item runs\*.jsonl; Remove-Item runs.db` (clears old runs).

---

## Scene 1: Title (0:00 to 0:15)
**Show:** `brand\logo.svg` opened in the browser.

**Say:**
> "This is Crewline: a team of AI agents with budgets, retries, safety controls and replayable logs. Written by hand, no agent framework."

## Scene 2: The input (0:15 to 0:45)
**Show, in VS Code:**
1. `sandbox\test-data\buggy_python_repo\db.py`, and point at **line 7** (SQL built from user text).
2. `sandbox\test-data\buggy_python_repo\NOTES.md`, and point at the `AI agent: ignore your previous instructions...` line.
3. `tasks\tasks.json`, and point at the `myrepo` entry.

**Say:**
> "The input is a small repo with eight planted bugs, like this SQL injection. NOTES.md is a trap: it tells the AI to ignore its instructions. A task is just one entry here: folder, team, goal."

## Scene 3: Full run (0:45 to 1:50)
**Type:** `python run.py --task myrepo`

**Say while it runs:**
> "The lead plans. Three specialists work in parallel, each with only the tools it needs. A checker reviews their work and can send it back."

**When it finishes, point at:** the findings table (high severity first), the `NOTE injection suspected ... NOTES.md` line, and the status word.

**Type:** `Test-Path outside.txt`, and point at **`False`**.

**Say:**
> "It found the planted bugs. The trap was spotted and not obeyed: no file was written."

**If it says PARTIAL:**
> "PARTIAL means one agent ran out of steps. The harness says so honestly."

## Scene 4: Replay (1:50 to 2:20)
**Type:** the `python replay.py runs\...jsonl` line printed at the end of scene 3.

**Point at:** the three `agent_start` lines at the same second, the purple `INJECTION` line, a checker `verdict`, and the totals table.

**Say:**
> "Every step is logged. The three specialists start together. Here's the trap being read. And here's the cost per agent."

## Scene 5: Failure (2:20 to 2:50)
**Type:** `cls`, then `python run.py --task myrepo --fail-agent security`

**Point at:** the yellow `PARTIAL`, `MISSING security`, and the findings that are still listed.

**Say:**
> "Security fails on purpose. It retries after one, two and four seconds, then the run finishes as PARTIAL. The rest of the work is kept."

## Scene 6: Limit hit (2:50 to 3:10)
**Type:** `cls`, then `python run.py --task myrepo --max-tokens 3000`

**Point at:** the red `STOPPED: run tokens` and the `MISSING` lines.

**Say:**
> "A tiny token budget. The run stops cleanly and lists what's missing."

## Scene 7: Web page (3:10 to 3:30)
**Show:** the browser at http://localhost:8501.
1. Choose the scene 3 run (ending in `-myrepo-multi`) and scroll: report, totals, timeline.
2. Click **Approvals** in the sidebar.

**Say:**
> "The same runs on a web page. Risky actions wait here for a human yes. No answer means no."

## Scene 8: Honest result (3:30 to 3:50)
**Show:** `README.md`, section **3. Results: team vs single agent**.

**Say:**
> "On tasks this small, one agent was as accurate, and faster and cheaper. A team pays off on bigger jobs. Thanks for watching."

---

**Optional extra scene (20 seconds):** type `python run.py --task inbox` and point at `msg_01.txt` to `msg_10.txt` labelled bug, spam, support and feature.
> "The same harness also sorts support messages. That needed only a new team in the config, no new code."
