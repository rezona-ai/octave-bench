#!/usr/bin/env python3
"""Batch runner: drive Claude Code / Codex CLI over benchmark cases, one isolated
process per (model, case), with per-model credentials injected via env only.

Layout (BENCH_HOME, default ~/bench):
  configs/models.json      model registry (agent, base_url, model id, key_env, ...)
  configs/keys.env         KEY=value lines, never copied anywhere else
  configs/prompt_template.md  wrapper around the case prompt ({prompt})
  (cases)                  any .jsonl / .json case file, e.g. data/octave_180_zh.jsonl from this repo
  runs/<model_key>/<task_id>/{prompt.md,transcript.jsonl,stderr.log,meta.json,project/}
  cc_home/<model_key>/     CLAUDE_CONFIG_DIR per model (keeps ~/.claude untouched)
  codex_home/<model_key>/  CODEX_HOME per model (own config.toml)

Usage:
  run_bench.py run   --models cc_glm_5_3,codex_gpt_5_5 --cases data/octave_180_zh.jsonl --limit 3
  run_bench.py run   --models all --cases data/octave_180_zh.jsonl
  run_bench.py smoke --models all            # trivial prompt through every model that has a key
  run_bench.py status [--models all]         # summarize meta.json into a table + CSV
"""
from __future__ import annotations
import argparse, csv, json, os, shutil, signal, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BENCH = Path(os.environ.get("BENCH_HOME", str(Path.home() / "bench")))
CFG = BENCH / "configs"
RUNS = BENCH / "runs"
LOGS = BENCH / "logs"
PRUNE_DIRS = {"node_modules", ".vite", ".cache", ".turbo", ".parcel-cache"}
SMOKE_PROMPT = "Create a file named hello.txt in the current directory containing exactly the text OK. Do nothing else, then stop."

KEYS: dict = {}  # populated by cmd_run from configs/keys.env
_print_lock = threading.Lock()
def log(msg: str, fh=None):
    line = f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}"
    with _print_lock:
        print(line, flush=True)
        if fh:
            fh.write(line + "\n"); fh.flush()

def now_iso(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_keys() -> dict:
    p = CFG / "keys.env"
    keys = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln: continue
            k, v = ln.split("=", 1); keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys

def load_models() -> dict:
    return json.loads((CFG / "models.json").read_text())["models"]

def load_cases(path: str) -> list[dict]:
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    d = json.loads(Path(path).read_text())
    return d if isinstance(d, list) else d["cases"]

def render_prompt(case: dict) -> str:
    """Wrap the case prompt. A case with platform=="mobile" uses configs/prompt_template_mobile.md when present."""
    tpl_p = CFG / "prompt_template.md"
    if case.get("platform") == "mobile" and (CFG / "prompt_template_mobile.md").exists():
        tpl_p = CFG / "prompt_template_mobile.md"
    return tpl_p.read_text().replace("{prompt}", case["prompt"])

def tool_versions() -> dict:
    out = {}
    for name in ("claude", "codex", "node", "npm"):
        try:
            out[name] = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=30, env=base_env()).stdout.strip()
        except Exception as e:
            out[name] = f"ERR {e}"
    return out

# ---------------------------------------------------------------- agent launchers
def base_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "OPENAI_", "CODEX_", "CLAUDE_"))}
    # BENCH_TOOLS_BIN lets a pinned agent-CLI install (e.g. ~/bench/tools/node_modules/.bin) win over globals
    env["PATH"] = (f"{os.environ['BENCH_TOOLS_BIN']}:" if os.environ.get("BENCH_TOOLS_BIN") else "") + f"{Path.home()}/.npm-global/bin:{Path.home()}/.local/bin:" + env.get("PATH", "")
    env["CI"] = "1"
    return env

