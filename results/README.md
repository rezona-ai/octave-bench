# Results (v1, judge: gpt-6-astra)

Judge results for 12 model–harness pairs on the 180 tasks in [`data/`](../data): 2,160 attempts, one per pair and
task, and 21,600 judged requirements. Every number in the paper's leaderboard can be recomputed with:

```bash
python scoring/leaderboard.py     # rewrites leaderboard.csv, leaderboard.md and breakdowns.json from the two score files
python scoring/paper_numbers.py   # recomputes the paper's tables and figures and checks each number
```

| File | Rows | Content |
|---|---|---|
| `leaderboard.csv` / `leaderboard.md` | 12 | One row per model–harness pair, ranked by Completeness, with C1–C8 scores |
| `breakdowns.json` | — | Overall figures, the leaderboard, capability scores split by requirement type (Figure 4), pass rates by requirement difficulty (Table G.1), and the same metrics sliced by track, platform, render, task level, category, incentive and judge batch |
| `case_scores.csv` | 2,160 | One row per attempt (model × task) |
| `item_scores.csv.gz` | 21,600 | One row per judged requirement (6 Completeness + 4 Richness per task), with the judge's reason |
| `generation.csv` | 2,160 | Generation side per attempt: agent status, wall time, tokens, cost (USD) |

## Metrics

* **Completeness** (ranking metric): share of the 6 public requirements passed, averaged over tasks.
* **Richness**: share of the 4 hidden requirements passed, averaged over tasks.
* **Gate flag rate**: share of attempts flagged by the judge's runnability gate (entry files, imports, execution
  path, platform and render checks), plus the 2 attempts with no artifact. For PC player tasks the judge's public
  gate marker is used; for Mobile and expert / reconstruction tasks an attempt is flagged when it passes no
  Completeness requirement and at least one Completeness reason says the code cannot run (`无法运行`). This gives
  452 gate failures and 2 missing artifacts, 454 / 2,160 = 21.0%. Gate flags are diagnostic: flagged
  attempts keep their raw judgments, and missing artifacts score zero. No attempt is removed. In v1 all 454 flagged
  attempts fail every Completeness requirement, while 89 of them (Mobile-75 and Final-30, where hidden requirements
  were judged in the same call) still pass some Richness requirements.
* **C1–C8**: pass rate over all 10 requirements, grouped by each requirement's **primary capability** (the first
  code in its capability list).
* **Requirement difficulty**: pass rate within each of the four equal strata of 450 requirements (`difficulty` in
  `item_scores.csv.gz`, cut from the requirement score `ads`; see the [dataset card](../data/README.md#difficulty)).
* **aux_levels / aux_juice** (in `case_scores.csv`): the judge's two auxiliary 0–5 ratings (level design and game
  feel). Not used in any ranking.

Over all attempts: Completeness 32.2%, Richness 33.5%, gate flags 21.0%.

## Columns

`case_scores.csv`: `model, model_name, task_id, judge_batch, track, platform, render, category, subtype, incentive,
level, completeness_passed, completeness_total, completeness, richness_passed, richness_total, richness, gate_flag,
artifact_present, aux_levels, aux_juice`

`item_scores.csv.gz`: `model, task_id, kind (completeness|richness), item_index (0-based position in completeness_requirements /
richness_requirements), passed (0|1), primary_capability, capabilities (C-codes, "|"-separated, primary first),
difficulty (easy|medium|hard|extreme), ads (requirement difficulty score), reason`

`generation.csv`: `model, task_id, judge_batch, gen_status (success|timeout|no_dist|no_project|agent_error|refusal),
wall_min, in_tok, out_tok, cache_read_tok, cache_write_tok, cost_usd, turns`

## How the results were produced

* **Generation**: each model ran inside its harness (Claude Code or Codex CLI, see `configs/models.json`) with a
  120-minute limit per task. Prompt language: Chinese for the PC-75 and Final-30 batches; for Mobile-75, an English
  variant with an extra `[Mobile]` section. Costs are recomputed from token usage with the prices in
  [`docs/PRICING.md`](../docs/PRICING.md).
* **Judging**: `gpt-6-astra` reads the generated project's source and fills the rubric in `llm-eval/` (2D / 3D ×
  web / mobile, picked from the task's `render` and `platform`). Settings per batch are in
  [`docs/reproduce.md`](../docs/reproduce.md#the-v1-judge).
* **Judge batches** (`judge_batch`): `PC-75` (main / web), `Mobile-75` (main / mobile), `Final-30` (expert +
  repro). Average pass rates differ a lot across batches (PC-75 is the hardest), so compare models within a batch
  when in doubt.
* **Expert tasks** were judged against their full original checklists (11–32 items). The scores here are recomputed
  on the released 6 + 4 requirements, which were selected before judging and match the judged items verbatim.

## Known issues

* **Same-model evaluation.** The judge `gpt-6-astra` is also the top-ranked model (marked †). Without it, overall
  Completeness is 29.9% and Richness 32.1%.
* **Strict judge.** In the human cross-check, humans judged 76.3% of 266 judgeable requirements satisfied, against
  the judge's 46.2% pass rate, see [`docs/human_eval.md`](../docs/human_eval.md).
* **GLM pricing.** GLM-5.2 / GLM-5.3 have no captured unit price, so their cost columns are empty. Fable 5.1 is
  priced as Fable 5.
