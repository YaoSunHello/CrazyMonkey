"""One streamed completion against an OpenAI-compatible endpoint.

Small on purpose. The loop needs exactly one thing from the model — a long
generation, streamed — and every line here exists because something measured
demanded it.

Three facts about this endpoint, all verified against the live server:

1. **Streaming is mandatory.** A non-streamed call returns HTTP 524 after
   ~125s: Cloudflare closes an idle origin request at ~100s. Streaming puts
   the first token on the wire in under a second and the connection stays up.
2. **The User-Agent decides whether you get in at all.** No UA, `Python-urllib`
   and the real OpenAI SDK string (`OpenAI/Python 1.109.1`) are all rejected
   403 by Cloudflare. A descriptive one passes. The header is set here, in the
   one place every request goes through.
3. **This is a hybrid reasoning model.** vLLM streams its thinking in
   `delta.reasoning` — note, *not* `delta.reasoning_content`, which is what
   most clients look for, so the channel is invisible to them. When thinking
   runs long it can consume an entire `max_tokens` budget and finish with
   `length`, empty content and no tool calls. Sending no `max_tokens` at all
   avoids that; `enable_thinking` below turns the channel off entirely if you
   want the tokens spent on the answer instead.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Callable

from app.config import Settings


def _request(settings: Settings, payload: dict) -> urllib.request.Request:
    request = urllib.request.Request(
        settings.llm_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
    )
    request.add_header("Authorization", f"Bearer {settings.llm_api_key}")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", settings.llm_user_agent)
    return request


def _stream(settings: Settings, payload: dict, on_token, on_thought) -> str:
    answer: list[str] = []
    with urllib.request.urlopen(_request(settings, payload), timeout=settings.agent_timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            body = line[6:]
            if body == "[DONE]":
                break
            try:
                delta = json.loads(body)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

            thought = delta.get("reasoning") or delta.get("reasoning_content")
            if thought and on_thought:
                on_thought(thought)

            piece = delta.get("content")
            if piece:
                answer.append(piece)
                if on_token:
                    on_token(piece)
    return "".join(answer)


async def stream_completion(
    settings: Settings,
    prompt: str,
    *,
    on_token: Callable[[str], None] | None = None,
    on_thought: Callable[[str], None] | None = None,
) -> str:
    """Stream one completion and return the assistant's text.

    No `max_tokens`: the server's own default applies. Capping it is what lets
    a long reasoning pass finish with `length` and nothing to show for it.
    """
    payload = {
        "model": settings.resolved_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0,
    }
    thinking = settings.llm_thinking.strip().lower()
    if thinking in ("off", "false", "none", "0"):
        # Passed through to the chat template: the whole budget goes to the answer.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    elif thinking in ("low", "medium", "high"):
        # Keep the channel, but bound it. Unbounded reasoning on this task ran
        # to 120k characters without producing an answer.
        payload["reasoning_effort"] = thinking
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    return await asyncio.to_thread(_stream, settings, payload, on_token, on_thought)
