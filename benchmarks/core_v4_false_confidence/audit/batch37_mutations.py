"""Batch-37 guard mutations (I-14 part E, R-25 and finding 24): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch37_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

RO = "src/engcore/hybrid_uq/router.py"
LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch37.py"

MUTATIONS = [
    Mutation(
        "B37a", f"{RO}::HybridUQResult._require_one_truth",
        "            if local is not None and local.parameterization != \"declared\":\n",
        "            if False:\n",
        f"{T}::test_r25_renaming_the_parameterization_no_longer_switches_the_defence_off",
        "R-25's first forgery restored exactly: any label but 'declared' makes "
        "`_posterior_record_problems` return after one check, because a mapped posterior's diagnostics "
        "describe its PARENT by design -- so renaming a record to 'linear_map:forged' and dividing its "
        "covariance by 1e4 reads back SUPPORTED with sd [0.00027151, 0.00045993]. The whole defence "
        "switched off by a string"),
    Mutation(
        "B37b", f"{LG}::require_posterior_matches_calibration",
        "        if found != expected:\n",
        "        if False:\n",
        f"{T}::test_r25_moving_the_bounds_with_the_covariance_is_caught_against_the_calibration",
        "R-25's second forgery restored: the bounds move IN by sqrt(f) while the covariance is divided by f, "
        "so every bound distance in sd units survives and the re-derivation that catches a covariance-only "
        "shrink sees nothing. Declared bounds are the REQUEST's, and the calibration is the only thing that "
        "can contradict them"),
    Mutation(
        "B37c", f"{LG}",
        "    require_posterior_matches_calibration(posterior, calibration)\n",
        "    pass\n",
        f"{T}::test_r25_the_route_binds_its_own_record_to_the_calibration_it_used",
        "the rule exists and the route stops calling it, so the binding becomes one a reader may choose to "
        "apply -- and R-25's forgery is one no reader can catch from the record alone. A rule written and "
        "not reached is the shape this round keeps finding"),
    Mutation(
        "B37d", f"{LG}",
        "    require_posterior_matches_observations(posterior, observations)\n",
        "    pass\n",
        f"{T}::test_r25_a_genuine_routed_record_still_reads",
        "batch 36's observation binding stops being called by the route, which is the same defect one "
        "problem over. Named in THIS batch because both calls were added here in one place, and a guard on "
        "one of two adjacent calls leaves the other unwatched",
        expect="SURVIVED"),
    Mutation(
        "B37e", f"{RO}::routed_predictive_uncertainty",
        "    if isinstance(observations, ObservationSet) and forward is not None:\n",
        "    if False:\n",
        f"{T}::test_r27_predicting_with_the_evidence_is_supported_again",
        "the evidence is handed over and not re-run, so every grid prediction is DOWNGRADED whatever the "
        "caller supplies -- the opposite error to the audited one, and the one a fix like this most easily "
        "makes: a rule that never clears is a rule nobody can satisfy"),
    Mutation(
        "B37f", f"{RO}::routed_predictive_uncertainty",
        "        unbound.add(RouteReason.GRID_NOT_BOUND_TO_EVIDENCE)\n",
        "        pass\n",
        f"{T}::test_r27_predicting_from_a_grid_result_without_its_evidence_is_downgraded",
        "finding 24 restored exactly: a grid result predicts SUPPORTED without its evidence, so a grid "
        "computed from other data -- which `grid_predictive_uncertainty` refuses at chi-square 1064.66 -- "
        "predicts mean 2.4745 against an honest 1.9745 once wrapped in a hand-built result"),
    Mutation(
        "B37g", f"{RO}::routed_predictive_uncertainty",
        "            result.grid, predictive_table, spec, predict) | unbound\n",
        "            result.grid, predictive_table, spec, predict)\n",
        f"{T}::test_r27_predicting_from_a_grid_result_without_its_evidence_is_downgraded",
        "the reason is computed and then not carried onto the record, which is the shape I-16's round is "
        "about: a finding measured and discarded one line later"),
]

_CHANGED_FILES = (RO, LG)


def _existing():
    out = []
    for identifier, spec, old, new, attribution in M.MUTATIONS:
        if spec.partition("::")[0] not in _CHANGED_FILES:
            continue
        files = [word for word in attribution.replace(",", " ").split() if word.startswith("tests/")]
        if not files:
            continue
        out.append(Mutation(identifier, spec, old, new, files[0], f"pinned: {attribution}"))
    return out


def main() -> int:
    scratch = scratch_from_environment()
    status = run(MUTATIONS, label="BATCH37", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH37_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 37 changed ---", flush=True)
    status |= run(existing, label="BATCH37_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH37_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
