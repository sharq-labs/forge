#!/bin/bash
# usage: mutate.sh <name> <python-file-relative> <old> <new> [tests...]  (one exact replacement in the c69e579 tree copy,
# runs the BR1.1 authority suite (or the given tests), restores the file)
R=/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r10/B-architecture
T=$R/tree-c69e579
NAME=$1; FILE=$2; OLD=$3; NEW=$4; shift 4
TESTS=${@:-tests/mind benchmarks/mind_gen2_authority_v1/tests}
cp $T/$FILE $T/$FILE.orig
/home/user/.forge-venv/bin/python - "$T/$FILE" "$OLD" "$NEW" <<'PY'
import sys
p, old, new = sys.argv[1:4]
s = open(p).read()
assert s.count(old) == 1, (s.count(old), old)
open(p, "w").write(s.replace(old, new))
PY
cd $T && PYTHONPATH=$T/src:$T timeout 1500 /home/user/.forge-venv/bin/python -m pytest $TESTS -q -p no:cacheprovider -n 4 -m "not expensive" --basetemp=$R/pt-$NAME 2>&1 | grep -E "^FAILED|passed|failed|error" | sed 's/ - .*//' | head -15 > $R/mut_$NAME.txt
mv $T/$FILE.orig $T/$FILE
rm -rf $R/pt-$NAME
echo "== $NAME"; cat $R/mut_$NAME.txt
