# Pricing used for cost recomputation

All costs in this repo are recomputed from per-call token usage (`usage` in each case's `meta.json`) with the
unit prices in `configs/models.json` → `price` (USD per 1M tokens: `input`, `output`, `cache_read`, `cache_write`).
`run_bench.py status` and `scoring/aggregate.py` both use this table. Claude Code's self-reported
`total_cost_usd` is kept in the CSV (`cc_reported_cost`) for reference only — it prices third-party endpoints
at Anthropic rates and is wrong for them.

| model_key | model id (API) | input | cache read | cache write | output | source / note |
|---|---|---|---|---|---|---|
| cc_opus_5 | claude-opus-5 | 5.00 | 0.50 | 6.25 (5-min) | 25.00 | Anthropic pricing page, 2026-08-29 |
| cc_fable_5 | claude-fable-5 | 10.00 | 1.00 | 12.50 | 50.00 | same |
| cc_fable_5_1 | claude-fable-5-1 | 10.00 | 1.00 | 12.50 | 50.00 | assumed = Fable 5 |
| codex_gpt_5_5 | gpt-5.5 | 5.00 | 0.50 | – | 30.00 | OpenAI pricing, 2026-09-08 |
| codex_gpt_5_6_sol | gpt-5.6-sol | 4.00 | 0.40 | – | 20.00 | same |
| codex_gpt_6_astra | gpt-6-astra | 10.00 | 1.00 | – | 50.00 | same |
| codex_deepseek_v4_pro | deepseek-v4-pro | 1.26 | 0.042 | – | 3.78 | DeepSeek CN peak price ¥9 / ¥0.3 / ¥27 @7.15 |
| cc_deepseek_v4_flash / cc_deepseek_flash_41 | deepseek-v4-flash → deepseek-flash | 0.42 | 0.014 | – | 1.26 | ¥3 / ¥0.1 / ¥9 @7.15 (off-peak is half) |
| cc_seed_evolving | doubao-seed-evolving | 0.84 | 0 | – | 4.20 | Volcengine Ark ¥6 / ¥30 @7.15 |
| cc_glm_5_2 / cc_glm_5_3 | glm-5.2 / glm-5.3 | – | – | – | – | no official unit price captured; token counts only |

Exchange rate used for CNY-denominated vendors: 7.15 CNY/USD.
