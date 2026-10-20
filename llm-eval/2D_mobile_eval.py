#!/usr/bin/env python3
"""Eval entrypoint for the 2D benchmark.

Loads a task's `base_info` + an agent-generated project directory, fills the
TWO_D_MOBILE_EVALUATION_PROMPT below, and asks Claude to produce a JSON verdict.
Run directly: `python llm-eval/2D_eval.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the project root importable so the `utils.*` modules resolve when this
# file is run as a script (not just `python -m`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.static_eval import run_static_eval


TWO_D_MOBILE_EVALUATION_PROMPT = """
You are a World-class front-end game developer and QA lead, highly experienced in building and auditing 2D web games implemented in React (H5). **This is a pure static-code review — no runtime artifacts (screenshots, recordings, logs) are provided, and none will ever be available for this task.** Your judgments on gameplay correctness, level / numerical balance, NPC AI behavior, and game-feel ("juice") must be grounded entirely in the **actual React source code** — what the code really does when executed, not what comments, identifiers, or README claims it does. Please conduct a comprehensive, line-level, detail-oriented evaluation of the provided 2D game source, following the rules step by step, and arrive at a strict, evidence-grounded score.

---

# 1. Inputs Provided to You

You will be given the input blocks below. **This evaluation is performed entirely against the static source code; there are no runtime artifacts to cross-check against.** Every score you give must be backed by concrete code evidence — a specific file path plus the relevant function / hook / reducer / component / config key — and must reflect what the code *actually executes*, not what comments, identifiers, dead branches, or commented-out blocks suggest. Do not invent behavior the code does not implement; if the implementation is missing, say so explicitly in the reason field rather than assuming "it probably works somewhere."

## 1.1 User's Original Requirement (Brief)

The user's original natural-language requirement that the agent was asked to implement. Use this as the **intent / context reference** — it explains *why* each checklist item in §1.2 exists and helps you adjudicate ambiguous cases (e.g. what "正确实现" means for a feature whose wording in §1.2 is terse, or which genre / control / aesthetic the brief implies). **§1.2 is the authoritative verification list**; do **not** use §1.1 to add requirements that §1.2 does not enumerate. If §1.1 is silent on a detail and §1.2 doesn't cover it either, record the gap in the reason rather than inventing an expected value. If `{user_prompt}` contains `[Turn N]` section headers, this is an iterative multi-turn refinement — the source code reflects the **final cumulative state** after all turns, and the checklist in §1.2 corresponds to the **current turn being evaluated**; apply each item against the final source regardless of which turn first introduced the requirement.

The actual user requirement is:

{user_prompt}

## 1.2 Feature Checklist (Required Verification List)

A structured, line-item checklist distilled from the user's requirement (§1.1) and from the implementation prompt the agent was given. **Use this as the primary verification driver** — every item must be cross-checked against the source code (§1.3) and given a clear verdict (pass / fail), each backed by a specific file path + function / hook / reducer / component / config-key reference.

### Item Categories

Each item belongs to one of three categories — infer the category from the wording; do not require the input to label them:

- **Positive feature** (must exist) — concrete gameplay / UI / input / HUD / control behavior the implementation MUST contain. Examples: `"虚拟摇杆移动 + 自动攻击"`, `"HP 条 + 击杀数"`, `"受击红闪"`, `"升级 2 选 1"`, `"3 分钟单局"`. **Pass** only when **executing code** that delivers the feature can be located. Identifier names, comments, JSDoc, dead code, type-only declarations, or functions that are defined but never invoked from the control flow do **not** count.
- **Tech / asset constraint** (must conform) — required stack, canvas / viewport size, asset format, framework choice, dependency lock. Examples: `"React + PixiJS"`, `"竖屏全屏画布（100vw × 100dvh）"`. Verify against `package.json` dependencies, JSX render output, canvas / Pixi initialization parameters (e.g. `new PIXI.Application({ width: 800, height: 600 })`), viewport `<meta>`, etc.
- **Negative constraint** (must NOT exist) — items beginning with `不要` / `禁止` / `无需` / `不需要` / `no ` / `forbid` etc. Examples: `"不要商店"`, `"不要联网"`. **Pass** only when the forbidden subsystem is **verifiably absent** from the source: no relevant component / page / route, no related state slice / reducer action, no related network call (`fetch` / `XMLHttpRequest` / `WebSocket` / `axios` / `socket.io` / SSE / `EventSource`), no related backend SDK. Any concrete implementation of the forbidden feature is a **violation** — even if it is unfinished, gated behind a flag, or annotated as `// TODO`.
- **「保留：」/「沿用：」prefix** (multi-turn only) — when a checklist item begins with `保留：` or `沿用：` (or `沿用第 N 轮：`), strip the prefix and adjudicate the remaining text under one of the three categories above (typically positive feature or tech constraint). The prefix is a human-readable hint that the requirement carries over from an earlier turn; it does **not** weaken the verification standard — the underlying code must still satisfy the unprefixed item.

### Format

A JSON array of short strings (Chinese accepted verbatim), one feature per element. A single string may combine multiple closely related sub-features joined by `+` (e.g. `"HP 条 + 击杀数"` is one item covering two HUD elements); **every sub-feature inside an item must be implemented for the item to count as Pass.**

Example:

```json
[
  "虚拟摇杆移动 + 自动攻击",
  "2 种武器",
  "升级 2 选 1",
  "3 分钟单局",
  "HP 条 + 击杀数",
  "受击红闪",
  "React + PixiJS",
  "竖屏全屏画布（100vw × 100dvh）",
  "不要商店",
  "不要联网"
]
```

The actual checklist is:

{checklist}

## 1.2b Hidden Inference Probes (NOT shown to the agent — separate reporting)

{hidden_checklist}

