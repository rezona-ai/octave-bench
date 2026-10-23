# OCTAVE

**A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation**

[Website](https://rezona-ai.github.io/benchmark-site/) · [Dataset (Hugging Face)](https://huggingface.co/datasets/rezonalab/game-benchmark) · [中文](README_zh.md) · [Dataset card](data/README.md) · [Results](results/README.md) · [Reproduce](docs/reproduce.md)

OCTAVE is a benchmark of 180 HTML5 game-generation tasks for coding agents (Claude Code, Codex CLI, …). Each task is
checked against 6 public **Completeness** and 4 hidden **Richness** requirements, each tagged with capabilities
C1–C8. Details are in the paper.

## Leaderboard (v1)

12 model–harness pairs × 180 tasks, judged by `gpt-6-astra`, ranked by Completeness.

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

† The evaluator is the same model. Per-capability and per-slice results: [`results/`](results/README.md).

## Quick start

```bash
git clone https://github.com/rezona-ai/octave-bench.git && cd octave-bench
pip install -r requirements.txt

# 1. Look at the tasks
python3 -c "import json; c=[json.loads(l) for l in open('data/octave_180_en.jsonl')]; print(len(c), c[0]['prompt'][:300])"

# 2. Rebuild the leaderboard from the released judge results (no API key needed)
python3 scoring/leaderboard.py

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
scoring/      leaderboard.py (rebuild results/) · aggregate.py (score your own runs)
playground/   build_play.py — static "click to play" index over generated games
utils/        judge plumbing: template filling, verdict validation, source collection, judge API (gpt-6-astra / Claude)
configs/      model registry and prices, prompt templates, LiteLLM proxy config, keys.env.example
docs/         reproduce.md · PRICING.md
```

## Task format

One JSON object per line; fields are listed in the [dataset card](data/README.md).

## Secrets

No credentials are stored here; `configs/keys.env` and `.env` are git-ignored.

## License

Code: [MIT](LICENSE). Tasks in `data/`: [CC BY 4.0](data/LICENSE). Third-party notices: [NOTICE.md](NOTICE.md).

## Citation

```bibtex
@article{rezona2026octave,
  title  = {OCTAVE: A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation},
  author = {Li, Kehang and Xu, Xinlan and Jin, Yulin and Cao, Heng and Li, Xuchen and Ren, Houxian and Ji, Zihao and Luo, Qiang and Mao, Yadong and Zhang, Jian and Zhao, Jian and Wang, Zihao},
  year   = {2026}
}
```