def claude_setup(mkey: str, mcfg: dict, key: str) -> tuple[list[str], dict]:
    home = BENCH / "cc_home" / mkey
    home.mkdir(parents=True, exist_ok=True)
    cj = home / ".claude.json"
    if not cj.exists():
        cj.write_text(json.dumps({"hasCompletedOnboarding": True, "theme": "dark",
                                  "bypassPermissionsModeAccepted": True}, indent=1))
    settings = {"permissions": {"defaultMode": "bypassPermissions"}}
    (home / "settings.json").write_text(json.dumps(settings, indent=1))
    env = base_env()
    env.update({
        "CLAUDE_CONFIG_DIR": str(home),
        "ANTHROPIC_BASE_URL": mcfg["base_url"].rstrip("/"),
        "ANTHROPIC_MODEL": mcfg["model"],
        "ANTHROPIC_DEFAULT_OPUS_MODEL": mcfg["model"],
        "ANTHROPIC_DEFAULT_SONNET_MODEL": mcfg["model"],
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": mcfg["model"],
        "CLAUDE_CODE_SUBAGENT_MODEL": mcfg["model"],
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # default cap is 32000; GLM-5.2 hit it in a single turn (hard_rewrite_048, 2026-09-08). Uniform for all models.
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(mcfg.get("max_output_tokens", 64000)),
    })
    if "api.anthropic.com" in mcfg["base_url"]:
        env["ANTHROPIC_API_KEY"] = key
    else:
        env["ANTHROPIC_AUTH_TOKEN"] = key
    # optional extra request headers (e.g. "anthropic-workspace-id: wrkspc_..." for org-scoped keys);
    # value comes from keys.env under the name given by models.json "custom_headers_env"
    hdr_env = mcfg.get("custom_headers_env")
    if hdr_env and KEYS.get(hdr_env):
        env["ANTHROPIC_CUSTOM_HEADERS"] = KEYS[hdr_env]
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions", "--model", mcfg["model"]]
    if mcfg.get("effort"):
        cmd += ["--effort", mcfg["effort"]]
    if mcfg.get("max_turns"):
        cmd += ["--max-turns", str(mcfg["max_turns"])]
    return cmd, env

def codex_setup(mkey: str, mcfg: dict, key: str) -> tuple[list[str], dict]:
    home = BENCH / "codex_home" / mkey
    home.mkdir(parents=True, exist_ok=True)
    cfg = f'''model = "{mcfg["model"]}"
model_provider = "bench"
model_reasoning_effort = "{mcfg.get("effort", "high")}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
disable_response_storage = true

[model_providers.bench]
name = "bench"
base_url = "{mcfg["base_url"].rstrip("/")}"
env_key = "BENCH_PROVIDER_KEY"
wire_api = "{mcfg.get("wire_api", "responses")}"
'''
    (home / "config.toml").write_text(cfg)
    env = base_env()
    env.update({"CODEX_HOME": str(home), "BENCH_PROVIDER_KEY": key})
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check",
           "--dangerously-bypass-approvals-and-sandbox", "-"]
    return cmd, env

# ---------------------------------------------------------------- result parsing
def parse_claude(transcript: Path) -> dict:
    out = {}
    try:
        for ln in transcript.read_text(errors="replace").splitlines()[::-1]:
            try: obj = json.loads(ln)
            except Exception: continue
            if obj.get("type") == "result":
                out = {k: obj.get(k) for k in ("subtype", "is_error", "duration_ms", "duration_api_ms",
                                               "num_turns", "total_cost_usd", "usage", "modelUsage")}
                out["final_text"] = (obj.get("result") or "")[:2000]
                break
    except FileNotFoundError: pass
    return out

def parse_codex(transcript: Path) -> dict:
    out, last_msg = {}, None
    try:
        for ln in transcript.read_text(errors="replace").splitlines():
            try: obj = json.loads(ln)
            except Exception: continue
            t = obj.get("type", "")
            if t == "turn.completed":
                out["usage"] = obj.get("usage")
            elif t == "item.completed" and (obj.get("item") or {}).get("type") == "agent_message":
                last_msg = obj["item"].get("text")
            elif t == "error":
                out.setdefault("errors", []).append(obj.get("message"))
    except FileNotFoundError: pass
    if last_msg: out["final_text"] = last_msg[:2000]
    return out

def project_stats(proj: Path) -> dict:
    src_files = 0; dist_ok = False; total_bytes = 0
    if proj.exists():
        for p in proj.rglob("*"):
            if any(part in PRUNE_DIRS for part in p.parts): continue
            if p.is_file():
                src_files += 1; total_bytes += p.stat().st_size
        dist_ok = (proj / "dist" / "index.html").exists()
    return {"files": src_files, "bytes": total_bytes, "dist_index_html": dist_ok,
            "package_json": (proj / "package.json").exists()}

def prune(proj: Path):
    for p in list(proj.rglob("*")):
        if p.is_dir() and p.name in PRUNE_DIRS:
            shutil.rmtree(p, ignore_errors=True)

