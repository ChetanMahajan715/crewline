# The four tools agents can use: list_files, read_file, grep, write_file. No shell, no web.
# Every call is checked against the role's allowed tools, and every result is wrapped as
# untrusted data so the model treats file content as data, not as orders.
import re

from harness.state import Run

# Folders that are never part of the task.
SKIP_DIRS = {".git", "__pycache__", ".venv"}


# All files in the task folder, as relative paths with forward slashes.
def list_files(run: Run) -> list[str]:
    return sorted(p.relative_to(run.folder).as_posix() for p in run.folder.rglob("*")
                  if p.is_file() and not SKIP_DIRS & set(p.relative_to(run.folder).parts))


# Read one file with line numbers, so agents can cite lines.
def read_file(run: Run, path: str) -> str:
    lines = (run.folder / path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(f"{n:4}| {line}" for n, line in enumerate(lines, 1))


# Search every file for a regular expression; return up to 50 "file:line: text" hits.
def grep(run: Run, pattern: str) -> str:
    hits = []
    for name in list_files(run):
        for n, line in enumerate((run.folder / name).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(pattern, line):
                hits.append(f"{name}:{n}: {line.strip()}")
    return "\n".join(hits[:50]) or "no matches"


# Wrap tool output so the model sees clearly where untrusted data starts and ends.
def wrap(source: str, text: str) -> str:
    text = text.replace("</untrusted_data>", "</untrusted-data>")  # stop a file closing the tag early
    return f'<untrusted_data source="{source}">\n{text}\n</untrusted_data>'


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
        else:
            raise ValueError(f"unknown tool {tool}")
    except Exception as error:  # a bad path or bad regex is reported to the agent, not fatal
        run.log(agent, "tool_call", status="error", tool=tool, tool_args=args, output=str(error))
        return f"ERROR: {error}"
    run.log(agent, "tool_call", tool=tool, tool_args=args, output=output)
    return wrap(f"{tool}:{args.get('path', args.get('pattern', ''))}", output)
