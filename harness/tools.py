# The four tools agents can use: list_files, read_file, grep, write_file. No shell, no web.
# Safety layers, in order: role permission check, sandbox path check, human approval for
# risky writes. Every result is wrapped as untrusted data and scanned for injection phrases.
import asyncio
import re
import sys
import threading
from pathlib import Path

from harness import config
from harness.state import Run

# Folders that are never part of the task.
SKIP_DIRS = {".git", "__pycache__", ".venv"}


# Turn an agent's path into a real path. Anything outside the task folder and sandbox is blocked.
def resolve(run: Run, path: str, base: Path) -> Path:
    target = (base / path).resolve()
    if not any(target.is_relative_to(root) for root in (run.folder, config.SANDBOX_DIR.resolve())):
        raise PermissionError(f"path escapes the task folder and sandbox: {path}")
    return target


# True if this path really stays inside the task folder or sandbox (links pointing out do not).
def is_safe(run: Run, path: Path) -> bool:
    try:
        resolve(run, str(path), run.folder)
        return True
    except PermissionError:
        return False


# All files in the task folder, as relative paths with forward slashes. grep uses this list too.
def list_files(run: Run) -> list[str]:
    return sorted(p.relative_to(run.folder).as_posix() for p in run.folder.rglob("*")
                  if p.is_file() and not SKIP_DIRS & set(p.relative_to(run.folder).parts) and is_safe(run, p))


# Read one file with line numbers, so agents can cite lines.
def read_file(run: Run, path: str) -> str:
    lines = resolve(run, path, run.folder).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(f"{n:4}| {line}" for n, line in enumerate(lines, 1))


# Search every file for a regular expression; return up to 50 "file:line: text" hits.
def grep(run: Run, pattern: str) -> str:
    hits = []
    for name in list_files(run):
        for n, line in enumerate((run.folder / name).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(pattern, line):
                hits.append(f"{name}:{n}: {line.strip()}")
    return "\n".join(hits[:50]) or "no matches"


# Write a file. Inside the sandbox: just write. Into the task's own files (even when the task folder
# is inside the sandbox, like the cloned public repo): ask a human first.
async def write_file(run: Run, agent: str, path: str, content: str) -> str:
    target = resolve(run, path, config.SANDBOX_DIR)
    if not target.is_relative_to(config.SANDBOX_DIR.resolve()) or target.is_relative_to(run.folder):
        if not await request_approval(run, agent, f"write_file {target}"):
            raise PermissionError(f"human approval denied for writing {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} characters to {path}"


# Ask a human to approve a risky action. Recorded in SQLite; no answer in time = deny.
async def request_approval(run: Run, agent: str, action: str) -> bool:
    cursor = run.db.execute("INSERT INTO approvals (run_id, agent, action, status) VALUES (?, ?, ?, 'pending')",
                            (run.run_id, agent, action))
    run.db.commit()
    run.log(agent, "approval_needed", status="approval", output=action)
    if config.APPROVAL_MODE == "streamlit":
        approved = await wait_for_streamlit(run, cursor.lastrowid)
    else:
        approved = await asyncio.to_thread(ask_terminal, f"{agent} wants to: {action}")
    decision = "approved" if approved else "denied"
    run.db.execute("UPDATE approvals SET status = ? WHERE id = ?", (decision, cursor.lastrowid))
    run.db.commit()
    run.log(agent, "approval", status="ok" if approved else "denied", output=f"{decision}: {action}")
    return approved


# Terminal approval: y/n prompt with a timeout. No terminal attached (tests, scripts) = deny.
def ask_terminal(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    answer = []
    prompt = f"\n\033[36mAPPROVAL NEEDED\033[0m {question}\nApprove? [y/N] ({config.APPROVAL_TIMEOUT_SECONDS}s): "

    # Read one line; if input is closed (EOFError), simply give no answer, which means deny.
    def read_answer() -> None:
        try:
            answer.append(input(prompt))
        except EOFError:
            pass

    thread = threading.Thread(target=read_answer, daemon=True)
    thread.start()
    thread.join(config.APPROVAL_TIMEOUT_SECONDS)
    return bool(answer) and answer[0].strip().lower() == "y"


# Streamlit approval: wait for app.py to change the row from pending to approved or denied.
async def wait_for_streamlit(run: Run, approval_id: int) -> bool:
    for _ in range(int(config.APPROVAL_TIMEOUT_SECONDS * 2)):
        status = run.db.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()[0]
        if status != "pending":
            return status == "approved"
        await asyncio.sleep(0.5)
    return False


# Wrap tool output so the model sees clearly where untrusted data starts and ends.
def wrap(source: str, text: str) -> str:
    text = text.replace("</untrusted_data>", "</untrusted-data>")  # stop a file closing the tag early
    return f'<untrusted_data source="{source}">\n{text}\n</untrusted_data>'


# Flag text that looks like it is giving orders to an agent. Logged and noted, never obeyed.
def flag_injection(run: Run, agent: str, source: str, text: str) -> None:
    for pattern in config.INJECTION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            run.log(agent, "injection_suspected", status="injection", tool=source, output=match.group(0))
            note = f"injection suspected in {source}: '{match.group(0)}' (treated as data, not obeyed)"
            if note not in run.notes:
                run.notes.append(note)
            return


# Run one tool call for an agent: check permission, run it, log it, return the observation.
async def run_tool(run: Run, agent: str, tool: str, args: dict, allowed: list[str]) -> str:
    if tool not in allowed:
        run.log(agent, "tool_denied", status="denied", tool=tool, tool_args=args)
        return f"DENIED: {agent} may not use {tool}. Allowed tools: {', '.join(allowed) or 'none'}."
    try:
        if tool == "list_files":
            output = "\n".join(list_files(run))
        elif tool == "read_file":
            output = read_file(run, args["path"])
        elif tool == "grep":
            output = grep(run, args["pattern"])
        elif tool == "write_file":
            output = await write_file(run, agent, args["path"], args["content"])
        else:
            raise ValueError(f"unknown tool {tool}")
    except PermissionError as error:  # sandbox escape or human said no
        run.log(agent, "tool_call", status="blocked", tool=tool, tool_args=args, output=str(error))
        return f"BLOCKED: {error}"
    except Exception as error:  # a bad path or bad regex is reported to the agent, not fatal
        run.log(agent, "tool_call", status="error", tool=tool, tool_args=args, output=str(error))
        return f"ERROR: {error}"
    run.log(agent, "tool_call", tool=tool, tool_args=args, output=output)
    source = f"{tool}:{args.get('path', args.get('pattern', ''))}"
    flag_injection(run, agent, source, output)
    return wrap(source, output)
