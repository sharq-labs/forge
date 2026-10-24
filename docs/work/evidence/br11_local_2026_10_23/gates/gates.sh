#!/bin/bash
# BR1.1 gates on one tree (PROGRESS GEN2-BR1.1 items 5-7 and 10): FAST, regression pack, guard suites, affected
# expensive minus campaign.  Usage: gates.sh <tree> <label>.  Uses the branch clone's .venv; the tree's own src first.
D=$1; L=$2
. ~/forge-gen2-authority-v1/.venv/bin/activate
OUT=~/br11-logs/gates_$L; rm -rf "$OUT"; mkdir -p "$OUT"
export TMPDIR=/tmp/br11gt_$L; rm -rf "$TMPDIR"; mkdir -p "$TMPDIR"
export PYTHONPATH="$D/src:$D"
cd "$D"
{ echo "tree $D HEAD $(git rev-parse HEAD)"; git status --short | head; python -VV; } > "$OUT/env.txt"
run() { local name=$1; shift; local t0=$(date +%s); "$@" > "$OUT/$name.txt" 2>&1; echo "$name exit=$? wall=$(( $(date +%s)-t0 ))s :: $(tail -n 1 "$OUT/$name.txt")" >> "$OUT/summary.txt"; }
run fast python -m pytest -q -n 4 --dist loadfile -m "not expensive" -p no:cacheprovider -rfE --basetemp="$TMPDIR/fast"
grep -E "^(FAILED|ERROR) " "$OUT/fast.txt" | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u > "$OUT/fast_failing_ids.txt"
run regression python tools/forge_check.py --regression
run guards python -m pytest tests/mind tests/test_blind_challenge_guards.py tests/test_core_api_layering.py \
  tests/test_core_guards.py tests/test_core_semantic_invariants.py tests/test_repository_architecture.py \
  tests/test_trust_boundary_*.py tests/test_sria_m5_campaign.py tests/test_sria_campaign_persistence_v03_adversarial.py \
  tests/test_sria_budget_ledger_identity.py -q -n 4 -p no:cacheprovider -rfE --basetemp="$TMPDIR/guards"
grep -E "^(FAILED|ERROR) " "$OUT/guards.txt" | sort > "$OUT/guards_failing.txt"
run expensive python -m pytest \
  benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_careful_identifies_synthetic_pulses_and_recovers_the_parameters \
  benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_mind_runs_end_to_end_on_synthetic_pulses_and_its_traces_replay \
  benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_no_arm_supports_identifiability_when_tau_is_far_outside_the_window \
  benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates \
  tests/domains/kinetics/test_cstr_domain.py tests/systems/aerospace/test_multirotor_mvr0.py \
  tests/systems/aerospace/test_multirotor_mvr1.py tests/test_electrical_v01_demo.py tests/test_heterogeneous_ngspice.py \
  tests/test_sria_e1_electrical.py tests/test_sria_e2_model_adequacy.py tests/test_sria_e3_adequacy_obligation.py \
  tests/test_sria_v01_certification_path.py tests/test_thermal_t1_fidelity_inference.py \
  -m "expensive and not campaign" -q -n 3 --dist loadfile -p no:cacheprovider -rfE --basetemp="$TMPDIR/exp"
grep -E "^(FAILED|ERROR) " "$OUT/expensive.txt" | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u > "$OUT/expensive_failing_ids.txt"
git status --short > "$OUT/status_after.txt"
rm -rf "$TMPDIR"
echo DONE >> "$OUT/summary.txt"
