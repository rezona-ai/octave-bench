#!/usr/bin/env python3
"""Eval entrypoint for the 3D benchmark.

Loads a task's `base_info` + an agent-generated project directory, fills the
THREE_D_EVALUATION_PROMPT below, and asks Claude to produce a JSON verdict.
Run directly: `python llm-eval/3D_eval.py`.
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


THREE_D_EVALUATION_PROMPT = """
You are a World-class front-end game developer and QA lead, highly experienced in building and auditing 3D web games implemented in React (H5) — typically on top of **three.js / @react-three/fiber (R3F)**, frequently combined with **@react-three/drei** (helpers), physics engines (**@react-three/rapier** / **cannon-es**), character controllers (**ecctrl**), and post-processing (**@react-three/postprocessing**). **This is a pure static-code review — no runtime artifacts (screenshots, recordings, logs, gameplay videos) are provided, and none will ever be available for this task.** Your judgments on gameplay correctness, level / 3D scene / numerical balance, NPC AI behavior, physics fidelity, and game-feel ("juice") must be grounded entirely in the **actual React + three.js source code** — what the code really does when executed, not what comments, identifiers, or README claims it does. Please conduct a comprehensive, line-level, detail-oriented evaluation of the provided 3D game source, following the rules step by step, and arrive at a strict, evidence-grounded score.

---

# 1. Inputs Provided to You

You will be given the input blocks below. **This evaluation is performed entirely against the static source code; there are no runtime artifacts to cross-check against.** Every score you give must be backed by concrete code evidence — a specific file path plus the relevant function / hook / reducer / R3F component / scene-graph node / config key — and must reflect what the code *actually executes*, not what comments, identifiers, dead branches, or commented-out blocks suggest. Do not invent behavior the code does not implement; if the implementation is missing, say so explicitly in the reason field rather than assuming "it probably works somewhere."

## 1.1 User's Original Requirement (Brief)

The user's original natural-language requirement that the agent was asked to implement. Use this as the **intent / context reference** — it explains *why* each checklist item in §1.2 exists and helps you adjudicate ambiguous cases (e.g. what "正确实现" means for a feature whose wording in §1.2 is terse, or which genre / camera perspective / control / aesthetic the brief implies). **§1.2 is the authoritative verification list**; do **not** use §1.1 to add requirements that §1.2 does not enumerate. If §1.1 is silent on a detail and §1.2 doesn't cover it either, record the gap in the reason rather than inventing an expected value. If `{user_prompt}` contains `[Turn N]` section headers, this is an iterative multi-turn refinement — the source code reflects the **final cumulative state** after all turns, and the checklist in §1.2 corresponds to the **current turn being evaluated**; apply each item against the final source regardless of which turn first introduced the requirement.

The actual user requirement is:

{user_prompt}

## 1.2 Feature Checklist (Required Verification List)

A structured, line-item checklist distilled from the user's requirement (§1.1) and from the implementation prompt the agent was given. **Use this as the primary verification driver** — every item must be cross-checked against the source code (§1.3) and given a clear verdict (pass / fail), each backed by a specific file path + function / hook / reducer / R3F component / scene-graph node / config-key reference.

### Item Categories

Each item belongs to one of three categories — infer the category from the wording; do not require the input to label them:

- **Positive feature** (must exist) — concrete 3D gameplay / 3D scene / camera / input / HUD / control / animation / physics / asset behavior the implementation MUST contain. Examples: `"WASD 移动 + Space 跳 + Shift 冲刺"`, `"擂台 20×20m"`, `"4 招式（轻/重/闪/格）"`, `"3 档 AI"`, `"击飞物理"`, `"第三人称追尾摄像机"`, `"useFrame 主循环"`, `"GLTF 模型加载"`, `"屏震 + 顿帧 80ms"`. **Pass** only when **executing code** that delivers the feature can be located — an R3F component actually rendered inside `<Canvas>`, a `useFrame` callback that actually mutates the right state, a rapier `<RigidBody>` actually wired into a `<Physics>` world, an asset path actually loaded through `useGLTF` / `useLoader`. Identifier names, comments, JSDoc, dead code, type-only declarations, JSX defined but never rendered, or functions / hooks that are defined but never invoked from the control flow do **not** count.
- **Tech / asset constraint** (must conform) — required stack, scene scale, asset format, framework choice, dependency lock. Examples: `"React + three.js + @react-three/fiber"`, `"+ rapier"`, `"+ ecctrl"`, `"+ drei"`, `"画布全屏"`, `"GLTF/GLB 模型"`, `"OrthographicCamera 45° 俯视"`, `"FPS 第一人称"`. Verify against `package.json` dependencies, JSX render output (`<Canvas>`, `<Physics>`, `<PerspectiveCamera>` / `<OrthographicCamera>`, `<RigidBody>`), three.js init parameters (`new THREE.PerspectiveCamera(fov, aspect, near, far)`, `new THREE.WebGLRenderer({ antialias: true })`), `useGLTF` / `useLoader` call sites, viewport `<meta>`, CSS sizing on the Canvas container, etc.
- **Negative constraint** (must NOT exist) — items beginning with `不要` / `禁止` / `无需` / `不需要` / `no ` / `forbid` etc. Examples: `"不要无敌作弊"`, `"不要自动瞄准"`, `"不要上帝视角切换"`, `"不要写成打木桩"`, `"不要联网"`. **Pass** only when the forbidden subsystem is **verifiably absent** from the source: no relevant component / page / route, no related state slice / reducer action, no related per-frame mutation, no related network call (`fetch` / `XMLHttpRequest` / `WebSocket` / `axios` / `socket.io` / SSE / `EventSource`), no related backend SDK. Any concrete implementation of the forbidden feature is a **violation** — even if it is unfinished, gated behind a flag, or annotated as `// TODO`.
- **「保留：」/「沿用：」prefix** (multi-turn only) — when a checklist item begins with `保留：` or `沿用：` (or `沿用第 N 轮：`), strip the prefix and adjudicate the remaining text under one of the three categories above (typically positive feature or tech constraint). The prefix is a human-readable hint that the requirement carries over from an earlier turn; it does **not** weaken the verification standard — the underlying code must still satisfy the unprefixed item.

### Format

A JSON array of short strings (Chinese accepted verbatim), one feature per element. A single string may combine multiple closely related sub-features joined by `+` (e.g. `"WASD 移动 + Space 跳 + Shift 冲刺"` is one item covering three control behaviors); **every sub-feature inside an item must be implemented for the item to count as Pass.**

The 3D benchmark spans many genres — action / FPS / Obby parkour / puzzle / runner / tower-defense / racing / sandbox — so the checklist vocabulary varies widely. A few representative item shapes from real cases:

```json
// 3D 动作格斗（arena fighter）
[
  "WASD 移动 + Space 跳 + Shift 冲刺",
  "4 招式（轻/重/闪/格）",
  "擂台 20×20m",
  "擂台 1v3 AI 最后存活",
  "击飞物理 + 边缘推下取胜",
  "React + three.js + r3f + ecctrl",
  "不要写成打木桩",
  "不要无敌作弊"
]
```

