#!/usr/bin/env python3
"""Aggregate harness status (run_bench.py status → status.csv) and judge results (eval/run_eval.py →
eval_results/<model>.csv) into one per-model table, optionally restricted to a case subset.

    python scoring/aggregate.py --status status_web.csv --eval-dir eval_results --subset data/octave_180_zh.jsonl --out my_results.md

Columns: cases, build success (dist/index.html), terminal failures by kind, cost USD (from token usage ×
configs/models.json prices), mean wall minutes, mean checklist pass ratio, gate-fail count, mean aux dims.
Cost is recomputed here from the usage columns so the numbers do not depend on what the CLI self-reported.
"""
from __future__ import annotations
import argparse, csv, json, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def cost_usd(price: dict | None, r: dict) -> float | None:
    if not price: return None
    tok = lambda k: int(r.get(k) or 0)
    return (tok("in_tok") * price["input"] + tok("out_tok") * price["output"] + tok("cache_read_tok") * price.get("cache_read", 0)
            + tok("cache_write_tok") * price.get("cache_write", 0)) / 1e6

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", required=True, nargs="+", help="one or more status.csv from run_bench.py status")
    ap.add_argument("--eval-dir", default=None, help="eval_results dir with <model>.csv (optional)")
    ap.add_argument("--subset", default=None, help="case .jsonl/.json; restrict to its task_ids")
    ap.add_argument("--models-json", default=str(ROOT / "configs/models.json"))
    ap.add_argument("--out", default=None, help="write markdown table here (stdout otherwise)")
    a = ap.parse_args()
    prices = {k: v.get("price") for k, v in json.loads(Path(a.models_json).read_text())["models"].items()}
    display = {k: v.get("display", k) for k, v in json.loads(Path(a.models_json).read_text())["models"].items()}
    if a.subset:
        text = Path(a.subset).read_text()
        rows = [json.loads(l) for l in text.splitlines() if l.strip()] if a.subset.endswith(".jsonl") else json.loads(text)
        subset = {c["task_id"] for c in rows}
    else:
        subset = None
    rows = collections.defaultdict(dict)  # model -> task -> latest row
    for f in a.status:
        for r in csv.DictReader(open(f)):
            if subset and r["task_id"] not in subset: continue
            rows[r["model_key"]][r["task_id"]] = r
    ev = collections.defaultdict(dict)
    if a.eval_dir:
        for f in Path(a.eval_dir).glob("*.csv"):
            for r in csv.DictReader(open(f)):
                if subset and r["task_id"] not in subset: continue
                ev[f.stem][r["task_id"]] = r
    hdr = ["model", "cases", "build_ok", "fail_kinds", "cost_usd", "usd/case", "avg_min", "judged", "mean_pass", "gate_fail", "aux_levels", "aux_juice"]
    lines = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for m in sorted(rows):
        rs = list(rows[m].values()); n = len(rs)
        ok = sum(r["status"] == "success" for r in rs)
        kinds = collections.Counter(r["status"] for r in rs if r["status"] != "success")
        costs = [cost_usd(prices.get(m), r) for r in rs]; has_price = prices.get(m) is not None
        tot = sum(c or 0 for c in costs)
        wall = sum(float(r.get("wall_s") or 0) for r in rs) / 60 / max(n, 1)
        e = [x for x in ev.get(m, {}).values() if x.get("total") not in (None, "", "0")]
        mp = sum(float(x["passed"]) / float(x["total"]) for x in e) / len(e) if e else None
        gf = sum(x.get("gate_failed") == "True" for x in e)
        al = [float(x["aux_levels"]) for x in e if x.get("aux_levels") not in ("", "None", None)]
        aj = [float(x["aux_juice"]) for x in e if x.get("aux_juice") not in ("", "None", None)]
        lines.append("| " + " | ".join([display.get(m, m), str(n), str(ok), ", ".join(f"{k}:{v}" for k, v in kinds.items()) or "-",
                     f"{tot:.2f}" if has_price else "n/a", f"{tot / max(n, 1):.2f}" if has_price else "n/a", f"{wall:.1f}",
                     str(len(e)), f"{mp:.3f}" if mp is not None else "-", str(gf) if e else "-",
                     f"{sum(al) / len(al):.2f}" if al else "-", f"{sum(aj) / len(aj):.2f}" if aj else "-"]) + " |")
    text = "\n".join(lines)
    if a.out: Path(a.out).write_text(text + "\n"); print("wrote", a.out)
    else: print(text)

if __name__ == "__main__":
    main()
