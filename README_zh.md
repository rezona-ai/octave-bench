# OCTAVE

**A Capability-Resolved Benchmark for End-to-End HTML5 Game Generation**

[网站](https://rezona-ai.github.io/benchmark-site/) · [数据集（Hugging Face）](https://huggingface.co/datasets/rezonalab/game-benchmark) · [English](README.md) · [数据集说明](data/README.md) · [结果](results/README.md) · [复现](docs/reproduce.md)

**编程 agent 能否根据一份设计说明，做出一个完整可玩的游戏？** OCTAVE 包含 180 道 HTML5 游戏生成题。每道题把一份多系统耦合的游戏设计交给 Claude Code、Codex CLI 等 agent，再用 10 条要求检查生成的项目：6 条题面写明的公开 **Completeness** 要求，加 4 条隐藏的 **Richness** 要求，考察题面只隐含的深层关系、边界情况和跨系统耦合。全集共 1,800 条要求，每条都标注了它考察的能力维度（C1–C8）。

- **180 道题，分三个赛道**：
  - `main`：桌面 Web 75 道 + 移动端 75 道，由玩家的游戏需求改写扩写而来
  - `expert`：游戏设计师出的 10 道
  - `repro`：复刻现有商业游戏机制的 20 道
- **覆盖范围**：2D / 3D；6 个游戏大类；8 个能力维度，从核心规则、AI 行为到打击感与引导。
- **判分方式**：源码判官（`gpt-6-astra`）先检查入口文件、import 和执行路径（可运行门槛），再逐条判定通过或不通过并给出理由。门槛标记只作诊断：被标记的尝试保留原始判定，缺产物的记 0 分。
- **公开内容**：题目（英文 + 中文原文）、生成 harness、判官及 rubric、12 个模型–harness 组合的逐条判分结果，以及能复算全部排行榜数字的脚本。

## 排行榜（v1）

共 2,160 次尝试（12 个模型–harness 组合 × 180 题，每题一次），按 Completeness 排序。判官为 `gpt-6-astra`，每题时限 120 分钟。

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

† 判官与被测模型是同一个模型。全部尝试上，Completeness 为 32.2%，Richness 为 33.5%；21.0% 的尝试被门槛标记或没有产物。结果为固定样本的描述性统计，不含置信区间。

- **判官偏严**：在 266 条可判定要求的人工交叉核验中，人工判定满足的比例为 76.3%，判官通过率为 46.2%；分歧几乎都是人工认为满足、判官判为不通过（见 [`docs/human_eval.md`](docs/human_eval.md)）。
- 各能力维度（C1–C8）的分数，以及按赛道、平台、2D/3D、要求难度、类别的切片结果，见 [`results/`](results/README.md)。`python3 scoring/paper_numbers.py` 用公开文件复算论文中的各项表格与图中数字，并逐项核对。

## 快速开始

```bash
git clone https://github.com/rezona-ai/octave-bench.git && cd octave-bench
pip install -r requirements.txt

# 1. 查看题目
python3 -c "import json; c=[json.loads(l) for l in open('data/octave_180_zh.jsonl')]; print(len(c), c[0]['prompt'][:200])"

# 2. 用公开的判分结果复算排行榜，并核对论文中的每个数字（不需要 API key）
python3 scoring/leaderboard.py
python3 scoring/paper_numbers.py

# 3. 用一个 agent 生成几道题，再判分（需要 API key，见 docs/reproduce.md）
python3 harness/run_bench.py run --models cc_opus_5 --cases data/octave_180_zh.jsonl --limit 3
python3 eval/run_eval.py --runs $HOME/bench/runs --cases data/octave_180_zh.jsonl --models cc_opus_5 --limit 3
```

目录结构、题目字段和能力编号（C1 核心规则 / C2 AI 与 NPC / C3 数值设计 / C4 交互与输入 / C5 关卡与场景 / C6 动画与渲染 / C7 反馈与打击感 / C8 引导与元 UI）的完整说明见 [README.md](README.md) 和 [数据集说明](data/README.md)。每条要求的能力列表中，第一个编号是它的主能力。

## 许可证

代码（`data/` 以外的所有内容）采用 [MIT](LICENSE)，`data/` 中的题目采用 [CC BY 4.0](data/LICENSE)。repro 题中提到的游戏名称和商标归各自权利人所有，详见 [NOTICE.md](NOTICE.md)。

## 引用

BibTeX 见 [README.md](README.md#citation) 或 [`CITATION.cff`](CITATION.cff)。arXiv 编号在论文发布后补充。
