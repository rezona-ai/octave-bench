"""Filesystem utilities for the eval pipeline.

`collect_source_code` walks an agent-generated project directory and packs the
eligible source files into one string ready to drop into the `{source_code}`
placeholder of the eval prompts.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

# Allowed file extensions. The eval prompts specifically state that only files
# carrying actual game logic, UI, state, config, and styling are evaluated.
# `.html` is required: the Runnability Gate inspects index.html's mount root,
# so leaving it out makes the judge hallucinate a missing entry point.
# `.glsl` / `.vert` / `.frag` carry standalone shader sources in 3D projects.
DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".tsx", ".ts", ".jsx", ".js", ".css", ".json",
    ".html",
    ".glsl", ".vert", ".frag",
)

# Context-budget guards for the packed dump, in characters. Code tokenizes at
# roughly 3–3.5 chars/token, so 50 K chars/file ≈ 15 K tokens and 400 K chars
# total ≈ 115–130 K tokens. The remainder of a 200 K-token window has to hold
# the eval rubric (~15–20 K tokens), the file manifest, the checklist, the
# model's thinking and up to 32 K output tokens — hence the headroom.
MAX_FILE_CHARS = 50_000
MAX_TOTAL_CHARS = 400_000

# When the total budget still overflows after per-file elision, whole files are
# dropped lowest-priority-first (then largest-first): styling goes before data
# config, config before markup; code / shaders are dropped only as a last
# resort. Anything not listed here ranks 3 (highest keep-priority).
_DROP_PRIORITY: dict[str, int] = {".css": 0, ".json": 1, ".html": 2}

# Files the Runnability Gate and the tech-constraint checks depend on. They are
# tiny, so dropping them saves nothing and costs the judge its ground truth for
# "is X in package.json" / "does index.html have a mount root" / "does the
# path alias resolve" — a dropped index.html reads as a broken entry point.
# Matched by file name at any depth.
_NEVER_DROP: frozenset[str] = frozenset({
    "package.json", "index.html",
    "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", "jsconfig.json",
    "vite.config.ts", "vite.config.js", "vite.config.mts", "vite.config.mjs",
})

# Dropping a file below this size buys back almost nothing but still blinds the
# judge to it, so the budget pass only considers files at least this large.
_MIN_DROP_CHARS = 2_000


def _elide_middle(content: str, max_chars: int) -> str:
    """Keep the head and tail of an oversized file, marking the removed middle.

    The marker text is echoed in the eval prompts (§1.3) so the judge knows it
    is harness-inserted and must treat the elided region as unknown code.
    """
    if len(content) <= max_chars:
        return content
    head = (max_chars * 2) // 3
    tail = max_chars - head
    omitted = len(content) - head - tail
    return (
        content[:head]
        + f"\n\n[...ELIDED {omitted} chars from the middle of this file to fit "
        "the context budget; treat the elided region as unknown code — do not "
        "invent its content...]\n\n"
        + content[-tail:]
    )

# Directory names skipped entirely (matched as any path component). Covers the
# usual suspects: deps, build output, VCS, framework caches, and known
# agent-pipeline trace/log directories.
DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    "node_modules",
    "dist", "build", "out",
    ".git", ".next", ".nuxt", ".svelte-kit", ".turbo", ".vercel", ".cache",
    "coverage", ".nyc_output",
    "_logs",
})

# Filenames skipped even when the extension matches — lockfiles, autogen
# type declarations, and trace metadata produced by the agent's harness.
DEFAULT_EXCLUDE_FILES: frozenset[str] = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "vite-env.d.ts", "next-env.d.ts",
    "langfuse_trace.json", "run_meta.json",
})

# Files the benchmark harness itself writes into the case / project directory
# (the judge's own raw output, agent logs, the rendered prompt, koubou event
# streams). They are not part of the agent's deliverable and must not appear in
# the "every file in the project" manifest, or the judge starts reasoning about
# them. `prompt_turn_N.txt` / `agent_turn_N.log` are matched by regex below.
HARNESS_FILES: frozenset[str] = frozenset({
    "eval_raw.txt", "agent.log", "prompt.txt", "events.jsonl",
})
_HARNESS_FILE_RE = re.compile(r"^(?:prompt_turn_\d+\.txt|agent_turn_\d+\.log)$")

# Manifest size guard: directories holding more than this many files are
# collapsed into one summary line, and the manifest is hard-capped at
# MAX_MANIFEST_LINES so a `public/` full of sprite frames cannot eat the budget.
_COLLAPSE_DIR_FILES = 20
MAX_MANIFEST_LINES = 400


def collect_source_code(
    project_path: str | Path,
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS,
    exclude_files: Iterable[str] = DEFAULT_EXCLUDE_FILES,
    *,
    max_file_chars: int = MAX_FILE_CHARS,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> str:
    """Concatenate eligible source files under `project_path` into one string.

    Output format matches §1.3 of the eval prompt:

        path/to/file.tsx: <file content...>
        ...content continues across newlines...

        path/to/next.ts: <file content...>

    Files are emitted in sorted relative-path order so the output is
    deterministic (good for caching and diffing across runs).

    Args:
        project_path: Root of the agent-generated project on disk.
        extensions: File extensions to include (case-insensitive, leading dot).
        exclude_dirs: Directory names to skip; matched against any component
            of a file's relative path (so e.g. "node_modules" anywhere in the
            tree is skipped).
        exclude_files: Filenames to skip even when the extension matches.
        max_file_chars: Per-file character cap; oversized files keep their head
            and tail with a harness elision marker in between.
        max_total_chars: Total dump cap; on overflow whole files are dropped
            lowest-priority-first (see _DROP_PRIORITY) and replaced with an
            omission stub so the judge still knows the file exists.

    Returns:
        A single string ready to drop into `{source_code}`. Empty string if
        no eligible files were found.

    Raises:
        FileNotFoundError if `project_path` does not exist.
        NotADirectoryError if `project_path` is not a directory.
    """
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"project_path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"project_path is not a directory: {root}")

    ext_set = {e.lower() for e in extensions}
    excl_dirs = frozenset(exclude_dirs)
    excl_files = frozenset(exclude_files)

    # (rel_str, suffix, content) — kept as a list so the total-budget pass can
    # rewrite entries in place while emission order stays sorted-by-path.
    entries: list[tuple[str, str, str]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        # Skip if any ancestor dir is in the exclude list.
        if any(part in excl_dirs for part in rel.parts[:-1]):
            continue

        if path.name in excl_files:
            continue

        if path.suffix.lower() not in ext_set:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # Binary file misnamed with a text extension, or unreadable — skip
            # silently rather than poisoning the dump with garbage / errors.
            continue

        rel_str = str(rel).replace("\\", "/")
        # Trim trailing whitespace on the content so we don't double-pad
        # between files; the "\n\n" join below already provides the gap.
        entries.append(
            (rel_str, path.suffix.lower(), _elide_middle(content.rstrip(), max_file_chars))
        )

    # Enforce the total budget by dropping whole files lowest-priority-first
    # (then largest-first). The stub keeps the file visible in the dump so the
    # judge knows it exists but was not shown, instead of a silent hole.
    # Gate-critical files (_NEVER_DROP) and files too small to matter
    # (_MIN_DROP_CHARS) are never candidates.
    total = sum(len(content) for _, _, content in entries)
    if total > max_total_chars:
        candidates = [
            i for i, (rel_str, _, content) in enumerate(entries)
            if Path(rel_str).name not in _NEVER_DROP and len(content) >= _MIN_DROP_CHARS
        ]
        drop_order = sorted(
            candidates,
            key=lambda i: (_DROP_PRIORITY.get(entries[i][1], 3), -len(entries[i][2])),
        )
        for i in drop_order:
            if total <= max_total_chars:
                break
            rel_str, suffix, content = entries[i]
            stub = (
                f"[FILE OMITTED: {len(content)} chars dropped to fit the context "
                "budget; the file exists — see the project file manifest (§1.5)]"
            )
            total += len(stub) - len(content)
            entries[i] = (rel_str, suffix, stub)

    return "\n\n".join(f"{rel_str}: {content}" for rel_str, _, content in entries)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _is_harness_file(name: str, exclude_files: frozenset[str]) -> bool:
    return name in exclude_files or bool(_HARNESS_FILE_RE.match(name))


def build_file_manifest(
    project_path: str | Path,
    exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS,
    exclude_files: Iterable[str] = DEFAULT_EXCLUDE_FILES | HARNESS_FILES,
    *,
    collapse_dir_files: int = _COLLAPSE_DIR_FILES,
    max_lines: int = MAX_MANIFEST_LINES,
) -> str:
    """List the project's files (relative path + size), including binary assets.

    Injected into the eval prompts' §1.5 so the judge answers file-existence
    questions (is the `.glb` referenced by `useGLTF` actually shipped under
    `public/`?) from ground truth instead of guessing — the §1.3 source dump
    contains text files only.

    Skipped: dependency / build directories (dist/ presence is reported
    separately via `build_gate_note`), lockfiles, and files the benchmark
    harness itself writes into the case directory (eval_raw.txt, agent.log,
    prompt*.txt, events.jsonl, run_meta.json …) — those are not the agent's
    deliverable and would only confuse the judge.

    Size guard: a directory with more than `collapse_dir_files` files is
    collapsed into one summary line (`dir/ — N files, total size, ext×count …`)
    so asset dumps stay legible; the whole manifest is capped at `max_lines`
    with a trailing "(… N more files not listed)" marker. The §1.5 prompt text
    documents both formats.
    """
    root = Path(project_path).expanduser().resolve()
    excl_dirs = frozenset(exclude_dirs)
    excl_files = frozenset(exclude_files)

    files: list[tuple[str, int]] = []  # (rel_str, size)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excl_dirs for part in rel.parts[:-1]):
            continue
        if _is_harness_file(path.name, excl_files):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append((str(rel).replace("\\", "/"), size))

    if not files:
        return "(no files found)"

    # Collapse crowded directories (by immediate parent) into summary lines.
    by_dir: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for rel_str, size in files:
        by_dir[str(Path(rel_str).parent)].append((rel_str, size))

    lines: list[str] = []
    for rel_str, size in files:
        parent = str(Path(rel_str).parent)
        group = by_dir.get(parent)
        if group is None:
            continue  # already emitted as a collapsed summary
        if len(group) > collapse_dir_files:
            exts = Counter((Path(r).suffix.lower() or "(no ext)") for r, _ in group)
            ext_summary = ", ".join(f"{e}×{n}" for e, n in exts.most_common(6))
            total = sum(sz for _, sz in group)
            label = "./" if parent == "." else parent + "/"
            lines.append(f"{label} — {len(group)} files, {_fmt_size(total)} ({ext_summary})")
            del by_dir[parent]
        else:
            lines.append(f"{rel_str} ({_fmt_size(size)})")

    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + [f"(… {hidden} more entries not listed to fit the context budget)"]
    return "\n".join(lines)


def build_artifact_status(project_path: str | Path) -> dict:
    """Detect whether a successful production build artifact exists for a project.

    The generation pipeline runs `vite build`, emitting ``dist/index.html`` plus
    bundled ``dist/assets/*.js``. Their presence is ground truth that the full
    source compiled — no syntax / parse error and no unresolved import survived
    the bundler (either of those makes the build refuse to emit). The eval
    prompts consume this (via :func:`build_gate_note`) to forbid phantom
    compile-time "代码无法运行" Runnability-Gate failures.

    Returns a dict ``{"built": bool, "bundles": int}``. ``built`` is True only
    when both an ``index.html`` entry and at least one JS chunk are present.
    """
    root = Path(project_path).expanduser().resolve()
    dist = root / "dist"
    assets = dist / "assets"
    bundles = sorted(assets.glob("*.js")) if assets.is_dir() else []
    built = (dist / "index.html").is_file() and len(bundles) > 0
    return {"built": built, "bundles": len(bundles)}


def build_gate_note(status: dict) -> str:
    """Render the §2.3 build-status note injected into the eval prompts.

    When a build artifact exists, the note tells the judge that a real
    compiler/bundler already proved the source parses and its imports resolve,
    so it MUST NOT fail the Runnability Gate for compile-time reasons (syntax /
    brace / parse defects, unresolved imports). Runtime gate reasons (missing
    provider wiring, first-render crash, loop never started, …) are explicitly
    preserved. When no artifact exists, the gate is applied as written.
    """
    if not status.get("built"):
        return (
            "No verified production build artifact was found for this project "
            "(`dist/` is absent or empty). Apply the Runnability Gate (§2.3) "
            "as written, using your best static judgment."
        )
    return (
        "**A production build of this project SUCCEEDED.** A real bundler "
        f"(`vite build`) compiled the entire source into `dist/index.html` + "
        f"bundled `dist/assets/*.js` ({status['bundles']} JS chunk(s)). This is "
        "ground truth from an actual compiler — not a guess from reading text.\n\n"
        "Because the build succeeded, the following Runnability-Gate failure "
        "categories are **PROVABLY FALSE and MUST NOT be cited** — a successful "
        "build rules them out by construction:\n"
        "- **Unresolved cross-file imports** — the bundler resolved the whole "
        "module graph; an unresolved import / missing dependency would have "
        "failed the build.\n"
        "- **Stage-blocking syntax / typing defect** (mismatched or single vs. "
        "double braces, unclosed JSX tag, module-scope parse error, etc.) — any "
        "such defect makes the build refuse to compile; since it compiled, none "
        "exist.\n"
        "- The **compile / parse aspect of 'Entry / mount broken'** — the entry "
        "module parsed and bundled successfully.\n\n"
        "In particular, **do NOT report a JSX/TS syntax error**. Valid JSX object "
        "props use double braces (`prop={{ ... }}`); if a snippet appears to use a "
        "single brace (`prop={ ... }`) or otherwise looks malformed, treat it as a "
        "rendering/display artifact, NOT a real defect — the successful build "
        "proves it parsed. Re-read carefully before citing ANY compile-time "
        "blocker, and never zero the whole checklist on a suspected syntax error.\n\n"
        "You MAY still fail the gate, but ONLY for **runtime** reasons a successful "
        "build does not rule out: missing provider / store wiring, rules-of-hooks "
        "violations, a guaranteed first-render crash, the game loop / per-frame "
        "tick never being started, an engine instantiated but never attached, or an "
        "entry that mounts but renders nothing. Any such gate failure must cite "
        "concrete runtime control-flow evidence — never a syntax / parse / import "
        "claim."
    )
