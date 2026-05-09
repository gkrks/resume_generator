"""Base agent class — thin wrapper around the Anthropic Messages API.

Supports prompt caching: pass `cached_system` to prepend a cached block
(e.g., master_resume) before the agent-specific system prompt.
"""

import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.Anthropic()

MODEL_SONNET = "claude-sonnet-4-20250514"
MODEL_HAIKU = "claude-haiku-4-5-20251001"


def call_agent(
    *,
    system: str,
    user_message: str,
    model: str = MODEL_SONNET,
    max_tokens: int = 16384,
    temperature: float = 0.3,
    cached_system: str | None = None,
) -> str:
    """Send a single-turn message via streaming with optional prompt caching.

    Args:
        system: Agent-specific system prompt.
        user_message: The user message.
        model: Model to use.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        cached_system: Optional large context (e.g., master_resume) to cache.
                       Placed before `system` with a cache_control breakpoint.
    """
    if cached_system:
        system_blocks = [
            {
                "type": "text",
                "text": cached_system,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": system},
        ]
    else:
        system_blocks = system

    text_parts = []
    with _client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_blocks,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            text_parts.append(text)
    return "".join(text_parts)


def call_agent_json(
    *,
    system: str,
    user_message: str,
    model: str = MODEL_SONNET,
    max_tokens: int = 16384,
    temperature: float = 0.2,
    cached_system: str | None = None,
) -> dict:
    """Call agent expecting a JSON response with optional prompt caching."""
    raw = call_agent(
        system=system,
        user_message=user_message,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        cached_system=cached_system,
    )
    return _parse_json(raw)


def _parse_json(text: str) -> dict:
    """Extract JSON from a response that may include markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return json.loads(text[start:end].strip())
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return json.loads(text[start:end].strip())
    first_brace = text.index("{")
    last_brace = text.rindex("}") + 1
    return json.loads(text[first_brace:last_brace])


def master_resume_cache_block(master_resume: dict) -> str:
    """Format master_resume as a cacheable system prompt block."""
    return (
        "## Master Resume (source of truth for all bullet matching)\n\n"
        f"```json\n{json.dumps(master_resume, indent=2)}\n```"
    )


def warm_cache(master_resume: dict) -> None:
    """Prime the prompt cache with master_resume using a cheap Haiku call.

    Call this ONCE before parallel fan-out so all subsequent Sonnet calls
    within 5 minutes hit the warm cache instead of each paying full price.
    """
    cached = master_resume_cache_block(master_resume)
    # Minimal call — 1 token output, just enough to register the cache
    with _client.messages.stream(
        model=MODEL_HAIKU,
        max_tokens=1,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": cached,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": "Acknowledge."},
        ],
        messages=[{"role": "user", "content": "ping"}],
    ) as stream:
        for _ in stream.text_stream:
            pass
    print("  [cache] Master resume cached for ~5 minutes")
