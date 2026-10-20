#!/usr/bin/env bash
# Launch one detached generation run.
#   run_set.sh <models,comma,separated> <concurrency> <cases.json> [timeout_min] [logname]
# Requires BENCH_HOME (defaults to $HOME/bench). Uses configs/keys.env inside BENCH_HOME.
set -euo pipefail
MODELS="$1"; CONC="$2"; CASES="$3"; TIMEOUT="${4:-120}"; LOG="${5:-run_$(date +%Y%m%d_%H%M%S)}"
export BENCH_HOME="${BENCH_HOME:-$HOME/bench}"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$BENCH_HOME/logs"
setsid nohup python3 "$HERE/run_bench.py" run --models "$MODELS" --cases "$CASES" \
  --concurrency "$CONC" --timeout-min "$TIMEOUT" > "$BENCH_HOME/logs/$LOG.out" 2>&1 < /dev/null &
echo "started: models=$MODELS conc=$CONC cases=$CASES log=$BENCH_HOME/logs/$LOG.out"
