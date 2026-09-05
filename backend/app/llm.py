"""One streamed completion, routed through LiteLLM.

LiteLLM rather than a hand-rolled client because the endpoint is not fixed:
this runs against a self-hosted vLLM and against Google's OpenAI-compatible
endpoint, and those two disagree about how you ask for reasoning. LiteLLM
normalises the call and, with `drop_params`, silently discards a parameter the
current provider does not understand instead of failing the request.

Facts behind the non-obvious lines here, all measured against the live vLLM:

1. **Streaming is mandatory.** A non-streamed call returned HTTP 524 after
   ~125s — Cloudflare closes an idle origin request at ~100s. Streamed, the
   first token arrives in under a second.
2. **The User-Agent decides whether you are served at all.** With no header,
   with `Python-urllib`, and with the OpenAI SDK's own `OpenAI/Python 1.109.1`,
   the endpoint returns 403. LiteLLM's own UA passes, which is the reason for
   the `hosted_vllm/` prefix rather than `openai/`.
3. **Reasoning arrives on `delta.reasoning`**, not `delta.reasoning_content`
   that most clients look for, so the channel is invisible unless you check
   both. LiteLLM maps it to `reasoning_content`; the raw name is checked too,
   in case the mapping changes.
"""

from __future__ import annotations

from typing import Callable

import litellm

from app.config import Settings

# Providers disagree about reasoning parameters. Drop what this one cannot take
# rather than failing the call — the alternative is a provider-specific branch
# at every call site.
litellm.drop_params = True
litellm.suppress_debug_info = True


def _thinking_params(setting: str) -> dict:
    """Translate one setting into whatever the provider understands.

    `reasoning_effort` is the portable spelling. `chat_template_kwargs` is
    vLLM's, and is the only way to switch a hybrid model's thinking off
    entirely; LiteLLM drops it where it means nothing.
    """
    thinking = setting.strip().lower()
    if thinking in ("off", "false", "none", "0"):
        return {
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        }
    if thinking in ("low", "medium", "high"):
        return {
            "reasoning_effort": thinking,
            "chat_template_kwargs": {"enable_thinking": True},
        }
    return {}


async def stream_completion(
    settings: Settings,
    prompt: str,
    *,
    on_token: Callable[[str], None] | None = None,
    on_thought: Callable[[str], None] | None = None,
) -> str:
    """Stream one completion and return the assistant's text.

    No `max_tokens`: the server's own default applies. Capping it is what lets
    a long reasoning pass end at `length` with nothing to show for it — a
    4,000-token cap produced 285s of reasoning and zero characters of answer.
    """
    response = await litellm.acompletion(
        model=settings.litellm_model,
        api_key=settings.llm_api_key,
        api_base=settings.llm_base_url,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        temperature=0,
        timeout=settings.agent_timeout,
        extra_headers={"User-Agent": settings.llm_user_agent},
        **_thinking_params(settings.llm_thinking),
    )

    answer: list[str] = []
    async for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue

        thought = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
        if thought and on_thought:
            on_thought(thought)

        piece = getattr(delta, "content", None)
        if piece:
            answer.append(piece)
            if on_token:
                on_token(piece)

    return "".join(answer)
