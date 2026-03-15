"""AEGIS AI agent — OpenAI gpt-4.1 integration for mission control queries."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional

import httpx

# Import config — handle the hyphenated directory name
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

from services import database

SYSTEM_PROMPT = (
    "You are AEGIS — the mission control AI for Omneforge IT infrastructure. "
    "You are authoritative, precise and calm like an ISS flight director. "
    "You respond in maximum three sentences. Never express uncertainty — "
    "if data is unavailable, say 'Data unavailable.' "
    "You refer to servers by their actual names. "
    "You respond in the same language as the question. "
    "Current context will be injected with each query."
)

MODEL = "gpt-4.1"
MAX_TOKENS = 150
TIMEOUT_SECONDS = 8
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

FALLBACK_RESPONSE = {
    "answer": "Data unavailable. Check Orion Hub.",
    "tokens_used": 0,
}


async def _build_context(env: Optional[str] = None) -> str:
    """Build context string from recent events and status summary."""
    parts: List[str] = []

    # Active environment
    if env:
        parts.append(f"Active environment: {env}")

    # Last 10 events
    recent = await database.get_recent_events(limit=10)
    if recent:
        parts.append("Last 10 events:")
        for e in recent:
            parts.append(
                f"  [{e['timestamp']}] {e['severity']} | {e['env']} | "
                f"{e['source']}: {e['title']}"
            )
    else:
        parts.append("No recent events recorded.")

    # Status summary per environment
    envs = ["CEDERVALL", "VALVX", "GWSK", "PERSONAL"]
    parts.append("\nStatus summary:")
    for env_name in envs:
        counts = await database.get_events_count_by_env_and_severity(env_name, hours=24)
        total_alerts = sum(counts.values())
        critical = counts.get("CRITICAL", 0)
        intrusion = counts.get("INTRUSION", 0)
        threat = "HIGH" if (critical > 0 or intrusion > 0) else ("MEDIUM" if total_alerts > 5 else "LOW")
        last = await database.get_last_event_for_env(env_name)
        last_str = last["title"] if last else "No events"
        parts.append(
            f"  {env_name}: alerts_24h={total_alerts}, "
            f"threat_level={threat}, last_event='{last_str}'"
        )

    return "\n".join(parts)


async def _call_openai(question: str, context: str, api_key: str) -> dict:
    """Make a single call to OpenAI. Returns {"answer": str, "tokens_used": int}."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Context:\n{context}"},
            {"role": "user", "content": question},
        ],
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.post(OPENAI_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]["message"]["content"].strip()
    tokens = data.get("usage", {}).get("total_tokens", 0)

    return {"answer": choice, "tokens_used": tokens}


async def query(question: str, env: Optional[str] = None) -> dict:
    """Query AEGIS AI with context injection.

    On timeout: returns fallback.
    On 429 (rate limit): waits 5s, retries once.
    """
    api_key = config.OPENAI_API_KEY
    if not api_key:
        return {
            "answer": "Data unavailable. OpenAI API key not configured.",
            "tokens_used": 0,
        }

    context = await _build_context(env)

    try:
        return await _call_openai(question, context, api_key)
    except httpx.TimeoutException:
        print(f"[AI_AGENT] Timeout after {TIMEOUT_SECONDS}s")
        return dict(FALLBACK_RESPONSE)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            print("[AI_AGENT] Rate limited (429). Retrying in 5s...")
            await asyncio.sleep(5)
            try:
                return await _call_openai(question, context, api_key)
            except Exception as retry_exc:
                print(f"[AI_AGENT] Retry failed: {retry_exc}")
                return dict(FALLBACK_RESPONSE)
        print(f"[AI_AGENT] HTTP error: {exc.response.status_code}")
        return dict(FALLBACK_RESPONSE)
    except Exception as exc:
        print(f"[AI_AGENT] Unexpected error: {exc}")
        return dict(FALLBACK_RESPONSE)
