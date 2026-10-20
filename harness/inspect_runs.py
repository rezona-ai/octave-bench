import json,sys
from pathlib import Path
rows=[]
for mp in sorted(Path.home().joinpath("bench/runs").glob("*/*/meta.json")):
    if "_smoke" in mp.parts: continue
    m=json.load(open(mp)); p=mp.parent/"project"
    src=[f for f in p.rglob("*") if f.is_file() and "dist" not in f.parts and f.suffix in (".ts",".tsx",".js",".jsx",".css",".html",".glsl")]
    loc=sum(len(f.read_text(errors="ignore").splitlines()) for f in src)
    dist=sum(f.stat().st_size for f in (p/"dist").rglob("*") if f.is_file()) if (p/"dist").exists() else 0
    ar=m.get("agent_result") or {}; u=ar.get("usage") or {}
    ncmd=0
    try:
        for ln in open(mp.parent/"transcript.jsonl",errors="ignore"):
            if '"command_execution"' in ln and '"item.completed"' in ln: ncmd+=1
            if '"tool_use"' in ln: ncmd+=1
    except FileNotFoundError: pass
    print(f"{m['model_key']:18} {m['task_id']:28} {m['status']:8} {m['wall_s']/60:5.1f}min src={len(src):2d} loc={loc:5d} dist={dist//1024:4d}KB tools={ncmd:3d} out_tok={u.get('output_tokens')} reason={u.get('reasoning_output_tokens')}")
    print("     final:", (ar.get("final_text") or "").replace("\n"," ")[:300])
