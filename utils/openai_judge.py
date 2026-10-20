"""OpenAI / Azure OpenAI judge backend (the v1 paper judge: gpt-6-astra).

Same call shape as `utils.llm_invoke.invoke_claude`, so the judge chain
(`static_eval` → `eval_json.invoke_json_with_retry`) can use it unchanged:
`invoke_openai(user_prompt=..., thinking=...) -> LLMResponse`.

Settings used for the v1 results:
    API                    Chat Completions (not the Responses API)
    model                  "gpt-6-astra" (on Azure: a deployment of that name)
    max_completion_tokens  16000
    temperature            not set (server default)
    reasoning_effort       not set
    timeout                900 s per request, up to 10 retries

Providers (env EVAL_JUDGE_PROVIDER, see utils/llm_invoke.py):
    openai  OPENAI_API_KEY, optional OPENAI_BASE_URL (default https://api.openai.com/v1)
    azure   AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, optional AZURE_OPENAI_DEPLOYMENT
            (default gpt-6-astra) and AZURE_OPENAI_API_VERSION (default 2024-10-21)

Stdlib only (urllib); no openai SDK dependency.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from utils.llm_invoke import LLMResponse, _safe_int

DEFAULT_OPENAI_MODEL = "gpt-6-astra"
DEFAULT_MAX_COMPLETION_TOKENS = 16_000
REQUEST_TIMEOUT_SECONDS = 900
MAX_RETRIES = 10
MAX_BACKOFF_SECONDS = 180  # a 60 s cap retries inside Azure's TPM window and hits the limit again

# 52x are Cloudflare edge errors; OpenAI's front end returns 520 now and then.
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527}
# Out of credit: fail at once instead of backing off on every case.
PERMANENT_MARKERS = ("insufficient_quota", "credit_balance_exhausted", "no credits remaining")


def _endpoint(provider: str, model: str) -> tuple[str, dict[str, str], bool]:
    """Return (url, headers, send_model_field)."""
    if provider == "azure":
        base = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        key = os.environ.get("AZURE_OPENAI_KEY")
        if not base or not key:
            raise RuntimeError("EVAL_JUDGE_PROVIDER=azure needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", model)
        version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={version}"
        # Azure picks the model from the deployment in the URL; a `model` field in the body is an error.
        return url, {"api-key": key, "content-type": "application/json"}, False
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (put it in .env or export it)")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return f"{base}/chat/completions", {"Authorization": f"Bearer {key}", "content-type": "application/json"}, True


def _retry_after(headers: Any) -> float:
    try:
        return float(headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        return 0.0


def invoke_openai(
    user_prompt: str,
    system: str | None = None,
    *,
    model: str = DEFAULT_OPENAI_MODEL,
    max_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    provider: str | None = None,
    effort: str | None = None,
    thinking: bool | None = None,       # Anthropic-only; accepted and ignored
    cache_system: bool | None = None,   # Anthropic-only; accepted and ignored
) -> LLMResponse:
    """Send one Chat Completions request and return text + usage.

    `max_tokens` is sent as `max_completion_tokens` (this model rejects `max_tokens`).
    `effort` is sent as `reasoning_effort` only when given; the v1 judge never set it.
    """
    provider = provider or os.environ.get("EVAL_JUDGE_PROVIDER", "openai")
    url, headers, send_model = _endpoint(provider, model)
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user_prompt}]
    body: dict[str, Any] = {"messages": messages, "max_completion_tokens": max_tokens}
    if send_model:
        body["model"] = model
    if effort is not None:
        body["reasoning_effort"] = effort
    data = json.dumps(body).encode("utf-8")

    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if any(m in text for m in PERMANENT_MARKERS):
                raise RuntimeError(f"judge API out of credit (HTTP {e.code}): {text[:300]}") from None
            if e.code not in RETRY_STATUS or attempt == MAX_RETRIES:
                raise RuntimeError(f"judge API HTTP {e.code}: {text[:500]}") from None
            wait = _retry_after(e.headers)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"judge API unreachable: {e!r}") from None
            wait = 0.0
        sleep = max(wait, min(MAX_BACKOFF_SECONDS, 2 ** attempt)) + random.random() * 2
        print(f"[llm-eval] judge retry {attempt + 1}/{MAX_RETRIES} in {sleep:.0f}s", file=sys.stderr, flush=True)
        time.sleep(sleep)

    choice = (payload.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = _safe_int(details.get("cached_tokens"))
    # OpenAI's prompt_tokens includes cache hits; Anthropic's input_tokens does not. Map to the Anthropic shape.
    return LLMResponse(
        text=text,
        model=payload.get("model") or model,
        stop_reason=choice.get("finish_reason"),
        input_tokens=_safe_int(usage.get("prompt_tokens")) - cached,
        output_tokens=_safe_int(usage.get("completion_tokens")),
        cache_creation_input_tokens=_safe_int(details.get("cache_write_tokens")),
        cache_read_input_tokens=cached,
    )