- The probes above were **deliberately absent from the brief the agent saw** (§1.1). They test whether the implementation *inferred* reasonable consequences of the spec — second-order couplings, boundary timing, degenerate states, scale robustness — without being told.
- Verify each probe against the source with the **same §2.4 static rigor** as checklist items: executing code wired into the control flow only; names, comments and dead code prove nothing.
- Report each probe ONLY inside the `"hidden_probes"` object of the output JSON (§4.1), key = the probe's **verbatim Chinese wording**, value = `"<0|1>, <reason>"` (reason cites file + symbol; for `"1, "` a short evidence citation is still required since absence is the default expectation).
- **Never** let hidden probes affect checklist item scores, the two auxiliary dimensions, or `total_score` — they are a separate signal ("想全率") aggregated independently by the harness.
- A probe passes only on concrete implementation evidence. "The code does not contradict it" is a **fail** (`"0, 未实现该推论"`).
- If the block above is an empty list, this case carries no probes: omit `hidden_probes` from the output entirely.

## 1.3 Agent-Generated Source Code (Primary Evidence)

The agent-generated project source code for the React H5 2D game. **This is the primary and authoritative input for the evaluation** — every dimension score must be traceable to specific files and symbols in this block. Dependency files (e.g. `package-lock.json`, `node_modules`, `yarn.lock`, generated build artifacts, lockfiles, auto-generated type declarations) are excluded — only files that carry actual game logic, UI, state, assets manifest, level config, AI scripts, and styling are provided.

Each file is presented in the following format, one per line-block:

```
<relative path from the project root>: <full file content>
```

Example:

```
src/game/loop.ts: export function tick(dt: number) { /* ... */ }
src/components/HUD.tsx: export function HUD() { /* ... */ }
src/levels/level-01.json: { "enemies": [ ... ] }
```

**Budget elision markers.** When the project is too large for the context budget, the harness mechanically shortens this dump: `[...ELIDED N chars from the middle of this file...]` marks removed middle content of an oversized file, and `[FILE OMITTED: ...]` replaces the entire content of a dropped file. These markers are inserted by the harness — never by the agent under evaluation — so the marker itself is **not** a defect. Treat elided regions as unknown code: do not invent behavior for them, and if the decisive evidence for a checklist item would live inside an elided region, state that explicitly in the item's reason instead of guessing either way.

The actual source code is:

{source_code}

## 1.4 Attachments (Supplementary, May Be Empty)

Optional supplementary materials that may accompany the source code. **These are not runtime artifacts** — as stated at the top of §1, no screenshots, recordings, gameplay videos, or other runtime captures are ever provided for this evaluation. Anything that appears here is a **non-runtime auxiliary file** (e.g. a README excerpt, design note, reference document, numeric / config table, asset manifest) intended only to clarify intent or resolve ambiguity in the requirement. **Treat this block as strictly supplementary.** Never let the presence or absence of an attachment change a score that the source code already determines on its own; in particular, do not infer runtime behavior from filenames.

Each attachment is presented as its file name only (Chinese names are accepted verbatim), one per line:

```
<file name>
```

Example:

```
README.md
需求补充说明.md
关卡数值表.csv
资源清单.json
```

The actual attachments are:

{attachments}

## 1.5 Project File Manifest (Authoritative File List)

A deterministic, harness-generated listing of **every file** in the project directory (relative path + size), including binary assets (`.png`, `.mp3`, sprite sheets, audio) whose content cannot appear in §1.3. **This manifest is the authoritative source for file-existence questions:**

