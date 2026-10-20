#!/usr/bin/env bash
# Zip one model's run directory and upload it to GCS.
#   zip_upload.sh <gs://bucket/prefix> <model_key>...
# Zip layout: <model_key>/<task_id>/{project/,prompt.md,transcript.jsonl,stderr.log,meta.json}
set -euo pipefail
DEST="$1"; shift
export BENCH_HOME="${BENCH_HOME:-$HOME/bench}"
cd "$BENCH_HOME/runs"
for m in "$@"; do
  rm -f "/tmp/$m.zip"; zip -rq "/tmp/$m.zip" "$m"
  python3 - "$m" <<'PY'
import zipfile, os, sys
m = sys.argv[1]; z = zipfile.ZipFile(f"/tmp/{m}.zip"); n = z.namelist()
print(m, len({p.split("/")[1] for p in n if p.count("/") >= 2}), "case dirs", round(os.path.getsize(f"/tmp/{m}.zip") / 1e6), "MB")
PY
  gcloud storage cp -q "/tmp/$m.zip" "$DEST/$m.zip" && echo "uploaded $DEST/$m.zip"
done
