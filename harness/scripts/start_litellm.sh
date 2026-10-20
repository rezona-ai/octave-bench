#!/usr/bin/env bash
# Anthropic-compatible proxy in front of an OpenAI-compatible vendor (used for Volcengine Ark / Seed evolving).
# Claude Code talks to http://127.0.0.1:4000 ; LiteLLM forwards to the vendor with ARK_API_KEY from keys.env.
set -euo pipefail
export BENCH_HOME="${BENCH_HOME:-$HOME/bench}"
set -a; source "$BENCH_HOME/configs/keys.env"; set +a
LITELLM="${LITELLM_BIN:-litellm}"   # e.g. /opt/litellm-venv/bin/litellm
exec "$LITELLM" --config "$BENCH_HOME/configs/litellm_seed.yaml" --host 127.0.0.1 --port 4000 --num_workers 4