# ---------------------------------------------------------------- one run
def run_one(mkey: str, mcfg: dict, key: str, case: dict, timeout_s: int, force: bool, smoke: bool, logfh) -> dict:
    tid = case["task_id"]
    wd = RUNS / ("_smoke" if smoke else "") / mkey / tid if smoke else RUNS / mkey / tid
    meta_p = wd / "meta.json"
    if meta_p.exists() and not force:
        try:
            old = json.loads(meta_p.read_text())
            if old.get("status") in ("success", "refusal"):
                return {"model": mkey, "task_id": tid, "status": "skipped-done"}
        except Exception: pass
    if wd.exists():  # archive previous attempt's logs, wipe project
        att = wd / "attempts"; att.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%m%d_%H%M%S")
        for f in ("transcript.jsonl", "stderr.log", "meta.json"):
            if (wd / f).exists(): shutil.move(str(wd / f), str(att / f"{stamp}_{f}"))
        shutil.rmtree(wd / "project", ignore_errors=True)
    proj = wd / "project"; proj.mkdir(parents=True, exist_ok=True)
    prompt = SMOKE_PROMPT if smoke else render_prompt(case)
    (wd / "prompt.md").write_text(prompt)
    if mcfg["agent"] == "claude": cmd, env = claude_setup(mkey, mcfg, key)
    elif mcfg["agent"] == "codex": cmd, env = codex_setup(mkey, mcfg, key)
    else: raise ValueError(mcfg["agent"])
    meta = {"model_key": mkey, "agent": mcfg["agent"], "model": mcfg["model"], "base_url": mcfg["base_url"],
            "display": mcfg.get("display"), "effort": mcfg.get("effort"), "task_id": tid,
            "level": case.get("level"), "category": case.get("category"), "source_file": case.get("source_file"),
            "platform": case.get("platform"), "prompt_template": "mobile" if case.get("platform") == "mobile" and (CFG / "prompt_template_mobile.md").exists() else "web",
            "cmd": cmd, "started_at": now_iso(), "timeout_s": timeout_s, "host": os.uname().nodename}
    log(f"START {mkey} {tid}", logfh)
    t0 = time.time()
    with open(wd / "transcript.jsonl", "wb") as out, open(wd / "stderr.log", "wb") as err:
        p = subprocess.Popen(cmd, cwd=str(proj), env=env, stdin=subprocess.PIPE, stdout=out, stderr=err,
                             start_new_session=True)
        try:
            p.stdin.write(prompt.encode()); p.stdin.close()
        except BrokenPipeError: pass
        timed_out = False
        try:
            rc = p.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(p.pid, signal.SIGTERM); time.sleep(10); os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            rc = p.wait()
        # agents often leave `vite dev` servers behind; reap the whole session group
        try: os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass
    wall = round(time.time() - t0, 1)
    parsed = parse_claude(wd / "transcript.jsonl") if mcfg["agent"] == "claude" else parse_codex(wd / "transcript.jsonl")
    prune(proj)
    stats = project_stats(proj)
    ft = (parsed or {}).get("final_text") or ""
    if timed_out: status = "timeout"
    elif rc != 0 and ("[general_harms]" in ft or "can't help with this" in ft): status = "refusal"  # model safety refusal: terminal, not retried
    elif rc != 0: status = "agent_error"
    elif smoke: status = "success" if (proj / "hello.txt").exists() else "no_output"
    elif stats["dist_index_html"]: status = "success"
    elif stats["package_json"]: status = "no_dist"
    else: status = "no_project"
    meta.update({"finished_at": now_iso(), "wall_s": wall, "returncode": rc, "timed_out": timed_out,
                 "status": status, "agent_result": parsed, "project": stats})
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    cost = (parsed or {}).get("total_cost_usd")
    log(f"END   {mkey} {tid} status={status} rc={rc} wall={wall}s cost={cost}", logfh)
    return {"model": mkey, "task_id": tid, "status": status, "wall_s": wall}

# ---------------------------------------------------------------- commands
def select_models(spec: str, models: dict, keys: dict) -> dict:
    sel = models if spec == "all" else {k: models[k] for k in spec.split(",")}
    ok = {}
    for k, m in sel.items():
        if not keys.get(m["key_env"]):
            log(f"SKIP {k}: no key for {m['key_env']} in configs/keys.env")
        else: ok[k] = m
    return ok

def cmd_run(args, smoke=False):
    keys, models = load_keys(), load_models()
    KEYS.update(keys)
    sel = select_models(args.models, models, keys)
    if not sel: sys.exit("no runnable models")
    if smoke:
        cases = [{"task_id": "smoke", "prompt": SMOKE_PROMPT}]
    else:
        cases = load_cases(args.cases)
        if args.task_ids:
            want = set(args.task_ids.split(",")); cases = [c for c in cases if c["task_id"] in want]
        if args.limit: cases = cases[: args.limit]
    LOGS.mkdir(parents=True, exist_ok=True)
    logfh = open(LOGS / f"{'smoke' if smoke else 'run'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", "a")
    log(f"tools={tool_versions()}", logfh)
    log(f"models={list(sel)} cases={len(cases)} timeout={args.timeout_min}min", logfh)
    if args.dry_run:
        for k in sel:
            for c in cases: print(k, c["task_id"])
        return
    sems = {k: threading.Semaphore(args.concurrency or m.get("concurrency", 3)) for k, m in sel.items()}
    total_workers = sum(args.concurrency or m.get("concurrency", 3) for m in sel.values())
    def job(k, c):
        with sems[k]:
            return run_one(k, sel[k], keys[sel[k]["key_env"]], c, int(args.timeout_min * 60), args.force, smoke, logfh)
    results = []
    with ThreadPoolExecutor(max_workers=total_workers) as ex:
        futs = [ex.submit(job, k, c) for c in cases for k in sel]   # interleave models so vendors share load
        for f in as_completed(futs):
            try: results.append(f.result())
            except Exception as e: log(f"EXC {e!r}", logfh)
    summ = {}
    for r in results: summ[(r["model"], r["status"])] = summ.get((r["model"], r["status"]), 0) + 1
    log("SUMMARY " + json.dumps({f"{m}:{s}": n for (m, s), n in sorted(summ.items())}), logfh)