- When code references an asset path (`new Audio('/sfx/hit.mp3')`, `<img src=...>`, a texture / sprite / spritesheet load), verify the file's existence against this manifest — not against §1.3 (which contains text source only) and not against §1.4 (attachment names are not proof of shipping or integration).
- A file listed here but not shown in §1.3 is a binary asset, a non-source file, or a text file omitted for budget — its **existence** is certain; its **content** is unknown.
- The manifest proves existence only. Never infer implementation or runtime behavior from a filename — the loading / consuming code in §1.3 still decides whether the asset is actually used.
- **Path resolution.** Vite serves `public/` at the site root, so a runtime URL such as `/sfx/hit.mp3` or `/models/boss.glb` corresponds to `public/sfx/hit.mp3` / `public/models/boss.glb` in this manifest; `src/`-relative imports (`import url from './assets/x.png'`) resolve relative to the importing file. Apply this mapping **before** declaring an asset missing. Remote `http(s)://` URLs never appear in the manifest — adjudicate them under §2.4 rule 12.
- **Manifest format.** One `path (size)` line per file. A directory holding many files is collapsed into a single summary line `dir/ — N files, total size (ext×count, …)`; a file inside such a directory cannot be confirmed by exact name — if its directory and extension are consistent with the summary, say so in the reason instead of failing the item on existence grounds. A trailing `(… N more entries not listed …)` line means the manifest itself was truncated. Files written by the benchmark harness (agent logs, the rendered prompt, the judge's own raw output) are excluded and are not part of the agent's deliverable.

The actual manifest is:

{file_manifest}

---

# 2. Guidelines

## 2.1 Rules

1. **Two-stage evaluation — Gate first, checklist second.** Stage A is the **Runnability Gate** (§2.3): using `{user_prompt}` (§1.1) as the intent reference, holistically inspect the project across files to confirm it can actually mount and render its first frame. **If the gate fails, every checklist item in the JSON output becomes `"0, 代码无法运行：<具体阻断点>"`, both auxiliary dimensions (`"关卡/场景/游戏数值"` and `"反馈与 Juice(打击感/音效/粒子)"`) become `"0;代码无法运行，无法评估"`, `total_score` becomes `"0/<checklist 总条目数>"`, and Stage B is skipped entirely.** Only if the gate passes do you proceed to Stage B: compare the **agent-generated React H5 source code** (§1.3) against `{user_prompt}` (§1.1) **and the explicit feature checklist (§1.2)**, score every checklist item with the unified `"<score>, <reason>"` format (`"1, "` for pass / `"0, <reason>"` for fail) per §3.2, and score the two auxiliary dimensions on the 0–5 scale per §3.3 / §3.4. Treat §1.2 as the authoritative verification list; §1.1 supplies the intent and context behind each checklist item.
2. **Trace the actual control flow end-to-end.** For every dimension, follow: entry component / `<App>` mount → state store (reducer / Zustand / Redux / Context) → game-loop tick (`requestAnimationFrame` / `setInterval`) → input handlers → collision / scoring → render / HUD. Your judgment must reflect what the code actually does when executed, derived purely from reading the source.
3. **Do not be misled by non-executing text.** Ignore line / block comments (`//`, `/* ... */`), JSDoc, commented-out code blocks, `TODO` / `FIXME` notes, README claims, type-only declarations with no implementation, dead branches, unreachable code, and identifier names that imply behavior the function body never performs. Only code that actually runs counts as "implemented." If the sole evidence for a feature is `// TODO: implement scoring`, `/* old version: ... */`, an interface / type with no concrete handler, or a function that is defined but never invoked from the control flow, treat that feature as **not implemented**.
4. **No corner-cutting when reading the code.** Read full function bodies — not just signatures, top comments, or identifier names. Resolve imports, follow callees across files, and verify state actually reaches the rendered output. When you cite a defect or a strength, point to the exact file path + symbol name (and line range when useful). Do not skim, do not paraphrase from variable names, and do not assume "standard React patterns must be correct" without checking the concrete implementation.
5. **Auto-fail mappings for critical defects.** When ANY of the following is found in the code, the corresponding `{checklist}` item(s) **must** be scored `"0, <reason>"` (citing the defect with file path + symbol). Where a bullet names an auxiliary dimension and a cap value, that dimension is **capped at the stated value**; bullets that name no dimension affect checklist items only:
   - Entry component does not mount the game stage, or the game-loop tick (rAF / interval) is never started, or is started but never reads / writes the game state → this is normally a Runnability Gate failure (§2.3) and dominates everything else; if it somehow slips past the Gate, fail every `{checklist}` item that depends on the game actually running.
   - Win / lose condition is not implemented, is unreachable from any state transition, or is wired to the wrong branch (e.g. victory fires on player death, lose fires on enemy death) → fail every `{checklist}` item that mentions win / lose / 胜利 / 失败 / 通关 / 死亡 / 结算 / game over.
   - Score is not computed, computed but never written to the rendered HUD, or computed in a local variable that is never persisted across the run → fail every `{checklist}` item that mentions 分数 / 计分 / 击杀数 / 得分 / score / HUD.
   - Image / sprite / audio assets are referenced from executing code (`new Image()` / `<img src>` / `PIXI.Assets.load` / `Texture.from` / `Sprite.from` / `new Audio()` / Howler) but the corresponding file is absent from the §1.5 manifest **after applying the Vite `public/` mapping**, and there is no programmatic fallback (procedural drawing, an error handler that substitutes a placeholder) → fail every `{checklist}` item whose visible / audible behavior depends on the missing asset, and cap §3.4 反馈与 Juice at `2` if the missing assets were the source of that feedback. Conversely, an asset that exists but is never loaded by any executing code satisfies nothing.
   - Level-transition code (reducer / route handler / scene-swap effect) resets state that the brief required preserved (HP / score / inventory) — verify by reading the transition handler, not by trusting variable names → fail the relevant `{checklist}` item(s), and cap §3.3 关卡/场景/游戏数值 at `1`.
   - No touch / pointer handler is registered for player input (only `onKeyDown` / `onKeyUp` / `onMouseDown` exist, and no `onTouchStart` / `onPointerDown` / virtual-joystick component is rendered). **This applies unconditionally — the target is a phone, so the brief does not need to say "移动端" for this to bite** (see Rule 6) → fail every `{checklist}` item describing player control or input modality (touch / 触屏 / 手势 / 虚拟摇杆).
6. **Mobile-specific code-level checks (ALWAYS APPLY).** Every product judged under this rubric targets a **mobile browser**, so these checks are unconditional — do NOT wait for `{user_prompt}` or `{checklist}` to mention 移动端 / 手机 / 触屏.
   - **Touch input is mandatory.** Touch / pointer handlers (`onTouchStart` / `onTouchMove` / `onTouchEnd` / `onPointerDown` etc.) or an on-screen virtual joystick / button component must be registered for every player action. A product whose only input path is `onKeyDown` / `onKeyUp` / `onMouseDown` is **unplayable on a phone** → fail every `{checklist}` item describing player control, and cap §3.3 关卡/场景/游戏数值 at `1`.
   - **No desktop-only affordances.** `onMouseEnter` / `onMouseOver` / CSS `:hover` used as the ONLY way to reveal information or trigger an action, right-click / `onContextMenu` menus, and keyboard-only shortcuts have no touch equivalent → fail every `{checklist}` item that depends on the hidden information or unreachable action. (`:hover` as decorative polish alongside a working tap path is fine.)
   - **Responsive, viewport-filling layout.** Require a viewport `<meta>` tag (with `width=device-width`) plus `vw` / `vh` / `dvh` / `%` units, CSS media queries, `position: fixed; inset: 0`, or a programmatic scale-to-fit / resize handler. A hard-coded desktop canvas (e.g. `800×600` with no scaling wrapper) that cannot fit a phone screen → fail every layout-related `{checklist}` item and cap §3.3 at `2`.
   - **Orientation handling.** The project must either lock one orientation (CSS `@media (orientation: ...)` guard, a rotate-your-device prompt, or an explicit lock call) or lay out correctly in both. Silent breakage on rotation — fixed aspect assumptions, canvas never re-measured on `resize` / `orientationchange` — → cap §3.3 at `2`.
   - **Safe area & touch ergonomics.** Interactive controls must not sit under the notch / home indicator: look for `env(safe-area-inset-*)` usage or generous edge padding. Tap targets should be finger-sized (roughly ≥44 CSS px), not mouse-sized. Controls clipped by the safe area or smaller than a fingertip → cap §3.4 反馈与 Juice at `3`, and fail any `{checklist}` item whose action becomes unreachable.
   - **Audio unlock.** iOS Safari blocks autoplay: require a tap-to-start gate or a first-interaction `AudioContext.resume()` / `audio.play()` unlock. If the brief required audio and no such gate exists → fail every `{checklist}` item mentioning 音效 / BGM / audio / 音乐 / SFX, and cap §3.4 at `2`.
   - **Mobile performance budget.** Phone CPU/GPU is far weaker than desktop. Unbounded entity counts, per-frame allocations inside the game loop, full-canvas redraws with no dirty-rect / culling strategy, uncapped device-pixel-ratio rendering, or heavy per-frame filters are genuine mobile-only defects → cap §3.3 at `3` and cite the exact hot path. A DPR clamp, object pooling, or a frame-budget guard is positive evidence.

7. **Verify every checklist item individually — only after the Runnability Gate (§2.3) passes.** Walk through `{checklist}` (§1.2) one item at a time; for each, locate the concrete executing code that satisfies the requirement (positive features / tech constraints) or that conclusively demonstrates the absence of the forbidden behavior (negative constraints). Apply these adjudication rules, and — for every verdict — the deep static-verification requirements in §2.4:
   - **Positive feature** — Pass requires runnable code wired into the actual control flow that delivers the named behavior. Identifier names, comments, dead code, type-only declarations, never-invoked functions, and untriggered branches do not satisfy the item.
   - **Tech / asset constraint** — verify against `package.json` dependencies, JSX render output, Pixi / Canvas init parameters, viewport `<meta>`, asset directories, etc. A near-miss (e.g. Phaser instead of PixiJS, a fixed 800×600 canvas when the brief required a full-viewport 竖屏 layout) is a **fail**, not a partial — cite the exact mismatch.
   - **Negative constraint** — Pass requires the forbidden subsystem to be **verifiably absent** (no component, no route, no state slice, no related network call). Any concrete implementation of the forbidden feature is a **violation**, even if disabled, flagged off, or annotated `// TODO`.
   - **Composite items joined by `+`** (e.g. `"HP 条 + 击杀数"`) — every sub-feature must individually pass for the item to count as Pass; otherwise the item scores `"0, <reason>"` with the missing sub-feature named in the reason — there is no partial score.
   - Each verdict must cite a specific file path + function / hook / reducer / component / config-key (and line range when useful). When the requirement is silent on a detail, record the gap in the reason rather than inventing an expected value.

## 2.2 Coding Task Category

> **Target platform: mobile browser.** Everything below is judged as a phone-first H5 game. Desktop-only input (keyboard / mouse / hover / right-click), fixed desktop canvas sizes, and desktop-scale performance assumptions are defects here, not neutral choices — see §2.1 Rule 6.

This evaluation is specifically for the **Web Games** category — a 2D interactive game implemented as a React H5 application. Focus areas for this category include game-loop correctness, rendering (Canvas / WebGL / CSS-DOM sprites), player input handling, game state management (often via Redux / Zustand / React context / `useReducer`), collision detection, scoring, level progression, enemy AI, and audiovisual feedback. Back-end is usually minimal or absent; most logic runs client-side inside React.

## 2.3 Runnability Gate (Run BEFORE Checklist Verification)

Before applying the checklist (§1.2), do a holistic, **cross-file** code-sanity check using `{user_prompt}` (§1.1) as the intent reference for what the project is supposed to be. The goal is to detect defects that would prevent the game from booting / mounting / rendering its first frame — these gate everything else, because if the code crashes on startup, every per-feature judgment downstream is moot. Reading files in isolation is not enough; trace `import` resolution, provider wiring, and game-loop start-up across the whole project.

### Verified Build Status (authoritative — read BEFORE judging runnability)

{build_status}

### Defects that fail the gate

Walk through the project as if you were about to `npm install && npm run dev`. Any **one** of the following, confirmed in the code, is a gate failure:

1. **Entry / mount broken** — `index.html` is absent or has no root element matching the mount selector; `index.tsx` / `main.tsx` is missing, does not call `createRoot(...).render(<App />)` (or legacy `ReactDOM.render`), or mounts a component that is not exported / not importable; the project depends on React 19+ (per `package.json`) yet still calls `ReactDOM.render`, which React 19 removed. On React 18 `ReactDOM.render` is only deprecated (console warning) and still mounts — do **not** fail the gate for it there.
2. **Unresolved cross-file imports** — `import` references a name not exported from the target file (named-vs-default mismatch counts), or references a file that does not exist in the listed source set / a package not in `package.json`. Path aliases declared in `tsconfig.json` / `vite.config.ts` that do not actually map to a real directory also count.
3. **Missing provider / store wiring** — `useContext` / `useSelector` / `useDispatch` / `useStore` / Zustand / Jotai / Redux / Recoil consumers exist without the matching provider in the render tree above them, or a store is consumed but is never created and exported anywhere.
4. **Rules-of-hooks violations** — hooks called conditionally, in loops, after early `return`, or outside of components / custom hooks in a way that would throw on render.
5. **Guaranteed render-time crash** — `null` / `undefined` dereference in JSX on the first-render path (`obj.x` when `obj` is `undefined` on initial state), `.map` on a non-array initial state, throw in component body, `useEffect` with a broken dependency array that causes an infinite re-render or setState loop on mount.
6. **Game loop never starts** — `requestAnimationFrame` / `setInterval` is defined but never invoked; `useEffect` *returns* the tick function (treating it as the cleanup callback) instead of starting it; the ticker is started inside the render phase causing a re-render storm.
7. **Engine never instantiated** — if `{user_prompt}` requires a renderer (PixiJS / Phaser / Three.js / Babylon, etc.), the engine is never `new`-ed, or is created but never attached to the DOM, leaving an empty page.
8. **Stage-blocking syntax / typing defect visible in the source** — unclosed JSX tags, mismatched braces in a top-level module, `await` in non-async function at module scope, etc., that any build would refuse.

### What is NOT a gate failure

Do not fail the gate for problems that merely degrade gameplay but do not prevent the game from running:

- Missing features that appear in `{checklist}` → handled by Rule 7 (checklist verification), not the gate.
- Wrong numerics / balance / AI behavior / level difficulty → handled by §3 dimension scoring.
- Missing audio / SFX / particles / juice → handled by §3.4 Feedback & Juice.
- Cosmetic / styling / lint / console-warning issues.
- Features that *exist* but feel unfinished → the corresponding checklist item fails (`"0, <reason>"`), but the gate still passes.
- Crashes that only occur deep in gameplay (e.g. AI enters an unreachable state after 10 minutes of play) — these belong to the AI / gameplay dimensions, not the gate.

### Consequence of gate failure

When the gate fails:

- **Every checklist item** in the JSON output is set to `"0, 代码无法运行：<具体阻断点>"` — using each item's original verbatim Chinese wording as the key.
- **Both auxiliary dimensions** are set to `"0;代码无法运行，无法评估"` — i.e. `"关卡/场景/游戏数值"` and `"反馈与 Juice(打击感/音效/粒子)"`.
- **`total_score`** is `"0/<checklist 总条目数>"`.
- The blocking defect must be stated **in Chinese** with file path + symbol + a one-line cause. Example reason text: `代码无法运行：src/main.tsx 第 8 行 createRoot 引用的 <App /> 在 src/App.tsx 中并未导出，import 解析失败，应用无法挂载。`
- **Skip Stage B entirely** (do not run per-checklist verification, do not award partial credit for any feature whose code happens to look correct in isolation when the project as a whole cannot start).
- It is acceptable for all checklist items and both auxiliary dimensions to share the same blocking-defect citation in their reason text; you do not need to invent independent paragraphs.

## 2.4 Deep Static-Verification Requirements (Apply to EVERY Stage B Verdict)

These requirements exist because the most common judging error is awarding a pass on **surface evidence** — a matching constant, a well-named identifier, an isolated function — without proving the behavior is reachable, actually executed, and observable by the player. Apply every applicable requirement to each checklist item; when one is violated on the item's causal path, the item scores `"0, <中文原因>"` and the reason states which requirement failed.

**Scope discipline:** a violation fails an item only when it lies on that item's **causal path** — the code the item's observable behavior actually depends on. Off-path defects (an unreachable duplicate branch beside a reachable correct one, an unconsumed config field shadowed by a correct hardcoded value on the executing path, dead code the shipped game never touches) are cited as 潜在风险 in the reason without changing the score. Never let a risk-note soften a genuine causal-path violation into a pass. The same evidence standards also govern what you cite when scoring §3.3 / §3.4.

1. **Definition + consumption.** Evidence for any numeric or behavioral requirement must include both where the value / logic is defined AND where the executing control flow consumes it. Config / schema fields never read at runtime, helpers with no caller, formulas inside unreachable branches, styles / assets nothing applies, and matching string literals are not implementation.

2. **Reachability precedes credit.** Prove the state in which the feature fires is reachable in normal play:
   - *Input chain* — trace the real gesture (click / touch / key) through every coordinate transform to the state-mutating handler. Drawn geometry and hit-test geometry must share the same coordinate space; overlays must not swallow input; an invisible or misplaced hotspot, or an early-return that clears a selection before the command branch runs, makes every downstream feature unreachable. Confirm entry-point UI actually falls inside representative **phone** viewports (both a small 360×640-class screen and a tall 430×932-class screen, with the safe area subtracted) with a registered hit target.
   - *Game state* — features gated behind later levels / waves / accumulated states require the whole prerequisite chain to be attainable: earlier stages solvable, the economy able to afford prerequisites, the tested intermediate state constructible through legal play. A broken prerequisite chain fails the item even when its local code is correct.
   - *Default liveness* — with no player input and shipped defaults, the game must not self-terminate or soft-lock before the tested mechanic can occur (units drifting out of bounds from a coordinate-frame bug, initial values already beyond an end-condition threshold, a structural resource deadlock). If default play collapses first, every dependent item fails.

3. **Terminal states & state machines.** Enumerate ALL write points of win / lose / score / phase and back-trace each one's conditions; the stated predicate must hold as a full conjunction, and "destroyed" must not be conflated with "escaped / reached the goal". Phase loops must provably terminate and return to a playable state — any freeze / banner / replay timer must be decremented by a clock that is not itself frozen; when two outcomes can fire in the same tick, the stated priority must survive the actual execution order. A guard that can never be true under the surrounding update order is dead code, not implementation.

4. **Numeric semantics over string matching.**
   - Verify stated outcomes under the actual integration and units (an outcome ratio may require a square-root parameter under gravity integration; an impulse must survive damping over the effect window) — do not just match a constant.
   - Wall-clock claims must accumulate real elapsed time, not a fixed per-frame constant; verify stated tolerances under varying frame rates, and check both the first cycle and the steady-state period of scheduled events.
   - Evaluate boundaries: `>=` vs `>`, zero / empty cases, exact thresholds, and same-tick simultaneous events under the real update order.
   - Fast movers must not tunnel: swept or previous-position collision checks, `dt`-scaled sub-steps, or engine-provided continuous collision detection where speeds exceed collider thickness per step.
   - When an item embeds a worked example, symbolically execute it from the stated initial state through the full chain and require the exact stated result.

5. **Observability.** An internal mutation that never reaches the screen does not pass an observable-behavior rubric. Trace the value from its write to the rendered output and confirm the render layer reads the SAME state the logic writes. If game state lives in a mutable object outside the UI framework and the UI re-submits the same reference (no clone, no version counter, no subscription), the framework never re-renders — every visible-update rubric through that path fails even though the internal number changed. Feedback must be bound to its specific event (the required sound / animation for that event, not a generic one; an actual visual change on the subject, not an unused style). A display claiming to list every entry fails if it truncates within a normal playthrough.

6. **Dual implementations.** When one rule exists twice (player path vs AI path, per-frame path vs precomputed path, render geometry vs collision geometry, displayed value vs settled value), verify the rubric against both copies or prove they share a single source; universally-worded items (任何情况下 / 绝不 / 始终) fail if any copy breaks.

7. **Conjunctions decompose.** Items containing 且 / 但 / 同时 / `+` split into sub-assertions, each verified independently — including its own reachability. Any failed sub-assertion fails the item; name the failing clause in the reason.

8. **"Never happens" needs write-point enumeration.** To pass a negative claim, enumerate every code path that can write the relevant state — including alternate input paths, buffered / synthesized inputs, spawn edge cases, and restart logic — and show each is gated as required. Absence of a keyword is not proof; one ungated path fails the item.

9. **Atomic transactions; exact undo.** A failed action (invalid placement, insufficient resources, rejected move) must leave EVERY piece of state unchanged — no pre-deducted resources, no consumed cooldowns or counters, no half-applied moves. Where undo exists, it must restore the exact prior snapshot LIFO, including derived state, and one logical action must undo as one unit.

10. **Persistence closes the loop.** A survives-reload claim requires all four stages: write at the correct time (success path only; best results merged, not overwritten by worse retries) → a load path that actually feeds initial state → consumption by the same logic → UI that renders the restored value. Terminal states must persist correctly, and no later unconditional save may clobber a deliberate clear.

11. **AI verified on worst-case branches.** Behavioral claims must hold across all random branches and shipped defaults, not just the happy path; a random early-return must not be able to starve a mandatory action, and difficulty tiers must not silently replace a stated fixed rule. Movement claims need a convergence check (distance to target strictly decreases per step; coordinate-frame conversion applied exactly once). Scheduled behaviors are verified by integrating the actual scheduler with shipped defaults over the stated window and counting the triggers. Long-horizon liveness claims need bounded progress that does not hinge on unseeded randomness with no floor, and repeat-trigger claims require the state machine to provably re-arm.

12. **Placeholders & degraded assets.** A render path that only draws scaffold / placeholder content fails every visual rubric it covers, regardless of the logic underneath. Assets referenced only from dev / temporary remote URLs with no local copy and no error / timeout fallback are treated as absent for dependent rubrics; a programmatic fallback counts as present.

13. **Exactly-once & write-time bounds.** Events worded 恰好 / 精确 / 每次…一次 must fire exactly once per cause: on the first threshold crossing only, deduplicated by a stable identity, immune to repeated frames, to mutually exclusive sibling branches both firing, and to double delivery through parallel input paths. One user gesture produces exactly one logical action. Bounded values must hold their bounds at every observable moment — clamp at the write site; a deferred clamp that lets any observer see an out-of-range value fails the bound.

14. **Pause & deferred callbacks.** When the brief includes pause, the paused branch must freeze the ENTIRE update graph — physics, AI, timers, spawners, scheduled events — and resume must continue from the same values without rebuilding state or retro-charging elapsed wall-clock time. Any deferred / delayed callback must re-validate its preconditions when it fires (or block conflicting input while pending) and must be guarded against firing across a scene / level / run change.

15. **Randomness and determinism cut both ways.** Where the rubric requires variation, verify the generator actually re-runs with fresh randomness on every new run AND its post-conditions hold on every generation path — check them as properties of the generator, not of one sampled output; a fixed or reused layout is a placeholder. Where the rubric requires determinism, verify the mapping has no random source and no hidden dependence on unrelated state. Probabilistic claims require a genuine independent sample per event — cached rolls or pregenerated outcomes that make all-success / all-fail typical are fails.

---

# 3. Evaluation Procedure

This chapter specifies the procedure you must follow to produce the JSON output (§4). It has two ordered stages plus two auxiliary dimensions. **The checklist (§1.2) is the core**; the two auxiliary dimensions are independent supplements scored on a 0–5 scale.

## 3.1 Stage A — Runnability Gate (Defined in §2.3)

Run the Runnability Gate first; the full rules and failure consequences are in §2.3. Recap:

- **Gate passes** → proceed to §3.2 (Stage B checklist) and the two auxiliary dimensions (§3.3, §3.4).
- **Gate fails** → every checklist item in the output becomes `"0, 代码无法运行：<具体阻断点>"`; both auxiliary dimensions become `"0;代码无法运行，无法评估"`; `total_score` becomes `"0/<checklist 总条目数>"`. **Skip Stage B and the auxiliary scoring entirely** — do not attempt partial credit.

## 3.2 Stage B — Per-Checklist-Item Strict Verification (Core)

For every item in `{checklist}`, perform an independent, strict, project-wide verification.

### Verification procedure

1. **Trace across the whole project.** Start from the most likely entry (component / store action / hook / config) and follow the control flow through every file the item depends on. Reading any single file in isolation is **not** sufficient — the feature must work as part of the running project.
2. **Verify completeness and logical correctness.** The feature must be wired into the actual execution path (not just declared / typed / imported), free of obvious logical bugs that would produce wrong behavior, and consistent with the rest of the project (no contradicting state, no orphan handler, no broken cross-module assumption).
3. **Apply the category rules from §2.1 Rule 7** — positive feature requires runnable code; tech / asset constraint must match exactly; negative constraint requires verifiable absence; composite items joined by `+` require every sub-feature to pass independently.
4. **Apply the deep static-verification requirements from §2.4.** In particular: a matching constant without a consumption site, an unreachable prerequisite state, a dead branch, an internal mutation that never reaches the rendered UI (including the mutable-store / same-reference React re-render trap), a non-atomic failure path, or a rule fixed in only one of two parallel implementations all mean the item fails **when the violation lies on the item's causal path** (§2.4 scope discipline) — regardless of how correct the isolated fragment looks. Off-path defects are cited as 潜在风险 in the reason without changing the score. State which §2.4 requirement was violated in the reason text.

### Per-item scoring (binary)

Each checklist item receives a binary score in the output. **All values follow the unified `"<score>, <reason>"` format** — the trailing `, ` is kept even when the score is `1` so every checklist value parses the same way:

- **`"1, "`** — fully implemented and logically correct end-to-end across the project. Reason is intentionally empty (`1` plus comma plus space), which is the literal pass marker. Partial implementations, near-misses, broken wiring, or items implemented only via comments / dead code / never-invoked functions / type-only declarations **do not earn `"1, "`**.
- **`"0, <中文原因>"`** — missing, partial, incorrect, or wired in a way that would not actually work. The reason **must** be written in Chinese and must include: file relative path + function / hook / reducer / component / config key (and line range when useful) + a one-line cause. If the item is a negative constraint that has been violated, explicitly name the forbidden subsystem found in the code.

There is **no halfway numeric** at the item level — the project either implements the feature correctly or it does not. Surface "almost there" implementations through the `0` reason text, not through a partial score.

### `total_score`

After scoring every checklist item, compute:

```
total_score = "<得 1 分的条目数>/<checklist 总条目数>"
```

Express it as a **fraction string** (e.g. `"8/10"`) — not a decimal, percentage, or aggregate float. The two auxiliary dimensions do **not** enter `total_score`.

## 3.3 Auxiliary Dimension — 关卡 / 场景 / 游戏数值

Scored on **0–5**, independent of the checklist. This dimension captures the overall design quality of the level / scene / numeric system — aspects the checklist may not enumerate item by item.

**What to check:**

- Number of levels / scenes; level config files (JSON / TS); per-level parameters.
- Difficulty curve — should be monotonically non-decreasing unless the brief explicitly says otherwise.
- Numerical balance — damage, speed, HP, drop rate, spawn rate, cooldown.
- Scene-transition correctness — does state (HP / score / inventory) persist or reset across transitions as the brief requires?
- Save / checkpoint logic if the brief requires it.

**Scoring rubric (0–5):**

- **5** — full design; multiple levels / scenes; clear, sensible difficulty curve; numerics balanced and tunable from config; state preservation across transitions is correct.
- **4** — solid implementation with one or two minor imbalances or rough transitions.
- **3** — basic level / numeric structure exists but with noticeable issues (one level too easy / hard, hard-coded numerics with poor values, transitions lose some state).
- **2** — minimal scaffolding only; balance clearly off; multiple state-loss bugs across transitions.
- **1** — level / scene / numeric system exists in code but is broken (transitions reset everything, only one level, numerics nonsensical, later level strictly easier than earlier).
- **0** — entirely missing where the brief required it, or genre has no analogous design layer (explain in reason).

**If the game's genre does not have a traditional level / scene / numeric layer** (endless runner with one infinite scene, pure puzzle, single-screen game, etc.), evaluate the **equivalent design layer** for that genre (e.g. difficulty ramp over time, puzzle progression, single-scene numeric balance) on the same 0–5 scale, and in the reason name the equivalent concept you scored. If the genre genuinely has no analogous design layer at all, score `0` and explain why this dimension does not apply.

**Value format in the JSON:** `"<0-5>;<中文打分说明，引用代码证据：文件路径 + 函数 / 符号 + 必要时行号>"`.

## 3.4 Auxiliary Dimension — 反馈与 Juice (打击感 / 音效 / 粒子)

Scored on **0–5**, independent of the checklist. This dimension captures audiovisual feedback richness — the "game feel" / juice that the checklist may not enumerate exhaustively.

**What to check:**

- **Hit feedback** — screen shake, flash, knockback, hitstop, damage numbers floating up.
- **Input feedback** — button press / touch animation, visual response on press.
- **Audio** — SFX on hit / jump / pickup / level-up / UI; BGM loop; volume mixing.
- **Particles** — hit sparks, explosions, trails, magic, ambient effects.
- **UI animation** — score pop-up, HP bar tween, level-up flash, scene transitions.
- **Consistency** — every core action should have *some* feedback; a core action with zero feedback is a noticeable defect.

**Scoring rubric (0–5):**

- **5** — every core action has both visual *and* audio feedback; particles, screen shake, and UI animations cohere; no obvious silent or visually flat interaction.
- **4** — most actions have both visual and audio feedback with one or two gaps.
- **3** — basic visual or audio feedback present for the most important actions; juice is sparse but functional.
- **2** — minimal feedback; multiple core actions are silent or visually flat.
- **1** — almost no feedback; the game looks and sounds like a wireframe; hits produce zero visual or audio change.
- **0** — no feedback layer at all where the brief required it; no SFX whatsoever when the brief required audio.

**If the game's genre legitimately has minimal juice** (turn-based text adventure, pure logic puzzle with no animated state, etc.), evaluate the **genre-appropriate feedback** (text reveal pacing, success / failure cues, focus-state animation, transition smoothness) on the same 0–5 scale; in the reason, name the equivalent feedback layer you scored.

**Value format in the JSON:** `"<0-5>;<中文打分说明，引用代码证据：文件路径 + 函数 / 符号 + 必要时行号>"`.

---

# 4. Output Format

## 4.1 Format Example

The skeleton below uses `<...>` placeholders — in the real output, use each `{checklist}` item's **original verbatim Chinese wording** as its JSON key (one entry per item, in the same order as the input array):

```json
{{
    "关卡/场景/游戏数值": "<0-5>;<中文打分说明：覆盖关卡数 / 难度曲线 / 数值平衡 / 场景切换 / 状态保持，引用代码证据：文件路径 + 函数 / 符号 + 必要时行号；若游戏类型不涉及关卡 / 场景，说明所评估的等效维度>",
    "反馈与 Juice(打击感/音效/粒子)": "<0-5>;<中文打分说明：覆盖打击感 / 音效 / 粒子 / UI 动效的完备程度，引用代码证据：文件路径 + 函数 / 符号 + 必要时行号；若游戏类型本身缺乏 juice 概念，说明所评估的等效反馈层>",
    "<checklist 条目 1 原文>": "1, ",
    "<checklist 条目 2 原文>": "0, <中文说明：文件路径 + 函数 / 符号 + 一句因果>",
    "<checklist 条目 3 原文>": "1, ",
    "...": "...",
    "hidden_probes": {{
        "<hidden 探针 1 原文>": "1, <证据：文件路径 + 符号>",
        "<hidden 探针 2 原文>": "0, <中文说明：未实现该推论 / 实现与推论矛盾之处>",
        "...": "..."
    }},
    "total_score": "<得 1 分的条目数>/<checklist 总条目数>"
}}
```

## 4.2 Key Rules

- `hidden_probes` covers **every** §1.2b probe with its verbatim wording as key (omit the object when §1.2b is empty); probes never influence checklist scores, auxiliary dimensions, or `total_score`.

1. **Every item in `{checklist}` must appear as its own top-level JSON key**, with the original Chinese wording **verbatim** — do not paraphrase, abbreviate, translate, reorder, or merge items.
2. The two auxiliary-dimension keys (`"关卡/场景/游戏数值"` and `"反馈与 Juice(打击感/音效/粒子)"`) are **always present**, even when the game genre doesn't naturally include these features — in that case, score the equivalent design / feedback layer per §3.3 / §3.4 and explain in the reason what you actually scored.
3. **Per-checklist value format — uniform `"<score>, <reason>"`:**
   - `"1, "` — implemented and logically correct end-to-end across the project. The trailing `, ` is kept (empty reason) so every checklist value parses identically; do not output bare `"1"`.
   - `"0, <Chinese reason>"` — not implemented / partial / broken; or (for negative constraints) violated. Reason must cite file path + function / hook / reducer / component / config key + one-line cause.
4. **Auxiliary-dimension value format:** `"<0-5>;<Chinese reason>"` — a single integer 0–5, then a `;`, then the reason text. The integer comes first; do not invert the order.
5. **`total_score` is a fraction string** like `"8/10"` — never a decimal, percentage, or aggregate float. The two auxiliary dimensions do **not** enter `total_score`.
6. **If the Runnability Gate (§2.3) fails**, every checklist item is `"0, 代码无法运行：<具体阻断点>"`, both auxiliary dimensions are `"0;代码无法运行，无法评估"`, and `total_score` is `"0/<checklist 总条目数>"`.
7. Output **only** the JSON object — no markdown fences, no preamble, no commentary outside the JSON.

---

# 5. Constraint

Format: Only print the result in JSON format as shown in **Output Format** (§4). Do not output any extra prose outside the JSON object — no markdown code fences, no commentary, no leading or trailing text. Every reason text inside the JSON values must be written in **Chinese** and must cite concrete evidence — file relative path + function / hook / reducer / component / config-key name (and line range when useful) from `{source_code}`. Use each `{checklist}` item's **original verbatim Chinese wording** as its JSON key; do not paraphrase, translate, abbreviate, reorder, or merge items.

---

# 6. Action

Follow the instructions above and evaluate the provided React H5 2D game strictly against `{user_prompt}` (the requirement), `{checklist}` (the explicit feature verification list — the primary verification driver), and `{source_code}` (the source — read it line by line). Produce the JSON output that satisfies the **Constraint**.
"""

class Eval2DMobileScenario:
    """Run the 2D **mobile** static-code evaluation prompt against an agent-generated project."""

    def eval(self, base_info: dict, output_file_path: str) -> dict:
        """Evaluate one task and return the judge's validated JSON verdict.

        Args:
            base_info: Task metadata. Must contain `prompt` (the original brief,
                a string) and `checklist` (a non-empty list of Chinese strings).
                Optional `attachment` (list of filenames) is also read.
            output_file_path: Path to the agent-generated project directory.
                Can be absolute, or relative to the project root.

        Project collection, template filling, the model call, output-contract
        validation and `total_score` recomputation are shared with the other
        judges in `utils/static_eval.py`, so the scenarios cannot drift apart.
        """
        return run_static_eval(
            TWO_D_MOBILE_EVALUATION_PROMPT, base_info, output_file_path,
            project_root=_PROJECT_ROOT,
        )


if __name__ == "__main__":
   base_info = {
    "task_id": "2D_2d_action_L1_001",
    "category": "2D动作",
    "desc": "2D 俯视角简单割草（3分钟单局，2种武器）",
    "agent_ability": [
      "C1",
      "C2",
      "C6",
      "C7"
    ],
    "prompt": "做一款手机端 2D 俯视角割草小游戏，React + PixiJS。竖屏全屏自适应（100vw × 100dvh），左下角虚拟摇杆移动，自动攻击最近的敌人。2 种武器：回旋镖（前方扇形）、光环（身周持续伤害）。敌人从四边随机刷出，密度随时间缓慢增加。击杀掉经验球，集满升级，2 选 1。3 分钟单局，存活到底即通关。HP 条与击杀数置于顶部安全区内。受击红闪 + 轻微屏震。不要商店，不要联网，不要内购。",
    "level": "L1",
    "label": [
      "type:2d_action"
    ],
    "attachment": [],
    "result_verify": "",
    "checklist": [
      "左下角虚拟摇杆可拖动控制角色移动，方向正确且角色不会移出可视区域",
      "回旋镖武器以角色为中心向前方发出扇形攻击，光环武器在角色周身持续造成伤害，两种武器行为明显不同",
      "击杀敌人后地面出现经验球，拾取后经验条增长；经验满触发升级界面，玩家可在「强化当前武器」和「解锁另一把武器」中选 1",
      "敌人从画布四条边随机刷出，随游戏时间推进刷新密度可见增加",
      "左上角显示 HP 条，右上角显示击杀数，数值随游戏进程实时更新",
      "玩家受击时角色出现红色闪烁效果，同时画面产生轻微抖动（屏震）",
      "游戏在 3 分钟后结束并显示通关结果（击杀数等），期间无商店、无内购、无联网功能"
    ],
    "notes": "scenario=2D | game_type=2d_action | level=L1 | 合成 case"
  }
   output_file_path = "result/2D_mobile_benchmark_easy/2D_2d_action_L1_001"

   result = Eval2DMobileScenario().eval(base_info, output_file_path)
   print(json.dumps(result, ensure_ascii=False, indent=2))
