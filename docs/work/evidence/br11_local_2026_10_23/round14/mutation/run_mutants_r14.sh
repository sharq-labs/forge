#!/bin/bash
# Round-14 mutation run: each mutant (or "base": owners.py as committed at HEAD, with the working tree's tests) on a full
# tree copy of the working tree; the whole BR1.1 suite (base: the round-13 controls and the restated r11 control).
cd ~/forge-gen2-authority-v1
. .venv/bin/activate
OUT=~/br11-logs/mutants_r14_$(git rev-parse --short HEAD)
mkdir -p "$OUT"
export TMPDIR=/tmp/br11tmp; mkdir -p "$TMPDIR"
for m in "$@"; do
  T=/tmp/br11mut/tree; rm -rf /tmp/br11mut; mkdir -p "$T"
  { git ls-files -z; git ls-files -z --others --exclude-standard; } | tar --null -T - -cf - | tar -x -C "$T"
  if [ "$m" = base ]; then
    git show HEAD:src/engcore/mind/world/owners.py > "$T/src/engcore/mind/world/owners.py"
    TESTS="tests/mind/test_authority_review_r14.py"
  else
    python ~/br11-logs/mutate_r14_local.py "$T" "$m" || { echo "[$m] NOT APPLIED" >> "$OUT/summary.txt"; continue; }
    TESTS="tests/mind benchmarks/mind_gen2_authority_v1/tests benchmarks/mind_gen2_world_v1/tests tests/test_sria_budget_ledger_identity.py"
  fi
  ( cd "$T" && PYTHONPATH="$T/src:$T" timeout 900 python -m pytest $TESTS -q -p no:cacheprovider -n 4 --dist loadfile \
      --basetemp=/tmp/br11mut/pt > "$OUT/$m.txt" 2>&1 )
  { grep -E "^FAILED" "$OUT/$m.txt" | sed "s/^/[$m] /"; tail -n 1 "$OUT/$m.txt" | sed "s/^/[$m] /"; } >> "$OUT/summary.txt"
done
rm -rf /tmp/br11mut
echo DONE >> "$OUT/summary.txt"
