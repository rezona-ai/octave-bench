import json,glob,sys
from pathlib import Path
models=sys.argv[1:] or ["cc_seed_evolving","cc_glm_5_3","cc_deepseek_v4_flash"]
for m in models:
    for p in sorted(glob.glob(f"runs/{m}/*/meta.json")):
        d=json.load(open(p))
        if d["status"]=="success": continue
        proj=Path(p).parent/"project"
        src=[f for f in proj.rglob("*") if f.is_file() and "dist" not in f.parts and f.suffix in (".ts",".tsx",".js",".jsx",".html",".css")]
        loc=sum(len(f.read_text(errors="ignore").splitlines()) for f in src)
        pr=d["project"]
        print(f"{m:18} {d['task_id']:34} {d['status']:11} src_files={len(src):3d} loc={loc:5d} dist={pr['dist_index_html']} package_json={pr['package_json']}")
