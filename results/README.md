# Results (v1, judge: gpt-6-astra)

12 model–harness pairs × 180 tasks = 2,160 attempts, 21,600 judged requirements. Rebuild the derived files with
`python scoring/leaderboard.py`.

| File | Rows | Content |
|---|---|---|
| `leaderboard.csv` / `leaderboard.md` | 12 | One row per pair: Completeness, Richness, gate flag rate, C1–C8 |
| `breakdowns.json` | — | The same metrics by capability × requirement type, requirement difficulty, track, platform, render, category, judge batch |
| `case_scores.csv` | 2,160 | One row per attempt |
| `item_scores.csv.gz` | 21,600 | One row per judged requirement, with the judge's reason |
| `generation.csv` | 2,160 | Agent status, wall time, tokens, cost |

* **Completeness / Richness**: share of the 6 public / 4 hidden requirements passed. Every attempt counts; missing
  artifacts score 0.
* **Gate flag rate**: attempts flagged by the judge's runnability gate, plus missing artifacts. Flagged attempts keep
  their judgments.
* **C1–C8**: pass rate over all 10 requirements, grouped by primary capability.

Columns:

* `case_scores.csv`: `model, model_name, task_id, judge_batch, track, platform, render, category, subtype, incentive,
  level, completeness_passed, completeness_total, completeness, richness_passed, richness_total, richness, gate_flag,
  artifact_present, aux_levels, aux_juice` (the two `aux_*` 0–5 ratings are not used in any score)
* `item_scores.csv.gz`: `model, task_id, kind, item_index, passed, primary_capability, capabilities, difficulty, reason`
* `generation.csv`: `model, task_id, judge_batch, gen_status, wall_min, in_tok, out_tok, cache_read_tok,
  cache_write_tok, cost_usd, turns`

`judge_batch` is `PC-75` (main / web), `Mobile-75` (main / mobile) or `Final-30` (expert + repro); judge settings
per batch are in [`docs/reproduce.md`](../docs/reproduce.md#the-v1-judge). GLM prices were not captured, so their
cost is empty.
