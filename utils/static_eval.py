"""Shared harness for the static-code judges in `llm-eval/` (2D_eval.py, 3D_eval.py).

Each judge owns only its rubric text; everything else — collecting the project,
filling the template, calling the model, validating the verdict against the
output contract and recomputing `total_score` — lives here so the two scripts
cannot drift apart.

Template contract
-----------------
A rubric template is a plain string (NOT an f-string / `.format` template):

* A line consisting solely of `{name}` is a **data block** and is replaced by
  the corresponding value from `fill_template(..., data)`. Inline `{name}`
  references inside sentences are left as-is on purpose — they point the
  judge back at the §1 data block instead of duplicating large payloads.
* `{{` / `}}` are literal-brace escapes (used in the JSON output example and
  in JSX snippets such as `style={{{{ ... }}}}`, which renders as `style={{ ... }}`).

Both are handled in ONE regex pass over the bare template, so inserted data is
never re-scanned: braces inside the agent's source code are preserved verbatim
and a source line that happens to read `{attachments}` is not substituted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from utils.eval_json import VALIDATION_ERROR_KEY, invoke_json_with_retry
from utils.tools import (
    build_artifact_status,
    build_file_manifest,
    build_gate_note,
    collect_source_code,
)

# The two auxiliary-dimension keys every verdict must carry (§5.2 rule 2).
AUX_KEYS: tuple[str, str] = ("关卡/场景/游戏数值", "反馈与 Juice(打击感/音效/粒子)")
TOTAL_KEY = "total_score"
# Filled in by `normalize_verdict` when the model's own total disagreed with the
# recomputed one, so the discrepancy stays auditable.
MODEL_TOTAL_KEY = "total_score_model"

# Hidden inference probes (想全率层): reported under this key, never in total_score.
HIDDEN_KEY = "hidden_probes"
HIDDEN_SCORE_KEY = "hidden_score"

_ITEM_VALUE_RE = re.compile(r"^[01],")          # "1, " / "0, <reason>"
_AUX_VALUE_RE = re.compile(r"^[0-5];")          # "<0-5>;<reason>"
_PASS_RE = re.compile(r"^1,\s*$")               # the literal pass marker
_HIDDEN_PASS_RE = re.compile(r"^1,")             # hidden probes cite evidence on pass

# One pass: literal-brace escape OR a whole-line data-block placeholder.
_TEMPLATE_TOKEN_RE = re.compile(r"\{\{|\}\}|^\{(\w+)\}$", re.MULTILINE)


def fill_template(template: str, data: dict[str, str]) -> str:
    """Un-escape `{{`/`}}` and substitute whole-line `{name}` blocks in one pass."""

    def _repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name is None:                      # `{{` or `}}`
            return m.group(0)[0]
        return data.get(name, m.group(0))     # unknown placeholder: leave as-is

    return _TEMPLATE_TOKEN_RE.sub(_repl, template)


def coerce_checklist(raw: Any) -> list[str]:
    """Validate the case's `checklist` field: a non-empty list of non-empty strings."""
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "base_info['checklist'] must be a non-empty list of strings; "
            f"got {type(raw).__name__} with {len(raw) if hasattr(raw, '__len__') else '?'} item(s)"
        )
    items = []
    for i, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"checklist[{i}] must be a non-empty string; got {item!r}")
        items.append(item)
    return items


def validate_verdict(verdict: dict[str, Any], checklist: list[str],
                     hidden: list[str] | tuple[str, ...] = ()) -> str | None:
    """Check a parsed verdict against the §5 output contract.

    Returns None when acceptable, else a short description of the first
    problem class found (fed back to the model on retry). Extra keys are
    tolerated; `total_score` is NOT trusted here — `normalize_verdict`
    recomputes it from the per-item scores.
    """
    missing = [k for k in checklist if k not in verdict]
    if missing:
        shown = "; ".join(repr(k) for k in missing[:3])
        more = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
        return f"missing {len(missing)} checklist key(s) that must appear verbatim: {shown}{more}"

    bad_items = [k for k in checklist if not (isinstance(verdict[k], str) and _ITEM_VALUE_RE.match(verdict[k]))]
    if bad_items:
        return (
            f"{len(bad_items)} checklist value(s) do not follow the \"<0|1>, <reason>\" format, "
            f"e.g. {bad_items[0]!r} -> {verdict[bad_items[0]]!r}"
        )

    missing_aux = [k for k in AUX_KEYS if k not in verdict]
    if missing_aux:
        return f"missing auxiliary-dimension key(s): {missing_aux}"
    bad_aux = [k for k in AUX_KEYS if not (isinstance(verdict[k], str) and _AUX_VALUE_RE.match(verdict[k]))]
    if bad_aux:
        return (
            f"auxiliary value for {bad_aux[0]!r} does not follow the \"<0-5>;<reason>\" format: "
            f"{verdict[bad_aux[0]]!r}"
        )
    if hidden:
        hp = verdict.get(HIDDEN_KEY)
        if not isinstance(hp, dict):
            return f"missing '{HIDDEN_KEY}' object (one entry per hidden probe, verbatim keys)"
        missing_h = [k for k in hidden if k not in hp]
        if missing_h:
            shown = "; ".join(repr(k) for k in missing_h[:2])
            return f"'{HIDDEN_KEY}' missing {len(missing_h)} probe key(s): {shown}"
        bad_h = [k for k in hidden if not (isinstance(hp[k], str) and _ITEM_VALUE_RE.match(hp[k]))]
        if bad_h:
            return (
                f"{HIDDEN_KEY}[{bad_h[0]!r}] does not follow the \"<0|1>, <reason>\" format: "
                f"{hp[bad_h[0]]!r}"
            )
    return None


