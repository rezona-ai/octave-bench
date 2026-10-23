# OCTAVE

**A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation**

[网站](https://rezona-ai.github.io/benchmark-site/) · [数据集（Hugging Face）](https://huggingface.co/datasets/rezonalab/game-benchmark) · [English](README.md) · [数据集说明](data/README.md) · [结果](results/README.md) · [复现](docs/reproduce.md)

OCTAVE 是面向编程 agent（Claude Code、Codex CLI 等）的 HTML5 游戏生成 benchmark，共 180 道题。每道题用 6 条公开的 **Completeness** 要求和 4 条隐藏的 **Richness** 要求检查，每条要求标注能力维度 C1–C8。详见论文。

## 排行榜（v1）

12 个模型–harness 组合 × 180 题，判官 `gpt-6-astra`，按 Completeness 排序。

| # | 模型 | Harness | Completeness % | Richness % | 门槛标记 % |
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

† 判官与被测模型为同一模型。分能力、分切片结果见 [`results/`](results/README.md)。

## 快速开始

```bash
git clone https://github.com/rezona-ai/octave-bench.git && cd octave-bench
pip install -r requirements.txt

# 1. 查看题目
python3 -c "import json; c=[json.loads(l) for l in open('data/octave_180_zh.jsonl')]; print(len(c), c[0]['prompt'][:200])"

# 2. 用公开的判分结果复算排行榜（不需要 API key）
python3 scoring/leaderboard.py

# 3. 用一个 agent 生成几道题，再判分（需要 API key，见 docs/reproduce.md）
python3 harness/run_bench.py run --models cc_opus_5 --cases data/octave_180_zh.jsonl --limit 3
python3 eval/run_eval.py --runs $HOME/bench/runs --cases data/octave_180_zh.jsonl --models cc_opus_5 --limit 3
```

目录结构见 [README.md](README.md)，题目字段见[数据集说明](data/README.md)。

## 许可证

代码：[MIT](LICENSE)；`data/` 中的题目：[CC BY 4.0](data/LICENSE)；第三方声明见 [NOTICE.md](NOTICE.md)。

## 引用

见 [README.md](README.md#citation) 或 [`CITATION.cff`](CITATION.cff)。