def usage_tokens(agent: str, ar: dict) -> dict:
    u = (ar or {}).get("usage") or {}
    if agent == "claude":
        return {"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0)}
    # codex: input_tokens already includes cached_input_tokens
    ci = u.get("cached_input_tokens", 0)
    return {"in": u.get("input_tokens", 0) - ci, "out": u.get("output_tokens", 0), "cache_read": ci,
            "cache_write": u.get("cache_write_input_tokens", 0)}

def price_cost(price: dict | None, tk: dict):
    if not price: return None
    return round((tk["in"] * price["input"] + tk["out"] * price["output"] + tk["cache_read"] * price.get("cache_read", 0)
                  + tk["cache_write"] * price.get("cache_write", 0)) / 1e6, 4)

def cmd_status(args):
    rows = []
    models = load_models()
    for meta_p in RUNS.glob("*/*/meta.json"):
        try: m = json.loads(meta_p.read_text())
        except Exception: continue
        if args.models != "all" and m["model_key"] not in args.models.split(","): continue
        ar = m.get("agent_result") or {}
        tk = usage_tokens(m["agent"], ar)
        rows.append({"model_key": m["model_key"], "task_id": m["task_id"], "level": m.get("level"), "status": m["status"],
                     "wall_s": m.get("wall_s"), "in_tok": tk["in"], "out_tok": tk["out"], "cache_read_tok": tk["cache_read"],
                     "cache_write_tok": tk["cache_write"],
                     "cost_usd": price_cost((models.get(m["model_key"]) or {}).get("price"), tk),
                     "cc_reported_cost": ar.get("total_cost_usd"), "turns": ar.get("num_turns"),
                     "files": (m.get("project") or {}).get("files"), "dist": (m.get("project") or {}).get("dist_index_html"),
                     "finished_at": m.get("finished_at")})
    rows.sort(key=lambda r: (r["model_key"], r["task_id"]))
    out = BENCH / "status.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["model_key"]); w.writeheader(); w.writerows(rows)
    agg = {}
    for r in rows:
        a = agg.setdefault(r["model_key"], {"total": 0, "success": 0, "cost": 0.0, "wall": 0.0, "in": 0, "out": 0, "cr": 0})
        a["total"] += 1; a["success"] += r["status"] == "success"
        a["cost"] += r["cost_usd"] or 0; a["wall"] += r["wall_s"] or 0
        a["in"] += r["in_tok"] or 0; a["out"] += r["out_tok"] or 0; a["cr"] += r["cache_read_tok"] or 0
    print(f"{'model_key':24} {'done':>5} {'ok':>4} {'cost$':>9} {'$/case':>7} {'avg_min':>8} {'in_tok':>11} {'cache_rd':>12} {'out_tok':>10}")
    for k, a in sorted(agg.items()):
        n = max(a['total'], 1)
        print(f"{k:24} {a['total']:5d} {a['success']:4d} {a['cost']:9.2f} {a['cost']/n:7.2f} {a['wall']/60/n:8.1f} {a['in']:11,d} {a['cr']:12,d} {a['out']:10,d}")
    print(f"\n{len(rows)} rows -> {out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "smoke"):
        s = sub.add_parser(name)
        s.add_argument("--models", default="all")
        s.add_argument("--cases", default=str(BENCH / "cases" / "cases_270.json"))
        s.add_argument("--task-ids", default="")
        s.add_argument("--limit", type=int, default=0)
        s.add_argument("--concurrency", type=int, default=0, help="per-model override; default from models.json")
        s.add_argument("--timeout-min", type=float, default=90 if name == "run" else 5)
        s.add_argument("--force", action="store_true", help="re-run cases already marked success")
        s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("status"); s.add_argument("--models", default="all")
    args = ap.parse_args()
    if args.cmd == "run": cmd_run(args)
    elif args.cmd == "smoke": cmd_run(args, smoke=True)
    else: cmd_status(args)

if __name__ == "__main__":
    main()
