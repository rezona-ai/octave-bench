#!/usr/bin/env python3
"""Build a static "click to play" index over generated games and (optionally) upload it to a public GCS bucket.

For every (model zip, task_id) it extracts <model>/<task>/project/dist/ out of the result zip, rewrites
root-absolute asset paths ("/assets/…") to relative ones so Vite builds work under a sub-path, and writes
one HTML table per set (web / mobile) with a ▶ link per cell. Cells without a built dist show "—".

    python playground/build_play.py --zips-dir /tmp/zips --cases data/octave_180_zh.jsonl --select data/play_selection.json \
        --web-zip-prefix "" --mobile-zip-prefix m_ --out site --bucket gs://my-public-bucket

--select is a JSON {"web_models": [...], "mobile_models": [...], "cases": [...task_id...]}; without it, a
stratified pick is made (--n, default 20) preferring cases every model built successfully.
Zips must be named <prefix><model_key>.zip and contain <model_key>/<task_id>/project/dist/index.html.
The bucket must allow public reads (allUsers: objectViewer); authenticated storage.cloud.google.com links
break module-script loading and show blank pages.
"""
from __future__ import annotations
import argparse, collections, html, json, os, shutil, subprocess, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def render(c): return c["render"].upper() if c.get("render") else ("3D" if "_3d_" in c["task_id"] else "2D")

def load_cases(path: str) -> list[dict]:
    text = Path(path).read_text()
    return [json.loads(l) for l in text.splitlines() if l.strip()] if path.endswith(".jsonl") else json.loads(text)

def patch_text(s: str, public: set[str]) -> str:
    for n in sorted({"assets"} | public, key=len, reverse=True):
        for q in ('"', "'", "`", "("): s = s.replace(f"{q}/{n}", f"{q}./{n}")
        s = s.replace(f"url(/{n}", f"url(./{n}")
    return s.replace('href="/"', 'href="./"')

def extract(zp: Path, model: str, task: str, out: Path) -> bool:
    if not zp.exists(): return False
    prefix = f"{model}/{task}/project/dist/"
    with zipfile.ZipFile(zp) as z:
        members = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]
        if prefix + "index.html" not in members: return False
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True)
        for n in members:
            dst = out / n[len(prefix):]; dst.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(dst, "wb") as f: shutil.copyfileobj(src, f)
    public = {p.name for p in out.iterdir() if p.name != "index.html"}
    for p in out.rglob("*"):
        if p.suffix.lower() in (".html", ".js", ".mjs", ".css"):
            try: t = p.read_text(encoding="utf-8")
            except UnicodeDecodeError: continue
            t2 = patch_text(t, public)
            if t2 != t: p.write_text(t2, encoding="utf-8")
    return True

def has_dist(zp: Path, model: str, task: str) -> bool:
    if not zp.exists(): return False
    with zipfile.ZipFile(zp) as z: return f"{model}/{task}/project/dist/index.html" in set(z.namelist())

def pick_cases(cases: dict, sets: dict, n: int) -> list[str]:
    score = {t: sum(has_dist(zp, m, t) for zps in sets.values() for m, zp in zps.items()) for t in cases}
    bycat = collections.defaultdict(list)
    for t, c in cases.items(): bycat[c["category"]].append(t)
    total = len(cases); alloc = {k: max(1, round(len(v) * n / total)) for k, v in bycat.items()}
    while sum(alloc.values()) > n: alloc[max(alloc, key=alloc.get)] -= 1
    while sum(alloc.values()) < n: alloc[min(alloc, key=alloc.get)] += 1
    sel = []
    for k, v in bycat.items():
        sel += sorted(v, key=lambda t: (-score[t], render(cases[t]) != "3D", t))[: alloc[k]]
    return sorted(sel)

def table(setname, models, display, sel, cases, avail, host):
    h = ['<table><thead><tr><th class="case">Case</th>'] + [f"<th>{html.escape(display.get(m, m))}</th>" for m in models] + ["</tr></thead><tbody>"]
    for t in sel:
        c = cases[t]
        h.append(f'<tr><td class="case"><b>{t}</b><br><small>{html.escape(c.get("category",""))} · {c.get("level","")}</small>'
                 f'<details><summary>{html.escape(c.get("desc","")[:60])}</summary><pre>{html.escape(c["prompt"])}</pre></details></td>')
        h += [f'<td><a href="{host}/{setname}/{m}/{t}/index.html" target="_blank">▶ 玩</a></td>' if avail.get((setname, m, t)) else '<td><span class="na">—</span></td>' for m in models]
        h.append("</tr>")
    return "\n".join(h + ["</tbody></table>"])

