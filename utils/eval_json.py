"""Robust JSON extraction for LLM eval verdicts.

Eval prompts ask the model for a single JSON object, but models occasionally
emit malformed JSON (stray prose, code fences, trailing commas, a truncated
tail). ``invoke_json_with_retry`` makes parsing resilient in two layers:

  1. **Local salvage (free, instant)** — strip markdown fences, slice out the
     outermost ``{...}`` object, drop trailing commas, then ``json.loads``.
  2. **LLM retry (costs an extra call)** — if salvage still fails, re-invoke the
     model up to ``max_retries`` times with a corrective nudge telling it the
     previous output was unparseable and to return ONLY valid JSON.

Only after every attempt fails does it raise ``json.JSONDecodeError`` (with the
raw-response file path in the message, mirroring the previous behavior).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_fences(text: str) -> str:
    """Drop a leading ```/```json fence and the closing ``` if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _salvage(text: str) -> str:
    """Best-effort local repair: slice the outermost object, kill trailing commas."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    return _TRAILING_COMMA.sub(r"\1", text)


def parse_eval_json(text: str) -> tuple[dict[str, Any] | None, json.JSONDecodeError | None]:
    """Try strict parse, then local salvage. Return (parsed_dict, None) on success
    or (None, last_error) on failure."""
    cleaned = _strip_fences(text)
    candidates = [cleaned]
    salvaged = _salvage(cleaned)
    if salvaged != cleaned:
        candidates.append(salvaged)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if isinstance(obj, dict):
            return obj, None
        # Parsed but not an object (e.g. a list / string) — treat as malformed.
        last_exc = json.JSONDecodeError("top-level JSON value is not an object", candidate, 0)
    return None, last_exc


VALIDATION_ERROR_KEY = "_validation_error"


def invoke_json_with_retry(
    invoke: Callable[..., Any],
    prompt: str,
    *,
    raw_path: Path | None,
    max_retries: int = 2,
    thinking: bool = True,
    validate: Callable[[dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    """Invoke an LLM and return its response parsed as a JSON object, robustly.

    ``invoke`` is called as ``invoke(user_prompt=..., thinking=...)`` and must
    return an object with a ``.text`` attribute (the ``invoke_claude`` shape).
    The latest raw response is written to ``raw_path`` (best-effort; on OSError
    the path is dropped and saving is skipped). Tries local salvage first, then
    re-invokes up to ``max_retries`` extra times before raising.

    ``validate``, when given, is applied to every successfully parsed object
    and returns ``None`` when the object is acceptable or a human-readable
    problem description otherwise (e.g. "missing checklist keys: …"). A
    validation failure is retried like a parse failure, with the description
    fed back to the model. If every attempt parses but none validates, the
    LAST parsed object is returned with the problem recorded under
    ``VALIDATION_ERROR_KEY`` rather than raising — a flawed verdict with a
    visible warning beats losing the whole case.
    """
    last_exc: json.JSONDecodeError | None = None
    last_problem: str | None = None
    last_parsed: dict[str, Any] | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        if attempt == 0:
            call_prompt = prompt
        elif last_problem is not None:
            call_prompt = (
                f"{prompt}\n\n---\nIMPORTANT: your previous response parsed as JSON but "
                f"violated the required output contract: {last_problem}. Re-read §Output "
                "Format and output ONLY a single valid JSON object that satisfies it — "
                "every checklist item verbatim as its own key, the two auxiliary-dimension "
                "keys, the exact value formats, and no extra prose."
            )
        else:
            detail = f" (parser error: {last_exc.msg})" if last_exc else ""
            call_prompt = (
                f"{prompt}\n\n---\nIMPORTANT: your previous response could not be parsed "
                f"as JSON{detail}. Output ONLY a single valid JSON object — no markdown "
                "fences, no prose before or after, no trailing commas, and ensure every "
                "string is properly quoted and its inner quotes/newlines escaped."
            )

        resp = invoke(user_prompt=call_prompt, thinking=thinking)
        text = resp.text

        if raw_path is not None:
            try:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(text, encoding="utf-8")
            except OSError:
                raw_path = None  # don't fail eval just because we couldn't save raw

        parsed, last_exc = parse_eval_json(text)
        if parsed is None:
            last_problem = None
            continue
        if validate is None:
            return parsed
        last_parsed = parsed
        last_problem = validate(parsed)
        if last_problem is None:
            return parsed

    if last_parsed is not None:
        last_parsed[VALIDATION_ERROR_KEY] = (
            f"{last_problem} [after {attempts} attempt(s)]"
        )
        return last_parsed

    hint = f" (raw response: {raw_path})" if raw_path else ""
    assert last_exc is not None  # parse failure always records an error
    raise json.JSONDecodeError(
        f"{last_exc.msg} [after {attempts} attempt(s)]{hint}",
        last_exc.doc,
        last_exc.pos,
    ) from None
