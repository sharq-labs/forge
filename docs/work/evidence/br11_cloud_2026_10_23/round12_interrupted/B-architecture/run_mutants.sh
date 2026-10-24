#!/bin/bash
R=/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r12/B-architecture
for m in "$@"; do
  T=$R/tree-mut
  rm -rf $T $R/pt-mut; mkdir -p $T
  git -C /home/user/forge archive a96baa6 | tar -x -C $T
  /home/user/.forge-venv/bin/python $R/mutate_r12.py $T $m
  cd $T
  PYTHONPATH=$T/src:$T timeout 900 /home/user/.forge-venv/bin/python -m pytest tests/mind benchmarks/mind_gen2_authority_v1/tests benchmarks/mind_gen2_world_v1/tests tests/test_sria_budget_ledger_identity.py -q -p no:cacheprovider -n 4 --basetemp=$R/pt-mut 2>&1 | grep -E "^FAILED|passed|failed|error" | tail -8 | sed "s/^/[$m] /"
  cd /
  rm -rf $T $R/pt-mut
done