def normalize_verdict(verdict: dict[str, Any], checklist: list[str],
                      hidden: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """Recompute `total_score` from the per-item scores (never trust the model's arithmetic).

    Items missing from the verdict count as not passed. When the model's own
    total differs, it is preserved under `total_score_model` for auditing.
    """
    passed = sum(
        1 for k in checklist
        if isinstance(verdict.get(k), str) and _PASS_RE.match(verdict[k])
    )
    recomputed = f"{passed}/{len(checklist)}"
    reported = verdict.get(TOTAL_KEY)
    if reported is not None and str(reported).replace(" ", "") != recomputed:
        verdict[MODEL_TOTAL_KEY] = reported
    verdict[TOTAL_KEY] = recomputed
    if hidden:
        hp = verdict.get(HIDDEN_KEY)
        hp = hp if isinstance(hp, dict) else {}
        h_passed = sum(
            1 for k in hidden
            if isinstance(hp.get(k), str) and _HIDDEN_PASS_RE.match(hp[k])
        )
        verdict[HIDDEN_SCORE_KEY] = f"{h_passed}/{len(hidden)}"
    return verdict


def run_static_eval(
    template: str,
    base_info: dict[str, Any],
    output_file_path: str | Path,
    *,
    project_root: Path,
    invoke: Callable[..., Any] | None = None,
    max_retries: int = 2,
    thinking: bool = True,
) -> dict[str, Any]:
    """Evaluate one agent-generated project with `template` and return the verdict.

    Args:
        template: The scenario rubric (TWO_D_EVALUATION_PROMPT / THREE_D_…).
        base_info: Case metadata; requires `prompt` (str) and `checklist`
            (non-empty list[str]); optional `attachment` (list[str]).
        output_file_path: The project directory, absolute or relative to
            `project_root`.
        project_root: Repository root used to resolve relative paths.
        invoke: LLM call, `invoke(user_prompt=..., thinking=...) -> .text`.
            Defaults to `utils.llm_invoke.invoke` **looked up at call
            time** (late-bound), so test taps / usage meters that monkeypatch
            the module attribute are honored — a def-time default would freeze
            the original function and silently bypass them.

    Returns:
        The parsed verdict with `total_score` recomputed by the harness. If the
        model never produced a contract-conforming object, the best attempt is
        returned with the problem under `_validation_error`.
    """
    if invoke is None:  # late-bind so a monkeypatched invoke is honored
        from utils import llm_invoke as _li
        invoke = _li.invoke
    user_prompt = str(base_info["prompt"])
    checklist_items = coerce_checklist(base_info.get("checklist"))
    hidden_raw = base_info.get("hidden_checklist") or []
    # Only enforce the hidden contract when the rubric actually carries the
    # data block — web rubrics don't, and must keep working with case dicts
    # that happen to include `hidden_checklist`.
    hidden_items = (
        coerce_checklist(hidden_raw)
        if hidden_raw and "{hidden_checklist}" in template else []
    )
    checklist = json.dumps(checklist_items, ensure_ascii=False, indent=2)
    attachments_list = base_info.get("attachment", []) or []
    attachments = "\n".join(str(a) for a in attachments_list) if attachments_list else "(none)"

    proj = Path(output_file_path)
    if not proj.is_absolute():
        proj = project_root / proj

    filled = fill_template(template, {
        "user_prompt": user_prompt,
        "checklist": checklist,
        "hidden_checklist": json.dumps(hidden_items, ensure_ascii=False, indent=2),
        "source_code": collect_source_code(proj),
        "attachments": attachments,
        "file_manifest": build_file_manifest(proj),
        "build_status": build_gate_note(build_artifact_status(proj)),
    })

    # NOTE: eval_raw.txt is written into the project directory because the
    # preview server / webapp read it from there; tools.HARNESS_FILES keeps it
    # out of the manifest and it is not a source extension, so the judge never
    # sees its own previous output.
    verdict = invoke_json_with_retry(
        invoke, filled, raw_path=proj / "eval_raw.txt",
        max_retries=max_retries, thinking=thinking,
        validate=lambda v: validate_verdict(v, checklist_items, hidden_items),
    )
    return normalize_verdict(verdict, checklist_items, hidden_items)


__all__ = [
    "AUX_KEYS", "TOTAL_KEY", "MODEL_TOTAL_KEY", "VALIDATION_ERROR_KEY",
    "HIDDEN_KEY", "HIDDEN_SCORE_KEY",
    "fill_template", "coerce_checklist", "validate_verdict", "normalize_verdict",
    "run_static_eval",
]
