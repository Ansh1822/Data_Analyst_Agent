"""Section 3 - Thin LLM wrapper (Groq) + parsing helpers. Everything else calls llm.complete()."""
import asyncio
import json
import re

from groq import AsyncGroq, RateLimitError

from .config import GROQ_API_KEY, MODEL

_client = None
RETRY_WAITS = [4, 12, 30, 60]  # seconds; the free tier rate-limits per minute, so we wait and retry


async def complete(system: str, user: str) -> str:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env (free key: console.groq.com/keys).")
        _client = AsyncGroq(api_key=GROQ_API_KEY)

    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            resp = await _client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.1,   # low = more reliable code and JSON
                max_tokens=2048,   # keeps each call small, which helps the free tokens-per-minute cap
            )
            return resp.choices[0].message.content or ""
        except RateLimitError:
            if attempt == len(RETRY_WAITS):
                raise RuntimeError("Groq rate limit hit repeatedly. Wait a minute, or set ANALYST_MODEL=llama-3.1-8b-instant.")
            await asyncio.sleep(RETRY_WAITS[attempt])


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def parse_json_list(text: str) -> list:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON array found")
    return json.loads(m.group(0))
