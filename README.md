# OCTAVE

**A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation**

[Website](https://rezona-ai.github.io/benchmark-site/) · [Dataset (Hugging Face)](https://huggingface.co/datasets/rezonalab/game-benchmark) · [中文](README_zh.md) · [Dataset card](data/README.md) · [Results](results/README.md) · [Reproduce](docs/reproduce.md)

**Can a coding agent build a complete, playable game from a design brief?** OCTAVE has 180 HTML5
game-generation tasks. Each task gives an agent such as Claude Code or Codex CLI a multi-system game design and
checks the built project against 10 requirements: 6 public **Completeness** requirements stated in the brief, and 4
hidden **Richness** requirements that probe deeper relationships, edge cases and cross-system coupling the brief
only implies. That is 1,800 requirements in total, each tagged with the capabilities (C1–C8) it tests.

* **180 tasks** in three tracks:
  * `main`: 75 desktop-web + 75 mobile tasks, rewritten from player game requests
  * `expert`: 10 tasks written by game designers
  * `repro`: 20 tasks that reconstruct the mechanics of existing commercial games
* **Coverage**: 2D and 3D; six game categories; eight capability dimensions, from core rules and AI behaviour to
  game feel and guidance.
* **Scoring**: a source-code judge (`gpt-6-astra`) checks entry files, imports and the execution path (the
  runnability gate), then marks each requirement pass or fail with a reason. Gate flags are diagnostic: flagged
  attempts keep their raw judgments, and missing artifacts score zero.
* **Released**: the tasks (English, plus the original Chinese), the generation harness, the judge and its rubrics,
  per-requirement judge results for 12 model–harness pairs, and the scripts that rebuild every leaderboard number.

## Leaderboard (v1)

All 2,160 attempts (12 model–harness pairs × 180 tasks, one attempt each), ranked by Completeness. Judge:
`gpt-6-astra`. Agents ran with a 120-minute limit per task.

| # | Model | Harness | Completeness % | Richness % | Gate flag % |
|---|---|---|---|---|---|
| 1 | GPT-6-astra † | Codex CLI | **57.1** | 49.3 | 13.3 |
| 2 | Fable 5.1 | Claude Code | **44.7** | 40.7 | 17.8 |
| 3 | Fable 5 | Claude Code | **39.0** | 39.3 | 21.1 |
| 4 | Opus 5 | Claude Code | **37.2** | 40.4 | 16.1 |
| 5 | GPT-5.6-sol | Codex CLI | **33.4** | 32.6 | 16.7 |
| 6 | GLM-5.3 | Claude Code | **31.1** | 34.0 | 21.7 |
| 7 | GPT-5.5 | Codex CLI | **26.9** | 28.3 | 15.6 |
| 8 | DeepSeek-V4.1-Flash | Claude Code | **25.9** | 28.9 | 20.6 |
| 9 | GLM-5.2 | Claude Code | **24.3** | 28.1 | 26.7 |
| 10 | DeepSeek-V4-Flash-0731 | Claude Code | **23.5** | 28.5 | 26.7 |
| 11 | DeepSeek-V4-Pro | Codex CLI | **22.2** | 27.5 | 22.8 |
| 12 | Seed evolving | Claude Code | **21.0** | 24.9 | 33.3 |

† The evaluator is the same model. Over all attempts, Completeness is 32.2% and Richness 33.5%; 21.0% of attempts
are gate-flagged or have no artifact. Fixed-sample descriptive results, no confidence intervals.

* **Strict judge.** In a human cross-check on 266 judgeable requirements, humans judged 76.3% satisfied while the
  judge passed 46.2%; almost all disagreements are requirements humans accepted and the judge failed (see
  [`docs/human_eval.md`](docs/human_eval.md)).
* Per-capability scores (C1–C8) and slices by track, platform, 2D/3D, requirement difficulty and category are in
  [`results/`](results/README.md). `python3 scoring/paper_numbers.py` recomputes the paper's tables and figures from
  the released files and checks each number.

## Quick start

```bash
git clone https://github.com/rezona-ai/octave-bench.git && cd octave-bench
pip install -r requirements.txt

# 1. Look at the tasks
python3 -c "import json; c=[json.loads(l) for l in open('data/octave_180_en.jsonl')]; print(len(c), c[0]['prompt'][:300])"

# 2. Rebuild the leaderboard from the released judge results, and check every number in the paper (no API key needed)
python3 scoring/leaderboard.py
python3 scoring/paper_numbers.py

# 3. Generate games for a few tasks with one agent, then judge them (needs API keys; see docs/reproduce.md)
python3 harness/run_bench.py run --models cc_opus_5 --cases data/octave_180_zh.jsonl --limit 3
python3 eval/run_eval.py --runs $HOME/bench/runs --cases data/octave_180_zh.jsonl --models cc_opus_5 --limit 3
```

## Repository layout

```
data/         octave_180_{en,zh}.jsonl — the 180 tasks (CC BY 4.0) · README.md dataset card
results/      leaderboard, per-attempt and per-requirement judge results, generation cost/time (v1)
harness/      run_bench.py — runs Claude Code / Codex CLI over the tasks, one isolated process per (model, task) · scripts/
llm-eval/     judge rubrics: {2D,3D}_eval.py (web), {2D,3D}_mobile_eval.py (mobile)
eval/         run_eval.py — batch judge over a runs directory
scoring/      leaderboard.py (rebuild results/) · paper_numbers.py (check the paper's numbers) · aggregate.py (score your own runs)
playground/   build_play.py — static "click to play" index over generated games
utils/        judge plumbing: template filling, verdict validation, source collection, judge API (gpt-6-astra / Claude)
configs/      model registry and prices, prompt templates, LiteLLM proxy config, keys.env.example
docs/         reproduce.md · human_eval.md · PRICING.md
```

## Task format

One JSON object per line. Abridged:

```json
{
  "task_id": "hard_action_rpg_3d_017",
  "track": "main", "platform": "web", "render": "3d", "category": "RPG", "level": "extreme",
  "prompt": "[Game] AI-Directed Dynamic Dungeon: an invisible director adjusts pressure ...",
  "completeness_requirements": ["Branch from the same seed ... the efficient branch actually encounters more enemies ...", "..."],
  "richness_requirements": ["From the same initial combat state, compare leaving the healer alive with killing it ...", "..."],
  "agent_ability": ["C1", "C2", "C3", "C5"],
  "completeness_requirement_capabilities": [["C5", "C2"], ...],
  "completeness_requirement_difficulty": ["hard", ...]
}
```

The first code in each `*_requirement_capabilities` entry is the requirement's primary capability. See the [dataset card](data/README.md) for
every field, the capability codes, and how difficulty levels were assigned.

## Secrets

No credential is stored in this repository. `configs/keys.env` and `.env` are git-ignored, and the committed
`*.example` files hold placeholders only. `run_bench.py` passes each vendor key to its agent process through the
environment and never writes it to disk or into transcripts.

## License

Code (everything outside `data/`) is released under the [MIT License](LICENSE). The benchmark tasks in `data/` are
released under [CC BY 4.0](data/LICENSE). Game titles referenced by `repro` tasks are trademarks of their respective
owners; see [NOTICE.md](NOTICE.md) for third-party notices and the attribution format.

## Citation

```bibtex
@article{rezona2026octave,
  title  = {OCTAVE: A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation},
  author = {Li, Kehang and Xu, Xinlan and Jin, Yulin and Cao, Heng and Li, Xuchen and Ren, Houxian and Ji, Zihao and Luo, Qiang and Mao, Yadong and Zhang, Jian and Zhao, Jian and Wang, Zihao},
  year   = {2026}
}
```

The arXiv identifier will be added on publication. See also [`CITATION.cff`](CITATION.cff).
