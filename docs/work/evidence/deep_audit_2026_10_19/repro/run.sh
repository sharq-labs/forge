#!/usr/bin/env bash
# Usage: run.sh <id> <script.py>   -- runs one reproduction under the isolation contract and records evidence.
set -u
ID="$1"; SCRIPT="$2"
S="$(cd "$(dirname "$0")" && pwd)"
REPO=/d/forge-main-337519d1
PY="C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe"
pre_head=$(git -C "$REPO" rev-parse HEAD)
pre_status=$(git -C "$REPO" status --porcelain | tr '\n' '|')
pre_hash=$(cd "$REPO" && git ls-files -z src tests benchmarks tools | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
cd "$S"
start=$(date +%s.%N)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$(cygpath -w "$S/bootstrap");D:/forge-main-337519d1/src;D:/forge-main-337519d1" \
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
timeout 600 "$PY" -B "$SCRIPT" > "$S/$ID.out" 2> "$S/$ID.err"
code=$?
end=$(date +%s.%N)
post_head=$(git -C "$REPO" rev-parse HEAD)
post_status=$(git -C "$REPO" status --porcelain | tr '\n' '|')
post_hash=$(cd "$REPO" && git ls-files -z src tests benchmarks tools | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
pyc=$(find "$REPO/src" "$REPO/benchmarks" -name '*.pyc' -newer "$S/$SCRIPT" 2>/dev/null | wc -l)
wall=$(awk "BEGIN{print $end-$start}")
cat > "$S/$ID.json" <<EOF
{"id": "$ID", "argv": ["$PY", "-B", "$SCRIPT"], "cwd": "$S",
 "env": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "bootstrap;D:/forge-main-337519d1/src;D:/forge-main-337519d1", "BLAS_threads": "1"},
 "exit_code": $code, "wall_seconds": $wall,
 "stdout_sha256": "$(sha256sum "$S/$ID.out" | cut -d' ' -f1)", "stderr_sha256": "$(sha256sum "$S/$ID.err" | cut -d' ' -f1)",
 "script_sha256": "$(sha256sum "$S/$SCRIPT" | cut -d' ' -f1)",
 "source": {"head_before": "$pre_head", "head_after": "$post_head", "status_before": "$pre_status", "status_after": "$post_status",
            "tracked_hash_before": "$pre_hash", "tracked_hash_after": "$post_hash", "new_pyc_in_repo": $pyc}}
EOF
echo "exit=$code wall=${wall}s hash_unchanged=$([ "$pre_hash" = "$post_hash" ] && echo yes || echo NO) new_pyc=$pyc"
cat "$S/$ID.out"; echo "--- stderr ---"; tail -20 "$S/$ID.err"
