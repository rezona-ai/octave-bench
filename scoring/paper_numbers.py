#!/usr/bin/env python3
"""Recompute the numbers reported in the OCTAVE paper from the released files and check them.

    python scoring/paper_numbers.py

Reads data/octave_180_en.jsonl and results/{case_scores.csv, item_scores.csv.gz, generation.csv}. Each line prints
the paper's value, the recomputed value and OK / DIFF. Human-evaluation numbers (Table 5, Appendix F) are not
recomputed because per-item human labels are not released; see docs/human_eval.md.
"""
from __future__ import annotations
import csv, gzip, itertools, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "codex_gpt_6_astra"
BLOCKER = ("无法运行", "unable to run")
fails = 0


def check(ref, label, paper, ours):
    global fails
    ok = paper == ours
    fails += not ok
    print(f"{'OK  ' if ok else 'DIFF'} {ref:<10} {label:<58} paper={paper}  ours={ours}")


pct = lambda a, b: round(100 * a / b, 1)


def rate(rows):
    return pct(sum(int(r["passed"]) for r in rows), len(rows))


def jain(c):
    return round(sum(c) ** 2 / (len(c) * sum(x * x for x in c)), 4)


def main():
    tasks = [json.loads(l) for l in open(ROOT / "data/octave_180_en.jsonl", encoding="utf-8")]
    cases = list(csv.DictReader(open(ROOT / "results/case_scores.csv", encoding="utf-8")))
    items = list(csv.DictReader(gzip.open(ROOT / "results/item_scores.csv.gz", "rt", encoding="utf-8")))
    gen = {(r["model"], r["task_id"]): r["gen_status"] for r in csv.DictReader(open(ROOT / "results/generation.csv"))}
    case = {(r["model"], r["task_id"]): r for r in cases}
    caps = [f"C{i}" for i in range(1, 9)]
    comp = [i for i in items if i["kind"] == "completeness"]
    rich = [i for i in items if i["kind"] == "richness"]

    # Dataset (Tables 3, 4, A.1, A.2; Figure 2; Appendix A.4)
    check("Table 3", "tasks / requirements", (180, 1800),
          (len(tasks), sum(len(t["completeness_requirements"]) + len(t["richness_requirements"]) for t in tasks)))
    check("Table 3", "PC Web / Mobile Web tasks", (95, 85),
          (sum(t["platform"] == "web" for t in tasks), sum(t["platform"] == "mobile" for t in tasks)))
    check("Table 4", "source: player / reconstruction / expert", (150, 20, 10),
          tuple(Counter(t["track"] for t in tasks)[k] for k in ["main", "repro", "expert"]))
    check("Table 4", "2D / 3D", (91, 89), tuple(Counter(t["render"] for t in tasks)[k] for k in ["2d", "3d"]))
    genre = Counter(t["category"] for t in tasks)
    check("Table 4", "genres", {"Action": 30, "Adventure & Puzzle": 31, "RPG": 24, "Simulation & Sandbox": 45,
                                "Social & Tabletop": 16, "Strategy": 34}, dict(sorted(genre.items())))
    check("Table A.2", "PC: player / repro / expert", (75, 10, 10),
          tuple(sum(t["platform"] == "web" and t["track"] == k for t in tasks) for k in ["main", "repro", "expert"]))
    player = [t for t in tasks if t["track"] == "main"]
    cov = [sum(c in t["agent_ability"] for t in player) for c in caps]
    check("Table A.1", "selected player-task coverage C1..C8", [150, 133, 130, 74, 91, 74, 31, 80], cov)
    check("A.4", "Jain's index, 150 selected player tasks", 0.8696, jain(cov))
    cov_all = [sum(c in t["agent_ability"] for t in tasks) for c in caps]
    check("A.4", "task-level labels over 180 tasks / Jain", (878, 0.8573), (sum(cov_all), jain(cov_all)))
    c7 = [i for i in items if i["primary_capability"] == "C7"]
    check("G.2", "C7 primary: requirements / tasks / records", (85, 51, 1020),
          (len(c7) // 12, len({i["task_id"] for i in c7}), len(c7)))

    # Main results (Table 6, Section 4.5, Appendix E.4)
    check("E.4", "Completeness passed / slots", (4174, 12960), (sum(int(i["passed"]) for i in comp), len(comp)))
    check("E.4", "Richness passed / slots", (2898, 8640), (sum(int(i["passed"]) for i in rich), len(rich)))
    flags = sum(r["gate_flag"] == "True" for r in cases)
    missing = sum(r["artifact_present"] != "True" for r in cases)
    check("E.4", "gate failures + missing artifacts / records", (452, 2, 2160), (flags - missing, missing, len(cases)))
    check("4.5.1", "overall gate / Completeness / Richness %", (21.0, 32.2, 33.5),
          (pct(flags, len(cases)), rate(comp), rate(rich)))
    check("4.5.1", "without self-evaluation: Completeness / Richness %", (29.9, 32.1),
          (rate([i for i in comp if i["model"] != SELF]), rate([i for i in rich if i["model"] != SELF])))
    table6 = {"cc_deepseek_flash_41": (20.6, 25.9, 28.9), "cc_deepseek_v4_flash": (26.7, 23.5, 28.5),
              "cc_fable_5": (21.1, 39.0, 39.3), "cc_fable_5_1": (17.8, 44.7, 40.7), "cc_glm_5_2": (26.7, 24.3, 28.1),
              "cc_glm_5_3": (21.7, 31.1, 34.0), "cc_opus_5": (16.1, 37.2, 40.4), "cc_seed_evolving": (33.3, 21.0, 24.9),
              "codex_deepseek_v4_pro": (22.8, 22.2, 27.5), "codex_gpt_5_5": (15.6, 26.9, 28.3),
              "codex_gpt_5_6_sol": (16.7, 33.4, 32.6), "codex_gpt_6_astra": (13.3, 57.1, 49.3)}
    for m, paper in table6.items():
        rs = [r for r in cases if r["model"] == m]
        check("Table 6", f"{rs[0]['model_name']}: gate / Completeness / Richness %", paper,
              (pct(sum(r["gate_flag"] == "True" for r in rs), len(rs)),
               rate([i for i in comp if i["model"] == m]), rate([i for i in rich if i["model"] == m])))

    # Task source (Figure 3)
    for track, paper in {"main": (27.4, 28.8), "repro": (52.0, 49.2), "expert": (65.1, 72.7)}.items():
        check("4.5.2", f"{track}: Completeness / Richness %", paper,
              tuple(rate([i for i in rows if case[(i["model"], i["task_id"])]["track"] == track]) for rows in (comp, rich)))

    # Capabilities (Figure 4, Section 4.5.3)
    by_cap = lambda rows, c: rate([i for i in rows if i["primary_capability"] == c])
    check("4.5.3", "combined: C3 / C1 / C7 %", (37.5, 37.4, 26.7), tuple(by_cap(items, c) for c in ["C3", "C1", "C7"]))
    check("4.5.3", "Completeness: C3 (highest) / C7 (lowest) %", (37.6, 25.2), (by_cap(comp, "C3"), by_cap(comp, "C7")))
    check("4.5.3", "Richness: C1 (highest) / C4 (lowest) %", (37.5, 28.5), (by_cap(rich, "C1"), by_cap(rich, "C4")))
    comb = {c: by_cap(items, c) for c in caps}
    check("4.5.3", "combined highest / lowest capability", ("C3", "C7"), (max(comb, key=comb.get), min(comb, key=comb.get)))
    for plat, low in [("web", "C2"), ("mobile", "C4")]:
        rs = [i for i in items if case[(i["model"], i["task_id"])]["platform"] == plat]
        pc = {c: by_cap(rs, c) for c in caps}
        check("4.5.3", f"lowest capability on {plat}", low, min(pc, key=pc.get))

    # Difficulty (Figure 5, Table G.1)
    for lvl, paper in {"easy": (37.7, 41.9, 39.7), "medium": (31.7, 33.1, 32.3),
                       "hard": (30.9, 29.9, 30.5), "extreme": (29.6, 25.8, 28.5)}.items():
        check("Table G.1", f"{lvl}: Completeness / Richness / all %", paper,
              tuple(rate([i for i in rows if i["difficulty"] == lvl]) for rows in (comp, rich, items)))
    check("C.2", "requirements per stratum", [450] * 4,
          [sum(i["difficulty"] == l for i in items) // 12 for l in ["easy", "medium", "hard", "extreme"]])
    per_req = defaultdict(list)
    for i in items:
        per_req[(i["task_id"], i["kind"], i["item_index"])].append((float(i["ads"]), int(i["passed"])))
    xs = [v[0][0] for v in per_req.values()]
    ys = [statistics.mean(p for _, p in v) for v in per_req.values()]
    check("G.1", "Spearman a_DS vs 12-model pass rate", -0.1354, round(spearman(xs, ys), 4))
    check("G.1", "Spearman over 21,600 records", -0.0928,
          round(spearman([float(i["ads"]) for i in items], [int(i["passed"]) for i in items]), 4))

    # Platform (Figure 6, Appendix G.3)
    for label, keep, paper in [("all tasks", lambda r: True, (28.1, 13.1, 27.4, 37.6, 24.2, 44.0)),
                               ("without expert tasks (G.3)", lambda r: r["track"] != "expert",
                                (30.9, 13.1, 23.0, 37.6, 18.5, 44.0))]:
        out = []
        for plat in ["web", "mobile"]:
            rs = [r for r in cases if r["platform"] == plat and keep(r)]
            out.append(pct(sum(r["gate_flag"] == "True" for r in rs), len(rs)))
        for rows in (comp, rich):
            for plat in ["web", "mobile"]:
                out.append(rate([i for i in rows if case[(i["model"], i["task_id"])]["platform"] == plat
                                 and keep(case[(i["model"], i["task_id"])])]))
        check("4.5.5", f"{label}: gate PC/Mob, Compl. PC/Mob, Rich. PC/Mob", paper, tuple(out))
    plat_of = lambda i: case[(i["model"], i["task_id"])]["platform"]
    higher = lambda rows: rate([i for i in rows if plat_of(i) == "mobile"]) > rate([i for i in rows if plat_of(i) == "web"])
    check("4.5.5", "models with Mobile > PC on both Completeness and Richness", 12,
          sum(higher([i for i in comp if i["model"] == m]) and higher([i for i in rich if i["model"] == m]) for m in table6))
    check("4.5.5", "capabilities with Mobile > PC (combined)", 8,
          sum(higher([i for i in items if i["primary_capability"] == c]) for c in caps))

    # Generation statuses (Appendix D.4)
    check("D.4", "success / timeout / agent_error / refusal / no_dist", (2094, 50, 7, 5, 4),
          tuple(Counter(gen.values())[k] for k in ["success", "timeout", "agent_error", "refusal", "no_dist"]))
    flagged = Counter(gen[(r["model"], r["task_id"])] for r in cases if r["gate_flag"] == "True")
    check("D.4", "flagged: success / timeout / agent_error / refusal / no_dist", (418, 21, 6, 5, 4),
          tuple(flagged[k] for k in ["success", "timeout", "agent_error", "refusal", "no_dist"]))

    # Common task set (Appendix G.4): an attempt is excluded when all 10 requirements fail and a reason names a blocker
    rows_of = defaultdict(list)
    for i in items:
        rows_of[(i["model"], i["task_id"])].append(i)
    ok = defaultdict(set)
    for (m, t), rs in rows_of.items():
        blocked = all(i["passed"] == "0" for i in rs) and any(b in i["reason"] for i in rs for b in BLOCKER)
        if case[(m, t)]["artifact_present"] == "True" and not blocked:
            ok[m].add(t)
    common = set.intersection(*ok.values())
    cc = [i for i in comp if i["task_id"] in common]
    cr = [i for i in rich if i["task_id"] in common]
    check("G.4", "common tasks; Completeness / Richness passed / slots", (95, 2893, 6840, 1892, 4560),
          (len(common), sum(int(i["passed"]) for i in cc), len(cc), sum(int(i["passed"]) for i in cr), len(cr)))
    pw = [len(ok[a] & ok[b]) for a, b in itertools.combinations(sorted(ok), 2)]
    check("G.4", "pairwise supports: count / min / max / median", (66, 117, 157, 141),
          (len(pw), min(pw), max(pw), int(statistics.median(pw))))

    print(f"\n{'all checks passed' if not fails else f'{fails} check(s) differ'}")
    sys.exit(1 if fails else 0)


def spearman(a, b):
    def ranks(x):
        order = sorted(range(len(x)), key=x.__getitem__)
        r, i = [0.0] * len(x), 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return num / (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5


if __name__ == "__main__":
    main()