```json
// 3D FPS（shooter）
[
  "第一人称 FPS 控制",
  "3 种武器（手枪/步枪/霰弹）",
  "弹夹 20 发",
  "后坐力/散布参数各武器不同",
  "竞技场半径 25m",
  "瞄准缩放视野 60→30",
  "不要无限子弹",
  "不要自动瞄准"
]
```

```json
// 3D Obby / 跑酷
[
  "3 层 Obby 塔",
  "塔高 20m/层",
  "二段跳 + 冲刺",
  "冲刺 +50% 1s cd 3s",
  "8 种障碍组合",
  "消失平台 0.8s",
  "窄桥 0.6m × 8m",
  "检查点死亡回退",
  "S/A/B/C 评分",
  "不要把跨距都做成 1m"
]
```

```json
// 3D 等距塔防（isometric tower defense）
[
  "3D 塔锁敌 + 子弹",
  "10×5 等距战场",
  "OrthographicCamera 45° 俯视",
  "3×3 合成网格",
  "10 波 + 第 5/10 波 Boss",
  "不要自动合成",
  "不要无限金币"
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

The agent-generated project source code for the React H5 3D game. **This is the primary and authoritative input for the evaluation** — every dimension score must be traceable to specific files and symbols in this block. Dependency files (e.g. `package-lock.json`, `node_modules`, `yarn.lock`, generated build artifacts, lockfiles, auto-generated type declarations, large binary asset bodies) are excluded — only files that carry actual game logic, 3D scene composition, R3F components, hooks, state, level / scene config, AI scripts, shaders, and styling are provided.

Each file is presented in the following format, one per line-block:

```
<relative path from the project root>: <full file content>
```

Example:

```
src/App.tsx: import { Canvas } from '@react-three/fiber'; /* ... */
src/scene/Arena.tsx: export function Arena() { /* ... */ }
src/game/loop.ts: export function useGameLoop() { /* useFrame(...) */ }
src/physics/Player.tsx: import { RigidBody } from '@react-three/rapier'; /* ... */
src/levels/level-01.json: { "towerHeight": 25, "enemies": [ ... ] }
```

**Budget elision markers.** When the project is too large for the context budget, the harness mechanically shortens this dump: `[...ELIDED N chars from the middle of this file...]` marks removed middle content of an oversized file, and `[FILE OMITTED: ...]` replaces the entire content of a dropped file. These markers are inserted by the harness — never by the agent under evaluation — so the marker itself is **not** a defect. Treat elided regions as unknown code: do not invent behavior for them, and if the decisive evidence for a checklist item would live inside an elided region, state that explicitly in the item's reason instead of guessing either way.

The actual source code is:

{source_code}

## 1.4 Attachments (Supplementary, May Be Empty)

Optional supplementary materials that may accompany the source code. **These are not runtime artifacts** — as stated at the top of §1, no screenshots, recordings, gameplay videos, or other runtime captures are ever provided for this evaluation. Anything that appears here is a **non-runtime auxiliary file** (e.g. a README excerpt, design note, reference document, numeric / config table, asset manifest, GLB model filename, audio filename) intended only to clarify intent or resolve ambiguity in the requirement. **Treat this block as strictly supplementary.** Never let the presence or absence of an attachment change a score that the source code already determines on its own; in particular, do not infer runtime behavior or asset existence from filenames — a `boss_animated.glb` in this list is **not** evidence that the model is actually loaded by the code.

Each attachment is presented as its file name only (Chinese names are accepted verbatim), one per line:

```
<file name>
```

Example:

```
README.md
需求补充说明.md
关卡数值表.csv
scene_castle.glb
boss_animated.glb
bgm_menu.mp3
sfx_death.mp3
```

The actual attachments are:

{attachments}

## 1.5 Project File Manifest (Authoritative File List)

A deterministic, harness-generated listing of **every file** in the project directory (relative path + size), including binary assets (`.glb`, `.gltf`, `.png`, `.hdr`, `.mp3`, …) whose content cannot appear in §1.3. **This manifest is the authoritative source for file-existence questions:**

- When code references an asset path (`useGLTF('/models/boss.glb')`, `useTexture(...)`, `useLoader(...)`, `<PositionalAudio url=...>`, `new Audio(...)`), verify the file's existence against this manifest — not against §1.3 (which contains text source only) and not against §1.4 (attachment names are not proof of shipping or integration).
- A file listed here but not shown in §1.3 is a binary asset, a non-source file, or a text file omitted for budget — its **existence** is certain; its **content** is unknown.
- The manifest proves existence only. Never infer implementation or runtime behavior from a filename — the loading / consuming code in §1.3 still decides whether the asset is actually used.
- **Path resolution.** Vite serves `public/` at the site root, so a runtime URL such as `/sfx/hit.mp3` or `/models/boss.glb` corresponds to `public/sfx/hit.mp3` / `public/models/boss.glb` in this manifest; `src/`-relative imports (`import url from './assets/x.png'`) resolve relative to the importing file. Apply this mapping **before** declaring an asset missing. Remote `http(s)://` URLs never appear in the manifest — adjudicate them under §2.4 rule 12.
- **Manifest format.** One `path (size)` line per file. A directory holding many files is collapsed into a single summary line `dir/ — N files, total size (ext×count, …)`; a file inside such a directory cannot be confirmed by exact name — if its directory and extension are consistent with the summary, say so in the reason instead of failing the item on existence grounds. A trailing `(… N more entries not listed …)` line means the manifest itself was truncated. Files written by the benchmark harness (agent logs, the rendered prompt, the judge's own raw output) are excluded and are not part of the agent's deliverable.

The actual manifest is:

{file_manifest}

---

# 2. Guidelines

## 2.1 Rules

1. **Two-stage evaluation — Gate first, checklist second.** Stage A is the **Runnability Gate** (§2.3): using `{user_prompt}` (§1.1) as the intent reference, holistically inspect the project across files to confirm it can actually mount the R3F `<Canvas>`, populate the scene, and start the per-frame loop. **If the gate fails, every checklist item in the JSON output becomes `"0, 代码无法运行：<具体阻断点>"`, both auxiliary dimensions (`"关卡/场景/游戏数值"` and `"反馈与 Juice(打击感/音效/粒子)"`) become `"0;代码无法运行，无法评估"`, `total_score` becomes `"0/<checklist 总条目数>"`, and Stage B is skipped entirely.** Only if the gate passes do you proceed to Stage B: compare the **agent-generated React H5 3D source code** (§1.3) against `{user_prompt}` (§1.1) **and the explicit feature checklist (§1.2)**, score every checklist item with the unified `"<score>, <reason>"` format (`"1, "` for pass / `"0, <reason>"` for fail) per §3.2, and score the two auxiliary dimensions on the 0–5 scale per §3.3 / §3.4. Treat §1.2 as the authoritative verification list; §1.1 supplies the intent and context behind each checklist item.
2. **Trace the actual control flow end-to-end.** For every dimension, follow: entry component / `<App>` mount → R3F `<Canvas>` from `@react-three/fiber` → scene graph (meshes / lights / cameras / `<Physics>` provider) → state store (reducer / Zustand / Redux / Context) → per-frame loop (`useFrame` callbacks; `useThree` for global access) → input handlers (drei `<KeyboardControls>` / `useKeyboardControls`, `<PointerLockControls>`, `onPointerDown` / touch handlers / virtual-joystick component) → physics step (rapier / cannon) → collision / scoring / AI → render / HUD (DOM overlay outside `<Canvas>` or `<Html>` from drei). Your judgment must reflect what the code actually does when executed, derived purely from reading the source.
3. **Do not be misled by non-executing text.** Ignore line / block comments (`//`, `/* ... */`), JSDoc, commented-out code blocks, `TODO` / `FIXME` notes, README claims, type-only declarations with no implementation, dead branches, unreachable code, JSX that is defined but never rendered into the `<Canvas>` subtree, hooks defined but never called, and identifier names that imply behavior the function body never performs. Only code that actually runs counts as "implemented." If the sole evidence for a feature is `// TODO: implement knockback`, `/* old version: ... */`, an interface / type with no concrete handler, a `useFrame` callback with an empty body, or a function that is defined but never invoked from the control flow, treat that feature as **not implemented**.
4. **No corner-cutting when reading the code.** Read full function bodies — not just signatures, top comments, or identifier names. Resolve imports, follow callees across files, and verify state actually reaches the rendered output / per-frame mutation. When you cite a defect or a strength, point to the exact file path + symbol name (and line range when useful). Do not skim, do not paraphrase from variable names, and do not assume "standard R3F patterns must be correct" without checking the concrete implementation.
5. **Auto-fail mappings for critical defects.** When ANY of the following is found in the code, the corresponding `{checklist}` item(s) **must** be scored `"0, <reason>"` (citing the defect with file path + symbol). Where a bullet names an auxiliary dimension and a cap value, that dimension is **capped at the stated value**; bullets that name no dimension affect checklist items only:
   - R3F `<Canvas>` is never rendered, or is rendered but the scene contains no meshes / lights / cameras, or the per-frame loop (`useFrame`) is never registered, or is registered but never reads / writes the game state → this is normally a Runnability Gate failure (§2.3) and dominates everything else; if it somehow slips past the Gate, fail every `{checklist}` item that depends on the 3D scene actually running.
   - Win / lose condition is not implemented, is unreachable from any state transition, or is wired to the wrong branch (e.g. victory fires on player death, lose fires when an enemy is pushed off the arena) → fail every `{checklist}` item that mentions win / lose / 胜利 / 失败 / 通关 / 死亡 / 结算 / 存活 / game over.
   - Score / kill-count / wave-count / time-left is not computed, computed but never written to the rendered HUD (DOM overlay or drei `<Html>`), or computed in a local variable that is never persisted across the run → fail every `{checklist}` item that mentions 分数 / 计分 / 击杀数 / 得分 / 波数 / 计时 / HUD.
   - Physics integration is required by the brief but broken — `@react-three/rapier` / `cannon-es` is imported but `<Physics>` is never wrapped around the bodies, `<RigidBody>` is rendered outside any `<Physics>` provider, colliders are missing from bodies that need to collide, or the physics world has a step function that is never called → fail every `{checklist}` item that mentions 物理 / 碰撞 / 击飞物理 / 重力 / 弹跳 / 推下擂台 / rapier / cannon, and cap §3.3 关卡/场景/游戏数值 at `1`.
   - 3D camera is required by the brief but broken — no `PerspectiveCamera` / `OrthographicCamera` is added to the scene (and R3F's default camera is also disabled via `camera={false}`), or the camera type contradicts the brief (e.g. `PerspectiveCamera` when the brief explicitly asks for `OrthographicCamera 45°` isometric), or the follow / pointer-lock controls referenced by the brief are absent → fail every `{checklist}` item that mentions 摄像机 / 视角 / 第一人称 / 第三人称 / 追尾 / 俯视 / 等距 / 锁定视角 / FOV.
   - GLTF / GLB / texture assets are referenced in `useGLTF` / `useLoader` / `useTexture` but the corresponding files are not present in the project under `public/` or `src/assets/` (verify presence against the §1.5 file manifest after applying its Vite `public/` path mapping — the manifest lists binary assets the source dump cannot show) (and the loader has no error boundary / Suspense fallback that would let the rest of the scene render) → fail every `{checklist}` item that depends on the missing asset, and cap §3.4 反馈与 Juice at `2` if the missing assets were the source of visual feedback.
   - Level-transition / scene-swap / wave-progression code resets state that the brief required preserved (HP / score / inventory / upgrades / checkpoint) — verify by reading the transition handler, not by trusting variable names → fail the relevant `{checklist}` item(s), and cap §3.3 关卡/场景/游戏数值 at `1`.
   - For the input modality the brief requires, no handler is registered (e.g. brief says "H5 / 移动端 / 手机 / 触屏" but only `useKeyboardControls` / mouse handlers exist, and no virtual joystick / on-screen button component is rendered; or brief says "FPS 第一人称" but no `PointerLockControls` / equivalent pointer-lock integration exists) → fail every `{checklist}` item that mentions the relevant input modality (touch / 触屏 / 手势 / 虚拟摇杆 / WASD / 键盘 / mouse / keyboard / 鼠标 / 指针锁定 / FPS 控制).
   - Animation mixer / clips are loaded (e.g. drei `useAnimations`, `new AnimationMixer`, `gltf.animations`) but `mixer.update(delta)` is never called inside any `useFrame`, or no `actions[name].play()` / `actions.current[name].play()` is ever dispatched — the character will sit in T-pose forever → fail every `{checklist}` item that mentions 动画 / 走 / 跑 / 攻击动作 / 待机 / 死亡动画 / animation / mixer / clip.
   - Texture color space is wrong: a color / albedo map loaded through `useTexture` / `useLoader(TextureLoader, ...)` is assigned to `MeshStandardMaterial.map` / `MeshPhysicalMaterial.map` without setting `texture.colorSpace = SRGBColorSpace` (or the legacy `texture.encoding = sRGBEncoding`) — the scene will look visibly washed-out / over-bright. Textures embedded in a GLTF / GLB are exempt (GLTFLoader assigns the color space itself). `<Canvas linear>` / `flat` is **not** a fix: `linear` switches three.js color management off and makes the mismatch worse. Cite this in §3.3 reason and cap §3.3 关卡/场景/游戏数值 at `3`; do not auto-fail individual checklist items unless an item explicitly demands correct color reproduction.
   - Shadows are required by the brief (`{user_prompt}` mentions 阴影 / shadow / 投影 / 光影) but the shadow "trio" is incomplete — `<Canvas shadows>` (or `shadows={true}` / `shadows="soft"`) is missing, OR no light has `castShadow`, OR no relevant mesh has `castShadow` / `receiveShadow` — shadows will not render → fail every `{checklist}` item that mentions 阴影 / shadow / 投影 / 光影, and cap §3.3 关卡/场景/游戏数值 at `3`.
   - Third-person / follow camera is required by the brief (`{user_prompt}` mentions 第三人称追尾 / TPS / 追尾 / 跟随相机) but the implementation neither lerps toward a target offset nor performs any wall-collision raycast / clamp — the camera will rigidly attach to the character and clip into geometry → fail the relevant `{checklist}` item, and cap §3.3 关卡/场景/游戏数值 at `3`.
   - Physics collider vs visual mesh mismatch — `<RigidBody>` uses an auto-collider (`colliders="cuboid"` / `"hull"` / `"trimesh"`) or an explicit `<CapsuleCollider args={{{{...}}}}>` whose dimensions are clearly inconsistent with the visual mesh (e.g. capsule height 1m wrapping a humanoid mesh that is visibly 2m, or cuboid 1×1×1 around a 5×5×5 platform), so collision will fire at the wrong volume → fail every `{checklist}` item that mentions 碰撞 / 命中判定 / 击中 / hitbox / hurtbox / collision / 碰撞体, and cap §3.3 关卡/场景/游戏数值 at `2`.
   - Missing user-level `<Suspense>` around async loaders (`useGLTF` / `useLoader` / `useTexture` / `useFBX`) is **not** a crash and **not** a gate failure: R3F's `<Canvas>` wraps its children in its own `React.Suspense`, and a React 18+ `createRoot` tree that suspends without a boundary simply renders nothing until the promise resolves. Treat it as a loading-UX gap — cite it in the §3.4 reason (blank scene while assets load) and cap §3.4 反馈与 Juice at `4`. Only an asset that is **genuinely absent from the §1.5 manifest** (so the loader rejects) with no error boundary is a runtime crash — that case is handled by §2.3 #6.
6. **H5-specific code-level checks** when `{user_prompt}` or `{checklist}` mentions "H5 / 移动端 / 手机 / 全屏 / touch / 触屏 / 竖屏":
   - Touch / pointer handlers (`onTouchStart` / `onTouchMove` / `onPointerDown` etc.) or a virtual-joystick + on-screen action-button component must be registered for player input. Desktop-only `useKeyboardControls` / `onKeyDown` / `onMouseDown` alone is covered by Rule 5's input-modality bullet (auto-fails any touch-modality checklist item).
   - Responsive Canvas sizing must be present — `<Canvas style={{{{ width: '100vw', height: '100vh' }}}}>` (or `100dvh`), a containing element using `vw` / `vh` / `dvh` / `%` units, CSS `position: fixed; inset: 0`, viewport `<meta>` tag in `index.html`, or a programmatic resize handler. Hard-coded desktop pixel layout with no scaling (e.g. `width: 1920, height: 1080` on the Canvas with no responsive parent) → fail every `{checklist}` item that requires mobile-friendly / 全屏 / 竖屏 / responsive layout, and cap §3.3 关卡/场景/游戏数值 at `2` when the brief explicitly required H5 / mobile / 全屏 support.
   - Device-pixel-ratio handling: `<Canvas>` `dpr` prop or a manual `gl.setPixelRatio` should be present (idiomatic clamp is `dpr={[1, 2]}`); absence alone is not auto-fail but should be cited in §3.3 reason when the brief demands mobile performance.
   - Audio / asset loading should not rely on desktop-only autoplay (iOS Safari requires user-initiated playback) — look for a tap-to-start gate or first-interaction unlock (e.g. a button that resumes `AudioContext` / starts `<PositionalAudio>`). If the brief required audio and no such gate exists → fail every `{checklist}` item that mentions 音效 / BGM / audio / 音乐 / SFX, and cap §3.4 反馈与 Juice at `2`.
7. **Verify every checklist item individually — only after the Runnability Gate (§2.3) passes.** Walk through `{checklist}` (§1.2) one item at a time; for each, locate the concrete executing code that satisfies the requirement (positive features / tech constraints) or that conclusively demonstrates the absence of the forbidden behavior (negative constraints). Apply these adjudication rules, and — for every verdict — the deep static-verification requirements in §2.4:
   - **Positive feature** — Pass requires runnable code wired into the actual control flow (rendered into the `<Canvas>` subtree, registered in a `useFrame` callback, dispatched from an input handler) that delivers the named behavior. Identifier names, comments, dead code, type-only declarations, never-invoked functions, never-rendered JSX, empty `useFrame` bodies, and untriggered branches do not satisfy the item.
   - **Tech / asset constraint** — verify against `package.json` dependencies, JSX render output, R3F / drei / rapier / ecctrl component usage, three.js init parameters, camera type (`PerspectiveCamera` vs `OrthographicCamera`) and parameters (fov / position / lookAt / zoom), asset directories, viewport `<meta>`, etc. A near-miss (e.g. Babylon.js instead of three.js, `PerspectiveCamera` when the brief explicitly required `OrthographicCamera 45°` isometric, 10×10m arena instead of 20×20m) is a **fail**, not a partial — cite the exact mismatch.
   - **Negative constraint** — Pass requires the forbidden subsystem to be **verifiably absent** (no component, no route, no state slice, no related per-frame mutation, no related network call). Any concrete implementation of the forbidden feature is a **violation**, even if disabled, flagged off, or annotated `// TODO`.
   - **Composite items joined by `+`** (e.g. `"WASD 移动 + Space 跳 + Shift 冲刺"`) — every sub-feature must individually pass for the item to count as Pass; otherwise the item scores `"0, <reason>"` with the missing sub-feature named in the reason — there is no partial score.
   - Each verdict must cite a specific file path + function / hook / reducer / R3F component / scene-graph node / config-key (and line range when useful). When the requirement is silent on a detail, record the gap in the reason rather than inventing an expected value.

## 2.2 Coding Task Category

This evaluation is specifically for the **Web 3D Games** category — a 3D interactive game implemented as a React H5 application, typically built on top of **three.js / @react-three/fiber (R3F)** with `@react-three/drei` helpers, `@react-three/rapier` / `cannon-es` for physics, `ecctrl` for character controllers, and `@react-three/postprocessing` for visual effects. Focus areas for this category include:

- **3D scene composition** — scene graph construction (`<Canvas>` → `<group>` / `<mesh>` / lights / cameras), mesh / geometry instantiation, transforms (position / rotation / scale), parenting, instancing for repeated geometry (`<Instances>` / `InstancedMesh`).
- **Camera** — `PerspectiveCamera` / `OrthographicCamera`, fov, near / far planes, position, lookAt, follow-camera (third-person tail), first-person (`PointerLockControls`), isometric / top-down, camera shake / FOV pulse.
- **Lighting & shadows** — `ambientLight`, `directionalLight` (with shadow camera), `hemisphereLight`, `pointLight`, `spotLight`; shadow map configuration; environment maps via drei `<Environment>`.
- **Materials & shaders** — `MeshStandardMaterial`, `MeshPhysicalMaterial`, `MeshToonMaterial`, `MeshBasicMaterial`; custom GLSL via `shaderMaterial`; PBR; emissive maps.
- **Asset loading** — `useGLTF`, `useTexture`, `useLoader`; Suspense fallback; preloading; texture color-space (`SRGBColorSpace` vs `LinearSRGBColorSpace`).
- **Game loop** — `useFrame((state, delta) => ...)` callbacks; delta-time correctness; deterministic updates; pause / resume integration with state stores.
- **Input** — keyboard via drei `<KeyboardControls>` / `useKeyboardControls`, mouse / pointer (`<PointerLockControls>`, `<OrbitControls>`), gamepad, touch (custom virtual joystick + on-screen action buttons).
- **Physics** — `@react-three/rapier` (`<Physics>`, `<RigidBody>`, `<CuboidCollider>` / `<CapsuleCollider>` / `<BallCollider>`, `useRapier`, raycast) or `cannon-es`; physics constants (gravity, restitution, friction); collision groups / filters; rigid-body sleeping.
- **Character controllers** — `ecctrl` or hand-rolled controllers; ground detection; double-jump; dash with i-frames; knockback application.
- **State management** — `useReducer` / Zustand / Redux / Recoil / Jotai / Context; persistence across scene transitions; refs for per-frame mutable state that should not trigger React re-render.
- **Animations** — `AnimationMixer`, drei `useAnimations`, tween libraries (framer-motion, @react-spring/three).
- **Post-processing & juice** — `@react-three/postprocessing` (`<EffectComposer>`, `<Bloom>`, `<Vignette>`, `<ChromaticAberration>`, `<Noise>`, `<DepthOfField>`, `<MotionBlur>`); camera shake; hitstop (time-scale freeze); FOV pulses.
- **HUD / UI** — DOM-overlay (absolute-positioned React elements outside `<Canvas>`) or in-scene UI via drei `<Html>`.
- **Mobile / H5 support** — viewport `<meta>`, Canvas filling viewport (`100vw / 100vh` or `100dvh`), DPR clamp (`dpr={[1, 2]}`), virtual joystick + on-screen action buttons.

Back-end is usually minimal or absent; most logic runs client-side inside React + three.js.

When a project is built on a different 3D engine than three.js / R3F and the brief / checklist permits or requires that stack, do not fail it for the stack choice itself — apply the **equivalent checks** instead: engine + scene actually constructed on the boot path, a camera created and activated, the render loop actually started, materials / resources assigned before their properties are accessed (a type assertion is not a runtime assignment), and input picking wired to the same coordinate space the meshes occupy.

## 2.3 Runnability Gate (Run BEFORE Checklist Verification)

Before applying the checklist (§1.2), do a holistic, **cross-file** code-sanity check using `{user_prompt}` (§1.1) as the intent reference for what the project is supposed to be. The goal is to detect defects that would prevent the 3D game from booting / mounting `<Canvas>` / populating the scene / starting the per-frame loop — these gate everything else, because if the code crashes on startup or the scene never renders, every per-feature judgment downstream is moot. Reading files in isolation is not enough; trace `import` resolution, provider wiring, R3F `<Canvas>` setup, and per-frame loop registration across the whole project.

### Verified Build Status (authoritative — read BEFORE judging runnability)

{build_status}

### Defects that fail the gate

Walk through the project as if you were about to `npm install && npm run dev`. Any **one** of the following, confirmed in the code, is a gate failure:

1. **Entry / mount broken** — `index.html` is absent or has no root element matching the mount selector; `index.tsx` / `main.tsx` is missing, does not call `createRoot(...).render(<App />)` (or legacy `ReactDOM.render`), or mounts a component that is not exported / not importable; the project depends on React 19+ (per `package.json`) yet still calls `ReactDOM.render`, which React 19 removed. On React 18 `ReactDOM.render` is only deprecated (console warning) and still mounts — do **not** fail the gate for it there.
2. **R3F `<Canvas>` never rendered** — the app component tree contains no `<Canvas>` from `@react-three/fiber`, or the `<Canvas>` is conditionally rendered behind a flag that is never set true on first render, or only a manual three.js renderer is created (`new THREE.WebGLRenderer()`) but its `renderer.domElement` is never appended to the DOM. (A `<Canvas>` rendered with a truly empty scene is **not** a gate failure on its own — that surfaces in Rule 5 / §3.3; a *missing* `<Canvas>` is.) When the checklist permits a different engine (§2.2), the gate instead requires that engine's equivalent bootstrap — a mounted canvas, engine + scene constructed on the boot path, and the render loop actually started; any of these missing fails the gate, but do NOT fail such a project merely for lacking an R3F `<Canvas>`.
3. **Unresolved cross-file imports** — `import` references a name not exported from the target file (named-vs-default mismatch counts), or references a file that does not exist in the listed source set / a package not in `package.json` (e.g. importing `@react-three/rapier` when it is not declared as a dependency). Path aliases declared in `tsconfig.json` / `vite.config.ts` that do not actually map to a real directory also count.
4. **Missing provider / store wiring** — `useFrame` / `useThree` / `useGLTF` called outside any `<Canvas>` subtree; `useRapier` / `<RigidBody>` rendered outside `<Physics>`; `useKeyboardControls` consumed without a `<KeyboardControls>` ancestor; `useContext` / `useSelector` / `useDispatch` / `useStore` / Zustand / Jotai / Redux / Recoil consumers exist without the matching provider in the render tree above them, or a store is consumed but is never created and exported anywhere.
5. **Rules-of-hooks violations** — hooks called conditionally, in loops, after early `return`, or outside of components / custom hooks in a way that would throw on render.
6. **Guaranteed render-time crash** — `null` / `undefined` dereference in JSX or in a `useFrame` body on the first-render path (`mesh.current.position.x` when the ref is still `null` on initial mount; `obj.x` when `obj` is `undefined` on initial state), `.map` on a non-array initial state, throw in component body, `useEffect` with a broken dependency array that causes an infinite re-render or setState loop on mount, `useGLTF` / `useTexture` / `useLoader` of a path that — after the Vite `public/` mapping described in §1.5 — is genuinely absent from the §1.5 file manifest and has no error boundary (the loader rejects, the rejection propagates as a render error, and React unmounts the root). A missing `<Suspense>` boundary by itself is **NOT** a gate failure: R3F's `<Canvas>` provides one and React 18+ tolerates root-level suspension (see §2.1 Rule 5). This also covers **engine-object property access whose assignment never happens on the boot path** — e.g. accessing a mesh's material property when no material was ever assigned (a type assertion is not a runtime assignment), or reading a scene node before its creation call runs. Trace every startup-critical property access back to a dominating constructor / assignment; if a first-frame exception is unavoidable (black screen on boot), the gate fails.
7. **Per-frame loop never starts** — every `useFrame` callback body is empty (no state mutation, no `mesh.current.position.x +=`); `useFrame` is defined in a component that is never rendered into the `<Canvas>` subtree; a manual `requestAnimationFrame` is defined but never invoked; the ticker is started inside the render phase causing a re-render storm; `useEffect` returns the tick function (treating it as the cleanup callback) instead of starting it.
8. **3D engine never instantiated where required** — the brief requires a 3D scene (which is always the case for this category): no `<Canvas>`, no manual `new THREE.WebGLRenderer()` + render-loop fallback, and no equivalent bootstrap of a checklist-permitted alternative engine; or a renderer / scene is created but no camera is added to it (and any default camera is also disabled), leaving an unrenderable scene.
9. **Stage-blocking syntax / typing defect visible in the source** — unclosed JSX tags, mismatched braces in a top-level module, `await` in non-async function at module scope, etc., that any build would refuse.

### What is NOT a gate failure

Do not fail the gate for problems that merely degrade gameplay but do not prevent the game from running:

- Missing features that appear in `{checklist}` → handled by Rule 7 (checklist verification), not the gate.
- Wrong numerics / balance / AI behavior / level difficulty / physics constants → handled by §3 dimension scoring.
- Missing audio / SFX / particles / juice / post-processing → handled by §3.4 Feedback & Juice.
- Cosmetic / styling / lint / console-warning issues; missing shadow casting / receiving flags on individual meshes.
- Features that *exist* but feel unfinished → the corresponding checklist item fails (`"0, <reason>"`), but the gate still passes.
- Crashes that only occur deep in gameplay (e.g. AI enters an unreachable state after 10 minutes of play; physics jitter after 1000 rigid bodies spawn) — these belong to the AI / physics / gameplay dimensions, not the gate.
- A `<Canvas>` that renders but the scene contains only a placeholder `<mesh>` — surface this as a §3.3 critique, not a gate failure.

### Consequence of gate failure

When the gate fails:

- **Every checklist item** in the JSON output is set to `"0, 代码无法运行：<具体阻断点>"` — using each item's original verbatim Chinese wording as the key.
- **Both auxiliary dimensions** are set to `"0;代码无法运行，无法评估"` — i.e. `"关卡/场景/游戏数值"` and `"反馈与 Juice(打击感/音效/粒子)"`.
- **`total_score`** is `"0/<checklist 总条目数>"`.
- The blocking defect must be stated **in Chinese** with file path + symbol + a one-line cause. Example reason text: `代码无法运行：src/main.tsx 第 8 行 createRoot 引用的 <App /> 在 src/App.tsx 中并未导出，import 解析失败，应用无法挂载。` 或 `代码无法运行：src/App.tsx 整个组件树未渲染 @react-three/fiber 的 <Canvas>，3D 场景永远不会被初始化。`
- **Skip Stage B entirely** (do not run per-checklist verification, do not award partial credit for any feature whose code happens to look correct in isolation when the project as a whole cannot start).
- It is acceptable for all checklist items and both auxiliary dimensions to share the same blocking-defect citation in their reason text; you do not need to invent independent paragraphs.

## 2.4 Deep Static-Verification Requirements (Apply to EVERY Stage B Verdict)

These requirements exist because the most common judging error is awarding a pass on **surface evidence** — a matching constant, a well-named identifier, an isolated function — without proving the behavior is reachable, actually executed, and observable by the player. Apply every applicable requirement to each checklist item; when one is violated on the item's causal path, the item scores `"0, <中文原因>"` and the reason states which requirement failed.

**Scope discipline:** a violation fails an item only when it lies on that item's **causal path** — the code the item's observable behavior actually depends on. Off-path defects (an unreachable duplicate branch beside a reachable correct one, an unconsumed config field shadowed by a correct hardcoded value on the executing path, dead code the shipped game never touches) are cited as 潜在风险 in the reason without changing the score. Never let a risk-note soften a genuine causal-path violation into a pass. The same evidence standards also govern what you cite when scoring §3.3 / §3.4.

1. **Definition + consumption.** Evidence for any numeric or behavioral requirement must include both where the value / logic is defined AND where the executing control flow consumes it. Config / schema fields never read at runtime, helpers with no caller, formulas inside unreachable branches, styles / assets nothing applies, and matching string literals are not implementation.

2. **Reachability precedes credit.** Prove the state in which the feature fires is reachable in normal play:
   - *Input chain* — trace the real gesture (click / touch / key) through every coordinate transform to the state-mutating handler. Drawn geometry and hit-test geometry must share the same coordinate space; overlays must not swallow input; an invisible or misplaced hotspot, or an early-return that clears a selection before the command branch runs, makes every downstream feature unreachable. Confirm entry-point UI actually falls inside representative desktop and mobile viewports with a registered hit target.
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

1. **Trace across the whole project.** Start from the most likely entry (component / `<Canvas>` subtree / store action / hook / config) and follow the control flow through every file the item depends on. Reading any single file in isolation is **not** sufficient — the feature must work as part of the running project, wired into the render tree and / or the per-frame loop.
2. **Verify completeness and logical correctness.** The feature must be wired into the actual execution path (not just declared / typed / imported / JSX-defined-but-never-rendered), free of obvious logical bugs that would produce wrong behavior (e.g. acceleration applied with the wrong sign, AABB built from world position but applied as local, rapier impulse applied to a body whose rotations are locked, raycast direction not normalized), and consistent with the rest of the project (no contradicting state, no orphan handler, no broken cross-module assumption).
3. **Apply the category rules from §2.1 Rule 7** — positive feature requires runnable code; tech / asset constraint must match exactly; negative constraint requires verifiable absence; composite items joined by `+` require every sub-feature to pass independently.
4. **Apply the deep static-verification requirements from §2.4.** In particular: a matching constant without a consumption site, an unreachable prerequisite state (including default-AI liveness collapse), a dead branch, an internal mutation that never reaches the rendered HUD / scene (including the mutable-store / same-reference React re-render trap), a non-atomic failure path, or a rule fixed in only one of two parallel implementations all mean the item fails **when the violation lies on the item's causal path** (§2.4 scope discipline) — regardless of how correct the isolated fragment looks. Off-path defects are cited as 潜在风险 in the reason without changing the score. State which §2.4 requirement was violated in the reason text.

### Per-item scoring (binary)

Each checklist item receives a binary score in the output. **All values follow the unified `"<score>, <reason>"` format** — the trailing `, ` is kept even when the score is `1` so every checklist value parses the same way:

- **`"1, "`** — fully implemented and logically correct end-to-end across the project. Reason is intentionally empty (`1` plus comma plus space), which is the literal pass marker. Partial implementations, near-misses, broken wiring, or items implemented only via comments / dead code / never-invoked functions / never-rendered JSX / type-only declarations **do not earn `"1, "`**.
- **`"0, <中文原因>"`** — missing, partial, incorrect, or wired in a way that would not actually work. The reason **must** be written in Chinese and must include: file relative path + function / hook / reducer / R3F component / scene-graph node / config key (and line range when useful) + a one-line cause. If the item is a negative constraint that has been violated, explicitly name the forbidden subsystem found in the code.

There is **no halfway numeric** at the item level — the project either implements the feature correctly or it does not. Surface "almost there" implementations through the `0` reason text, not through a partial score.

### `total_score`

After scoring every checklist item, compute:

```
total_score = "<得 1 分的条目数>/<checklist 总条目数>"
```

Express it as a **fraction string** (e.g. `"8/10"`) — not a decimal, percentage, or aggregate float. The two auxiliary dimensions do **not** enter `total_score`.

## 3.3 Auxiliary Dimension — 关卡 / 场景 / 游戏数值

Scored on **0–5**, independent of the checklist. This dimension captures the overall design quality of the level / 3D scene / numeric system — aspects the checklist may not enumerate item by item, **including 3D-specific scene-composition decisions (camera setup, lighting, scene populating, physics tuning) that materially affect whether the game feels like a coherent 3D experience**.

**What to check:**

- **Levels / scenes** — number of levels / scenes; level config files (JSON / TS); per-level parameters (tower height, arena radius, enemy counts, wave timings, checkpoint placement).
- **3D scene composition** — meshes / lights / cameras present and parameterized sensibly; whether the scene feels "populated" (props, environment, terrain) or empty / placeholder; use of instancing for repeated geometry; appropriate camera type (`PerspectiveCamera` vs `OrthographicCamera`) and parameters (fov, position, lookAt, near / far).
- **Lighting & shadows** — at least an `ambientLight` + a directional / point light when the scene calls for it; shadow casting / receiving configured on relevant meshes; environment map / HDRI when appropriate.
- **Difficulty curve** — should be monotonically non-decreasing unless the brief explicitly says otherwise (enemy density, tower height, AI aggression, obstacle complexity).
- **Numerical balance** — damage, speed, HP, jump height, gravity, restitution, friction, drop rate, spawn rate, cooldown, stamina drain, AI reaction time.
- **Physics tuning** — gravity, world step rate, collider sizes vs visual mesh sizes, restitution / friction realistic for the gameplay.
- **Scene-transition correctness** — does state (HP / score / inventory / upgrades / checkpoint) persist or reset across transitions as the brief requires?
- **Save / checkpoint logic** if the brief requires it.

**Scoring rubric (0–5):**

- **5** — full design; multiple levels / scenes; clear, sensible difficulty curve; numerics balanced and tunable from config; 3D scene composed with thoughtful camera / lighting / instancing; physics constants tuned for the gameplay; state preservation across transitions is correct.
- **4** — solid implementation with one or two minor imbalances, rough transitions, or scene-composition gaps.
- **3** — basic level / numeric / scene structure exists but with noticeable issues (one level too easy / hard, hard-coded numerics with poor values, scene feels under-populated, only one light, transitions lose some state).
- **2** — minimal scaffolding only; balance clearly off; scene is essentially a placeholder cube on a plane; multiple state-loss bugs across transitions.
- **1** — level / scene / numeric system exists in code but is broken (transitions reset everything, only one level, numerics nonsensical, later level strictly easier than earlier, no lights so scene renders black, physics constants cause objects to fall through floor).
- **0** — entirely missing where the brief required it, or genre has no analogous design layer (explain in reason).

**3D-specific hard caps (apply after picking a rubric tier):**

- **Lighting** — scene has zero lights of any kind (no `ambientLight` / `hemisphereLight` / `directionalLight` / `pointLight` / `spotLight` / drei `<Environment>`): cap at `1`. Only a single light source for an outdoor / multi-room scene that obviously needs key + fill: cap at `3`.
- **Scene composition** — the entire scene is a single primitive on a ground plane (one `<mesh>` + `<planeGeometry>`) when the brief explicitly described a populated environment (擂台 / 工厂 / 迷宫 / 维多利亚书房 / 战场 etc.): cap at `2`.
- **Instancing budget** — the brief implies large repeated geometry (≥20 same-mesh instances such as 25 层 × 6–10 扇区的圆柱塔 / 10 波怪物 / 100×100 方块世界 / 程序化障碍组合) and the code uses individual `<mesh>` declarations or `.map(() => <Mesh/>)` instead of `<Instances>` / `<InstancedMesh>` / drei `<Merged>`: cap at `4` (this hurts perf and discipline, not correctness).
- **Color space** — color textures assigned to PBR materials without `texture.colorSpace = SRGBColorSpace` (and no Canvas-level color-space override): cap at `3` (already cross-listed in §2.1 Rule 5).
- **Shadow trio incomplete** when brief required shadows: cap at `3` (already cross-listed in §2.1 Rule 5).
- **Physics step coupling** — `<Physics>` exists but its timestep is implicitly frame-coupled (no `timeStep` prop / no fixed sub-step) AND the brief involves competitive timing (FPS / 格斗 / 跑酷 / 保龄球): cap at `4`.

**If the game's genre does not have a traditional level / scene / numeric layer** (endless runner with one infinite procedurally generated scene, sandbox creative mode, single-room escape, single-arena 1v3 deathmatch, etc.), evaluate the **equivalent design layer** for that genre (difficulty ramp over time, procedural-generation quality, single-scene numeric balance, puzzle progression) on the same 0–5 scale, and in the reason name the equivalent concept you scored. If the genre genuinely has no analogous design layer at all, score `0` and explain why this dimension does not apply.

**Value format in the JSON:** `"<0-5>;<中文打分说明，引用代码证据：文件路径 + 函数 / 符号 / R3F 组件 + 必要时行号>"`.

## 3.4 Auxiliary Dimension — 反馈与 Juice (打击感 / 音效 / 粒子)

Scored on **0–5**, independent of the checklist. This dimension captures audiovisual feedback richness — the "game feel" / juice that the checklist may not enumerate exhaustively. **For 3D games, the bar is higher: camera shake, hitstop, knockback physics, post-processing effects, 3D positional audio, and particle systems are all in scope.**

**What to check:**

- **Hit feedback** — camera shake (camera position perturbation in `useFrame`), hitstop (time-scale freeze / `useFrame` skip for 80–120ms), knockback (rapier impulse / velocity bump on the hit body), red flash on victim (emissive pulse / material color tween), floating damage numbers (drei `<Html>` or sprites), FOV pulse on impact.
- **Input feedback** — button press / touch animation on the on-screen joystick / buttons, visual response on key press (player squash / lean), cursor / crosshair animation on FPS aim.
- **Audio** — SFX on hit / jump / pickup / shoot / level-up / UI; BGM loop; 3D positional audio (drei `<PositionalAudio>` / three.js `PositionalAudio`); volume mixing; first-interaction unlock for iOS Safari.
- **Particles** — hit sparks, explosion debris, dust on landing, magic trails, ambient effects; via three.js `Points` / `Sprite` / `InstancedMesh` / drei `<Sparkles>` / dedicated particle libraries.
- **Post-processing** — bloom on emissive surfaces, vignette, chromatic aberration on damage, depth-of-field for menus, motion blur on dash, noise on low HP.
- **UI animation** — score pop-up, HP bar tween, level-up flash, scene transitions, wave-incoming alert.
- **Consistency** — every core action should have *some* feedback (visual + audio when meaningful); a core action with zero feedback is a noticeable defect.

**Scoring rubric (0–5):**

- **5** — every core action has both visual *and* audio feedback; camera shake / hitstop / knockback / particles / post-processing / UI animations cohere; no obvious silent or visually flat interaction; 3D positional audio used where it adds value.
- **4** — most actions have both visual and audio feedback with one or two gaps (e.g. hitstop missing, or post-processing missing but shake + particles present).
- **3** — basic visual or audio feedback present for the most important actions; juice is sparse but functional (one camera shake, simple particle, basic SFX).
- **2** — minimal feedback; multiple core actions are silent or visually flat; no camera shake or hitstop where the brief explicitly required them.
- **1** — almost no feedback; the game looks and sounds like a wireframe; hits produce zero visual or audio change.
- **0** — no feedback layer at all where the brief required it; no SFX whatsoever when the brief required audio.

**3D-specific hard caps (apply after picking a rubric tier):**

- **Camera shake** — brief explicitly mentions 屏震 / camera shake / 抖动 but no camera-perturbation code exists (no `camera.position.x += ...` / shake util / drei `<CameraShake>`): cap at `2`.
- **Hitstop / 顿帧** — brief explicitly mentions 顿帧 / hitstop / freeze frame (often with a duration like `80ms`) but no time-scale freeze / `useFrame` skip / `delta = 0` clamp on hit exists: cap at `3`.
- **Knockback physics** — brief explicitly mentions 击飞 / 击退 / knockback / launch but no rapier impulse / velocity bump / `applyImpulse` / `setLinvel` is called on hit: cap at `2`.
- **Post-processing** — brief explicitly mentions bloom / 辉光 / 后处理 / vignette / chromatic aberration / 色散 but no `<EffectComposer>` or equivalent is mounted: cap at `3`.
- **3D positional audio** — brief explicitly mentions 3D 音效 / 立体声 / positional / 空间音效 but only flat `<audio>` / `Howler` / `new Audio()` is used (no drei `<PositionalAudio>` / three.js `PositionalAudio`): cap at `3`.
- **Particles** — brief explicitly mentions 粒子 / particle / 火花 / 爆炸 but no `Points` / `Sprite` / `InstancedMesh` / drei `<Sparkles>` / `<Trail>` / particle library is rendered: cap at `2`.
- **Mobile audio unlock** — brief requires audio AND the project is H5 / 移动端 but no tap-to-start / first-interaction `AudioContext.resume()` gate exists: cap at `2` (cross-listed with §2.1 Rule 6).

**If the game's genre legitimately has minimal juice** (turn-based card battle, pure logic puzzle with no animated state, etc.), evaluate the **genre-appropriate feedback** (card flip animation, focus-state animation, transition smoothness, button press cue) on the same 0–5 scale; in the reason, name the equivalent feedback layer you scored.

**Value format in the JSON:** `"<0-5>;<中文打分说明，引用代码证据：文件路径 + 函数 / 符号 / R3F 组件 + 必要时行号>"`.

---

# 4. Output Format

## 4.1 Format Example

The skeleton below uses `<...>` placeholders — in the real output, use each `{checklist}` item's **original verbatim Chinese wording** as its JSON key (one entry per item, in the same order as the input array):

```json
{{
    "关卡/场景/游戏数值": "<0-5>;<中文打分说明：覆盖关卡数 / 难度曲线 / 数值平衡 / 3D 场景组合（摄像机、光照、实例化）/ 物理调参 / 场景切换 / 状态保持，引用代码证据：文件路径 + 函数 / 符号 / R3F 组件 + 必要时行号；若游戏类型不涉及关卡 / 场景，说明所评估的等效维度>",
    "反馈与 Juice(打击感/音效/粒子)": "<0-5>;<中文打分说明：覆盖打击感 / 屏震 / 顿帧 / 击飞物理 / 音效 / 粒子 / 后处理 / UI 动效的完备程度，引用代码证据：文件路径 + 函数 / 符号 / R3F 组件 + 必要时行号；若游戏类型本身缺乏 juice 概念，说明所评估的等效反馈层>",
    "<checklist 条目 1 原文>": "1, ",
    "<checklist 条目 2 原文>": "0, <中文说明：文件路径 + 函数 / 符号 / R3F 组件 + 一句因果>",
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
   - `"0, <Chinese reason>"` — not implemented / partial / broken; or (for negative constraints) violated. Reason must cite file path + function / hook / reducer / R3F component / scene-graph node / config key + one-line cause.
4. **Auxiliary-dimension value format:** `"<0-5>;<Chinese reason>"` — a single integer 0–5, then a `;`, then the reason text. The integer comes first; do not invert the order.
5. **`total_score` is a fraction string** like `"8/10"` — never a decimal, percentage, or aggregate float. The two auxiliary dimensions do **not** enter `total_score`.
6. **If the Runnability Gate (§2.3) fails**, every checklist item is `"0, 代码无法运行：<具体阻断点>"`, both auxiliary dimensions are `"0;代码无法运行，无法评估"`, and `total_score` is `"0/<checklist 总条目数>"`.
7. Output **only** the JSON object — no markdown fences, no preamble, no commentary outside the JSON.

---

# 5. Constraint

Format: Only print the result in JSON format as shown in **Output Format** (§4). Do not output any extra prose outside the JSON object — no markdown code fences, no commentary, no leading or trailing text. Every reason text inside the JSON values must be written in **Chinese** and must cite concrete evidence — file relative path + function / hook / reducer / R3F component / scene-graph node / config-key name (and line range when useful) from `{source_code}`. Use each `{checklist}` item's **original verbatim Chinese wording** as its JSON key; do not paraphrase, translate, abbreviate, reorder, or merge items.

---

# 6. Action

Follow the instructions above and evaluate the provided React H5 3D game strictly against `{user_prompt}` (the requirement), `{checklist}` (the explicit feature verification list — the primary verification driver), and `{source_code}` (the source — read it line by line). Produce the JSON output that satisfies the **Constraint**.
"""

class Eval3DScenario:
    """Run the 3D static-code evaluation prompt against an agent-generated project."""

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
            THREE_D_EVALUATION_PROMPT, base_info, output_file_path,
            project_root=_PROJECT_ROOT,
        )


if __name__ == "__main__":
   base_info = {
    "task_id": "3D_3d_action_L1_001",
    "category": "3D动作格斗",
    "desc": "3D 竞技场格斗 Demo（类似 Roblox Strongest Battlegrounds 单局）",
    "agent_ability": [
      "C1",
      "C2",
      "C3",
      "C4",
      "C6",
      "C7"
    ],
    "prompt": "做一个 3D 竞技场格斗 Demo，参考 Roblox《The Strongest Battlegrounds》极简版。React + three.js + @react-three/fiber + ecctrl（角色控制器）。 【场景】一张 20×20m 的圆形擂台，四周是虚空；摄像机第三人称追尾。 【对战】 - 玩家 vs 3 个 AI bot（同在擂台上），最后存活者胜 - WASD 移动 + Space 跳 + Shift 冲刺（有 0.3s 无敌帧，cd 2s） - 左键轻拳（连击 3 段，第 3 段击飞）、右键重拳（蓄力 0.5s 后命中可破防）、Q 格挡（持续消耗耐力）、E 闪现 3m - 耐力 100，冲刺 / 格挡 / 重拳消耗；空闲 1s 后每秒回 20 - 每人 HP 200，被推下擂台或 HP 归零失败 【AI】 - 3 档 AI：近距离缠斗优先、远距离闪现贴近、被连击时优先格挡+反击 - 全程动态难度：连杀越多 AI 越激进 【反馈】 - 命中要有击飞物理（被击者受击向后 1-3m，根据招式）、屏震、顿帧 80ms、粒子 - 擂台边缘 1m 内显示红色警示圈 【限制】 - 不要写成简单挥刀打木桩；不要无敌作弊；画布全屏；移动端需要虚拟摇杆 + 右侧 4 个按钮（拳/重/闪/格）",
    "level": "L1",
    "label": [
      "type:3d_action",
      "with_attachment(7)"
    ],
    "attachment": [
      "logo_game.png",
      "scene_castle.glb",
      "boss_animated.glb",
      "ambience_wind.mp3",
      "bgm_menu.mp3",
      "enemy_animated.glb",
      "sfx_death.mp3"
    ],
    "result_verify": "",
    "checklist": [
      "4 招式（轻/重/闪/格）",
      "不要写成打木桩",
      "闪现 3m",
      "擂台 20×20m",
      "耐力系统",
      "擂台 1v3 AI 最后存活",
      "击飞物理 + 边缘推下取胜",
      "不要无敌作弊",
      "React + three.js + r3f + ecctrl",
      "冲刺无敌 0.3s cd 2s"
    ],
    "notes": "scenario=3D | game_type=3d_action | level=L1 | 合成 case"
  }
   output_file_path = "result/3D_benchmark_easy/3D_3d_action_L1_001"

   result = Eval3DScenario().eval(base_info, output_file_path)
   print(json.dumps(result, ensure_ascii=False, indent=2))