CSS = """body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:24px;color:#222}h1{font-size:22px}h2{font-size:18px;margin-top:36px}
table{border-collapse:collapse;font-size:13px}th,td{border:1px solid #ddd;padding:6px 8px;text-align:center;vertical-align:top}th{background:#f4f4f4;position:sticky;top:0}
td.case,th.case{text-align:left;min-width:260px;max-width:340px}a{color:#0b5fff;text-decoration:none;font-weight:600}.na{color:#bbb}
details summary{cursor:pointer;color:#666;font-size:12px}pre{white-space:pre-wrap;font-size:11px;background:#fafafa;padding:6px;max-height:260px;overflow:auto}
.note{background:#fff8e1;padding:10px 12px;border-radius:6px;font-size:13px}"""

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zips-dir", required=True)
    ap.add_argument("--cases", required=True, help="web case json (prompts shown in the web table)")
    ap.add_argument("--mobile-cases", default=None, help="mobile case json (same task_ids, mobile prompts)")
    ap.add_argument("--select", default=None, help="selection json; generated if absent")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--models-json", default=str(ROOT / "configs/models.json"))
    ap.add_argument("--web-zip-prefix", default=""); ap.add_argument("--mobile-zip-prefix", default="m_")
    ap.add_argument("--out", default=str(ROOT / "playground/site"))
    ap.add_argument("--bucket", default=None, help="gs://bucket[/prefix] to rsync the site to (public-read bucket)")
    ap.add_argument("--title", default="Game Benchmark Playground")
    a = ap.parse_args()
    zd = Path(a.zips_dir); out = Path(a.out)
    models_cfg = json.loads(Path(a.models_json).read_text())["models"]
    display = {k: v.get("display", k) for k, v in models_cfg.items()}
    cases = {c["task_id"]: c for c in load_cases(a.cases)}
    mcases = {c["task_id"]: c for c in load_cases(a.mobile_cases)} if a.mobile_cases else cases
    order = list(models_cfg)
    sets = {"web": {m: zd / f"{a.web_zip_prefix}{m}.zip" for m in order if (zd / f"{a.web_zip_prefix}{m}.zip").exists()}}
    mob = {m: zd / f"{a.mobile_zip_prefix}{m}.zip" for m in order if (zd / f"{a.mobile_zip_prefix}{m}.zip").exists()}
    if mob and a.mobile_zip_prefix != a.web_zip_prefix: sets["mobile"] = mob
    if a.select:
        s = json.loads(Path(a.select).read_text()); sel = s["cases"]
    else:
        sel = pick_cases(cases, sets, a.n); (out.parent / "play_selection.json").write_text(json.dumps({"cases": sel}, indent=1))
    avail = {}
    for setname, zps in sets.items():
        for m, zp in zps.items():
            ok = sum(1 for t in sel if extract(zp, m, t, out / setname / m / t) and avail.setdefault((setname, m, t), True))
            print(f"{setname:6} {m:26} playable {ok}/{len(sel)}")
    host = (a.bucket.replace("gs://", "https://storage.googleapis.com/").rstrip("/")) if a.bucket else "."
    sections = []
    for setname, zps in sets.items():
        ms = [m for m in zps if any(avail.get((setname, m, t)) for t in sel)]
        n_ok = sum(avail.get((setname, m, t), False) for m in ms for t in sel)
        sections.append(f"<h2>{'Web' if setname == 'web' else 'Mobile'} ({n_ok} playable)</h2>" + table(setname, ms, display, sel, cases if setname == "web" else mcases, avail, host))
    page = (f'<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{html.escape(a.title)}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><h1>{html.escape(a.title)}</h1>'
            f'<p class="note">{len(sel)} shared cases; each cell opens the dist that model built for that case. “—” = no runnable build (failed, timed out or refused). '
            f'Mobile games lock to touch input; use a phone or the browser device emulator.</p>' + "".join(sections) + "</body></html>")
    out.mkdir(parents=True, exist_ok=True); (out / "index.html").write_text(page, encoding="utf-8")
    print("index:", out / "index.html")
    if a.bucket:
        subprocess.run(["gcloud", "storage", "rsync", "-r", "-q", str(out), a.bucket], check=True)
        print("uploaded:", host + "/index.html")

if __name__ == "__main__":
    main()
