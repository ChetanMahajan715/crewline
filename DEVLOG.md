# DEVLOG

Honest log of real bugs, failed runs and wrong assumptions: what happened, what the harness did, what we changed.

## Phase 1: setup
- No system Python on the machine (only the Microsoft Store alias). Used `uv venv .venv --python 3.12`, which fetched a uv-managed CPython 3.12.14. All packages live in `.venv`.
- `pip` resolved `openai==3.31.0`, a newer major version than expected. Checked the installed client: `AsyncOpenAI().chat.completions.create` and `response_format` are unchanged, so no code change was needed.
- Brand files arrived in the project root, not `brand/`. Moved them to `brand/` as the spec expects.
