# The one place that talks to a language model. call_llm() works the same for the real
# OpenAI-compatible provider (Mistral by default) and for the offline mock used in tests.
# It also spaces calls out (rate limiter) and retries with backoff on HTTP 429.
import asyncio
import json
import os
import re
import time

from openai import AsyncOpenAI, RateLimitError

from harness import config

# Mock provider settings. Tests put replies in MOCK_SCRIPT[agent_name]; they are used in order.
MOCK_SCRIPT: dict[str, list] = {}
MOCK_DELAY_SECONDS = 0.0

# Shared rate limiter state: one lock and the time of the last real call.
_lock = asyncio.Lock()
_last_call = 0.0
_client: AsyncOpenAI | None = None


# Send one request and return (reply text, input tokens, output tokens, seconds taken).
async def call_llm(system: str, messages: list[dict], agent_name: str, on_retry=None) -> tuple[str, int, int, float]:
    start = time.monotonic()
    if config.PROVIDER == "mock":
        text, in_tokens, out_tokens = await _mock_reply(system, messages, agent_name)
    else:
        text, in_tokens, out_tokens = await _real_reply(system, messages, on_retry)
    return text, in_tokens, out_tokens, round(time.monotonic() - start, 3)


# Wait until at least MIN_SECONDS_BETWEEN_CALLS has passed since the last call.
async def _wait_turn() -> None:
    global _last_call
    async with _lock:
        gap = config.MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_call = time.monotonic()


# Real provider: any OpenAI-compatible API. On 429 wait 1 s, 2 s, 4 s, then give up.
async def _real_reply(system: str, messages: list[dict], on_retry) -> tuple[str, int, int]:
    global _client
    if _client is None:
        # max_retries=0 so the only retries are ours, visible in the trace.
        _client = AsyncOpenAI(base_url=config.BASE_URL, api_key=os.environ[config.API_KEY_ENV],
                              max_retries=0, timeout=config.LLM_TIMEOUT_SECONDS)
    for delay in [*config.BACKOFF_SECONDS, None]:
        await _wait_turn()
        try:
            reply = await _client.chat.completions.create(
                model=config.MODEL, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, *messages])
            return reply.choices[0].message.content or "", reply.usage.prompt_tokens, reply.usage.completion_tokens
        except RateLimitError:
            if delay is None:
                raise
            if on_retry:
                on_retry(f"HTTP 429, waiting {delay}s")
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


# Mock provider: scripted replies first, then a sensible default for each role.
async def _mock_reply(system: str, messages: list[dict], agent_name: str) -> tuple[str, int, int]:
    await asyncio.sleep(MOCK_DELAY_SECONDS)
    queue = MOCK_SCRIPT.get(agent_name)
    if queue:
        reply = queue.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
    elif agent_name == "lead":
        # Default lead: one subtask per role named on the "Roles:" line of its task.
        roles = re.search(r"Roles: (.+)", messages[0]["content"]).group(1).split(", ")
        text = json.dumps({"final": {"subtasks": [
            {"id": r, "role": r, "instructions": f"Do the {r} job."} for r in roles]}})
    elif agent_name.startswith("checker"):
        text = json.dumps({"final": {"accept": True, "feedback": "ok"}})
    else:
        text = json.dumps({"final": {"findings": []}})
    # Rough token count: about 4 characters per token.
    prompt_chars = len(system) + sum(len(m["content"]) for m in messages)
    return text, prompt_chars // 4 + 1, len(text) // 4 + 1
