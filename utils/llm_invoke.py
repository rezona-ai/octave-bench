"""Thin wrapper for invoking LLMs in eval pipelines.

`invoke()` routes on EVAL_JUDGE_PROVIDER:
    openai (default)  gpt-6-astra via Chat Completions, the v1 paper judge (utils/openai_judge.py)
    azure             the same model on Azure OpenAI
    anthropic         Claude via the Anthropic SDK (invoke_claude below), or `claude -p`
                      with EVAL_ALLOW_CC_FALLBACK=1
EVAL_JUDGE_MODEL overrides the model id for whichever provider is active.

Setup:
    Anthropic path only:
    1. pip install "anthropic>=0.50"
    2. Put ANTHROPIC_API_KEY=YOUR_KEY_HERE in the project-root .env file
       (or export it in your shell). The .env is read by a built-in loader,
       so no python-dotenv dependency is required.

Quick use:
    from utils.llm_invoke import invoke_claude

    resp = invoke_claude(
        user_prompt="...formatted eval prompt with source code...",
        system="...the long static evaluation system prompt...",
        cache_system=True,  # save ~90% on the long system prompt across runs
    )
    print(resp.text)
    print(resp.cache_read_input_tokens, "tokens served from cache")
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import anthropic

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(dotenv_path: Path, *, override: bool = False) -> None:
    """Minimal .env loader (replaces python-dotenv, no external dependency).

    Reads KEY=VALUE lines into os.environ. Missing file is a no-op (never raises),
    so eval runs on remotes that inject env vars directly still work. With
    override=False, existing os.environ values win.

    Only simple `KEY=VALUE` lines are supported (plus `#` comments, a leading
    `export `, and surrounding quotes). It does NOT implement python-dotenv's
    inline comments after a value, `\\n`/`\\t` escapes inside double quotes,
    `${VAR}` expansion, or multiline quoted values — add them here if a future
    .env needs them.
    """
    try:
        text = Path(dotenv_path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError, OSError):
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)


DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 32_000  # generous headroom for code-review JSON outputs
DEFAULT_THINKING = True       # adaptive thinking helps on long-code eval tasks

CC_FALLBACK_ENV = "EVAL_ALLOW_CC_FALLBACK"  # set to "1" to enable the cc subprocess fallback
CC_TIMEOUT_SECONDS = 600                    # per-call ceiling for `claude -p` subprocess

# Minimal generic system prompt used when the caller did NOT pass `system=`.
# Purpose: replace cc's default Claude-Code-runtime system prompt (~25 K tokens
# of agentic framing) with a near-empty one, so the cc path is hermetic and
# the model treats the user message as a direct instruction-following task —
# not as "Claude Code is interacting with the user". Kept intentionally generic
# so it does not bias eval verdict scoring; the eval rubric and instructions
# all live in the caller's user_prompt.
_CC_DEFAULT_SYSTEM_PROMPT = (
    "You are a non-interactive evaluation engine. Follow the user's "
    "instructions exactly and respond only with the content the user asks for, "
    "in the format the user specifies. Do not add preamble, explanation, or "
    "commentary beyond what the user requested."
)


def _safe_int(value: Any) -> int:
    """Coerce an unknown JSON value to int, returning 0 on any failure.

    cc's envelope `usage.*` fields are documented as ints today, but a future
    cc version emitting a string ("1.2K"), a dict, or a float ("1234.0") would
    otherwise crash int() and turn a successful eval call into a wrapper
    exception. We trade exact accuracy on the token counter for robustness.
    """
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

EffortLevel = Literal["low", "medium", "high", "max"]

_client: "anthropic.Anthropic | None" = None
_cc_announced = False  # gate the "using cc fallback" one-shot stderr notice


def _cc_fallback_enabled() -> bool:
    return os.environ.get(CC_FALLBACK_ENV) == "1"


def _get_client() -> "anthropic.Anthropic":
    global _client
    if _client is None:

        import anthropic  # noqa: PLC0415

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Either:\n"
                f"  1. Put it in {_PROJECT_ROOT / '.env'} or export it in your shell, or\n"
                "  2. Pass --allow-cc-fallback to main.py to use the local "
                "Claude Code CLI (`claude -p`)."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


@dataclass
class LLMResponse:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int

    @property
    def total_input_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def __str__(self) -> str:
        return self.text


def _invoke_via_cc(
    user_prompt: str,
    *,
    system: str | None,
    model: str,
) -> LLMResponse:
    """Run the prompt through the local `claude` CLI in non-interactive mode.

    Used when ANTHROPIC_API_KEY is not set and the caller (main.py) opted in via
    --allow-cc-fallback. Auth comes from the user's local Claude Code session;
    no key is required. Thinking is intentionally NOT enabled on this path.

    Tools, session persistence, and cc's default Claude-Code-runtime system
    prompt are all disabled unconditionally so every call is hermetic and
    prompt-cache-friendly. The caller's `system` is passed via `--system-prompt`
    when provided; otherwise a minimal generic system prompt is used in its
    place to defuse cc's default agent framing. `user_prompt` is fed through
    stdin so it is not bound by argv length limits.
    """
    if not shutil.which("claude"):
        raise RuntimeError(
            "claude CLI not found on PATH. Install with "
            "`npm i -g @anthropic-ai/claude-code` and run `claude login`, "
            "or set ANTHROPIC_API_KEY to use the Anthropic SDK directly."
        )

    global _cc_announced
    if not _cc_announced:
        print(
            "[llm-eval] ANTHROPIC_API_KEY not set; using local `claude -p` CLI "
            "fallback (thinking disabled).",
            file=sys.stderr,
            flush=True,
        )
        _cc_announced = True

    # Build the command with hermetic-eval flags:
    #   --tools ""                 : disable all tools. Eval prompt carries the
    #                                full source code so the model never needs
    #                                Read/Bash/Edit. Also prevents the model
    #                                from emitting tool-call JSON inside the
    #                                response text, which the downstream parser
    #                                would mistake for a verdict.
    #   --no-session-persistence   : don't write a session file to ~/.claude;
    #                                each eval call is stateless.
    #   --system-prompt <s>        : ALWAYS provided (caller's or our minimal
    #                                default) — replaces cc's default ~25 K-
    #                                token Claude-Code-runtime system prompt
    #                                with a much smaller one. Without this flag
    #                                cc loads the full agentic framing and the
    #                                "hermetic" claim of this path would not
    #                                hold for callers that don't pass `system=`
    #                                (which today is every llm-eval caller).
    cc_system = system if system is not None else _CC_DEFAULT_SYSTEM_PROMPT
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--system-prompt", cc_system,
    ]
    try:
        # encoding="utf-8" is explicit because `text=True` alone falls back to
        # locale.getpreferredencoding() — on a fresh Linux box without LANG /
        # LC_ALL set, that can resolve to ASCII and crash on Chinese prompts.
        result = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CC_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"claude CLI timed out after {CC_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        snippet = (result.stderr or result.stdout)[:500].strip()
        raise RuntimeError(
            f"claude CLI failed (rc={result.returncode}): {snippet}"
        )

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude CLI did not return valid JSON ({exc.msg}). "
            f"Raw stdout (first 500 chars): {result.stdout[:500]}"
        ) from None

    # cc -p --output-format json shape: {type, subtype, is_error, result, usage, ...}
    if envelope.get("is_error"):
        raise RuntimeError(
            f"claude CLI returned error envelope: "
            f"{envelope.get('result') or envelope.get('subtype') or envelope}"
        )

    text = envelope.get("result")
    if not isinstance(text, str):
        raise RuntimeError(
            f"claude CLI envelope missing string 'result' field; got: {envelope}"
        )

    usage = envelope.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}  # defensive: future cc versions might change usage shape
    return LLMResponse(
        text=text,
        model=envelope.get("model") or model,
        stop_reason=envelope.get("stop_reason"),
        input_tokens=_safe_int(usage.get("input_tokens")),
        output_tokens=_safe_int(usage.get("output_tokens")),
        cache_creation_input_tokens=_safe_int(usage.get("cache_creation_input_tokens")),
        cache_read_input_tokens=_safe_int(usage.get("cache_read_input_tokens")),
    )


def invoke_claude(
    user_prompt: str,
    system: str | None = None,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    cache_system: bool = False,
    thinking: bool = DEFAULT_THINKING,
    effort: EffortLevel | None = None,
) -> LLMResponse:
    """Send a prompt to a Claude model and return text + usage stats.

    Streams the request internally (using `.get_final_message()`) to avoid
    HTTP timeouts at large `max_tokens` — the caller still gets a single
    blocking call that returns the complete response.

    Routing:
        - ANTHROPIC_API_KEY set → Anthropic SDK (default path, full features).
        - Key unset + EVAL_ALLOW_CC_FALLBACK=1 → shell out to `claude -p`
          (no thinking, no caching, no max_tokens / effort knobs).
        - Key unset + flag unset → RuntimeError from _get_client().

    Args:
        user_prompt: The user-turn text.
        system: Optional system prompt (the long eval rubric, for our use case).
        model: Anthropic model ID. Defaults to `claude-opus-5`.
        max_tokens: Max output tokens. Defaults to 32000. SDK path only.
        cache_system: When True and `system` is provided, attach
            `cache_control: {"type": "ephemeral"}` to the system block. Use this
            when calling repeatedly with the SAME `system` and varying
            `user_prompt` — subsequent calls within the cache TTL pay ~10% the
            normal input price for the cached system tokens. Off by default
            because caching has a ~25% write premium on the first call.
            SDK path only — ignored on the cc fallback path.
        thinking: Enable adaptive extended thinking (default True). Set False
            for simple / cheap calls where reasoning isn't useful. SDK path
            only — cc fallback path always runs without thinking.
        effort: One of "low" | "medium" | "high" | "max". Controls overall
            depth of reasoning and tool use. Leave None to use the model
            default (currently "high"). SDK path only.

    Returns:
        LLMResponse with `.text` and usage counters (including cache hits).
        On the cc fallback path, usage fields are populated from the JSON
        envelope when present, else 0.

    Raises:
        anthropic.APIError (or one of its typed subclasses) on API failure.
        RuntimeError if no auth path is available, or if the cc subprocess fails.
    """
    if _cc_fallback_enabled() and not os.environ.get("ANTHROPIC_API_KEY"):
        return _invoke_via_cc(user_prompt, system=system, model=model)

    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    if system is not None:
        if cache_system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            kwargs["system"] = system

    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    if effort is not None:
        kwargs["output_config"] = {"effort": effort}

    with client.messages.stream(**kwargs) as stream:
        final = stream.get_final_message()

    text = "".join(block.text for block in final.content if block.type == "text")

    usage = final.usage
    return LLMResponse(
        text=text,
        model=final.model,
        stop_reason=final.stop_reason,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )


JUDGE_PROVIDER_ENV = "EVAL_JUDGE_PROVIDER"  # openai (default) | azure | anthropic
JUDGE_MODEL_ENV = "EVAL_JUDGE_MODEL"


def invoke(user_prompt: str, system: str | None = None, **kwargs: Any) -> LLMResponse:
    """Judge entrypoint used by the eval chain; routes on EVAL_JUDGE_PROVIDER."""
    provider = os.environ.get(JUDGE_PROVIDER_ENV, "openai").lower()
    if os.environ.get(JUDGE_MODEL_ENV):
        kwargs.setdefault("model", os.environ[JUDGE_MODEL_ENV])
    if provider == "anthropic":
        return invoke_claude(user_prompt, system, **kwargs)
    if provider in ("openai", "azure"):
        from utils.openai_judge import invoke_openai  # noqa: PLC0415
        return invoke_openai(user_prompt, system, provider=provider, **kwargs)
    raise RuntimeError(f"unknown {JUDGE_PROVIDER_ENV}={provider!r} (openai | azure | anthropic)")
