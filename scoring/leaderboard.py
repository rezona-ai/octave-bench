#!/usr/bin/env python3
"""Recompute the leaderboard and per-slice breakdowns from the released judge results.

Input : results/case_scores.csv (one row per model × task) and results/item_scores.csv.gz (one row per requirement).
Output: results/leaderboard.csv, results/leaderboard.md and results/breakdowns.json.

    python scoring/leaderboard.py                       # writes into results/
    python scoring/leaderboard.py --results my_results  # same layout, another directory

Metrics (per model; every attempt counts, tasks weighted equally):
  completeness    share of the 6 public (Completeness) requirements passed, the ranking metric
  richness        share of the 4 hidden (Richness) requirements passed
  gate_fail_rate  share of attempts flagged by the judge's runnability gate or with no artifact
  C1..C8          pass rate over all 10 requirements, grouped by each requirement's primary capability
Gate flags are diagnostic: flagged attempts keep their raw judgments, and missing artifacts score zero.
"""
from __future__ import annotations
import argparse, csv, gzip, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = {"C1": "Core Rules", "C2": "AI / NPC", "C3": "Numerical Design", "C4": "Interaction & Input",
                "C5": "Levels & Scenes", "C6": "Animation & Rendering", "C7": "Feedback & Game Feel", "C8": "Guidance & Meta-UI"}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
    return {"n_attempts": n,
            "completeness": mean([float(r["completeness"]) for r in rows]),
            "richness": mean([float(r["richness"]) for r in rows]),
            "gate_fail_rate": round(sum(r["gate_flag"] == "True" for r in rows) / n, 4) if n else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=str(ROOT / "results"))
    a = ap.parse_args()
    res = Path(a.results)
    cases = list(csv.DictReader(open(res / "case_scores.csv", encoding="utf-8")))
    names = {r["model"]: r["model_name"] for r in cases}
    by_model = defaultdict(list)
    for r in cases:
        by_model[r["model"]].append(r)

    cap = defaultdict(lambda: [0, 0])
    with gzip.open(res / "item_scores.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = cap[(r["model"], r["primary_capability"])]
            k[0] += int(r["passed"]); k[1] += 1
    caps = {m: {c: round(cap[(m, c)][0] / cap[(m, c)][1], 4) for c in CAPABILITIES if cap[(m, c)][1]} for m in by_model}

    board = sorted(({"model": m, "model_name": names[m], **summarize(rs), **caps[m]} for m, rs in by_model.items()),
                   key=lambda x: -x["completeness"])
    for i, b in enumerate(board, 1):
        b["rank"] = i
    cols = ["rank", "model", "model_name", "n_attempts", "completeness", "richness", "gate_fail_rate", *CAPABILITIES]
    with open(res / "leaderboard.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows({k: b.get(k) for k in cols} for b in board)
    pct = lambda v: f"{v * 100:.1f}" if v is not None else "–"
    md = ["| # | Model | Completeness % | Richness % | Gate flag % | " + " | ".join(CAPABILITIES) + " |",
          "|---|---|---|---|---|" + "---|" * len(CAPABILITIES)]
    md += [f"| {b['rank']} | {b['model_name']} | **{pct(b['completeness'])}** | {pct(b['richness'])} | {pct(b['gate_fail_rate'])} | "
           + " | ".join(pct(b.get(c)) for c in CAPABILITIES) + " |" for b in board]
    (res / "leaderboard.md").write_text("\n".join(md) + "\n")

    breakdowns = {"capabilities": CAPABILITIES}
    for dim in ["track", "platform", "render", "level", "category", "incentive", "judge_batch"]:
        out = {}
        for m, rs in by_model.items():
            groups = defaultdict(list)
            for r in rs:
                groups[r[dim]].append(r)
            out[m] = {g: summarize(v) for g, v in sorted(groups.items())}
        breakdowns[f"by_{dim}"] = out
    overall = summarize(cases)
    (res / "breakdowns.json").write_text(json.dumps({"overall": overall, "leaderboard": board, **breakdowns},
                                                    ensure_ascii=False, indent=1))
    print("\n".join(md))
    print(f"\nAll {overall['n_attempts']} attempts: completeness {pct(overall['completeness'])}%, "
          f"richness {pct(overall['richness'])}%, gate flags {pct(overall['gate_fail_rate'])}%")


if __name__ == "__main__":
    main()
