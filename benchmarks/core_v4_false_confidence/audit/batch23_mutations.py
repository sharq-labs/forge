"""Batch-23 guard mutations (I-13 part B, a routed prediction's own numbers): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch23_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

PR = "src/engcore/hybrid_uq/predictive.py"
RT = "src/engcore/hybrid_uq/router.py"
CS = "src/engcore/studies/calibration_study.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch23.py"
GR = "tests/hybrid_uq/test_audit_hybrid_grid_route.py"
B17 = "tests/test_core_scientific_audit_batch17.py"

MUTATIONS = [
    # --- R-37: the nonlinearity, per spec and finite ---
    Mutation(
        "B23a", f"{PR}::linearized_predictive_uq",
        "                nonlinearity = np.maximum(nonlinearity, relative)\n",
        "                nonlinearity = np.full(len(specs), float(np.max(relative)))\n",
        f"{T}::test_r37_each_record_carries_its_own_nonlinearity",
        "R-37, the audited case restored exactly: the nonlinearity is pooled over the call again, so an "
        "exactly affine prediction records the curved one's number and its read-back rule derives "
        "PREDICTIVE_NONLINEAR for it from someone else's curvature"),
    Mutation(
        "B23b", f"{PR}::linearized_predictive_uq",
        "    if nonlinearity is not None and not np.all(np.isfinite(nonlinearity)):\n",
        "    if False:\n",
        f"{T}::test_r37_a_prediction_with_no_parameter_uncertainty_that_the_probes_move_is_refused",
        "a prediction whose reported interval is a point and whose probes have already shown that point to "
        "be wrong is emitted again -- nonlinearity inf, parameter sd 0, DOWNGRADED"),
    Mutation(
        "B23c", f"{PR}::RoutedPredictiveUncertainty._require_numbers_agree",
        "                if not math.isfinite(float(nonlinearity)):\n",
        "                if False:\n",
        f"{T}::test_r37_a_record_carrying_a_nonfinite_nonlinearity_is_refused_on_read",
        "the read-back rule stops refusing an infinite nonlinearity, so a record can carry one however the "
        "route that wrote it behaved -- the emission rule and the read-back rule must be the same rule"),
    Mutation(
        "B23d", f"{PR}::linearized_predictive_uq",
        "        measured = None if nonlinearity is None else float(nonlinearity[i])\n",
        "        measured = None if nonlinearity is None else float(np.max(nonlinearity))\n",
        f"{T}::test_r37_each_record_carries_its_own_nonlinearity",
        "the per-spec array is computed and then the pooled maximum is written onto every record, which is "
        "the defect with the fix in place above it"),
    # --- R-23: the predictive table, checked against predict ---
    Mutation(
        "B23e", f"{PR}::_table_reasons",
        "    _require_table_is_the_model(posterior, predictive_table, spec, predict)\n",
        "    pass\n",
        f"{T}::test_r23_a_table_of_twice_the_model_is_refused_when_predict_is_passed",
        "R-23, the audited case restored exactly: the table is never compared with the predict passed beside "
        "it, so a table of twice the model reports a SUPPORTED mean of 3.949 against the honest 1.975"),
    Mutation(
        "B23f", f"{PR}::_table_reasons",
        "    if predict is None:\n        return {RouteReason.PREDICTIVE_TABLE_NOT_CHECKED}\n",
        "    if predict is None:\n        return set()\n",
        f"{T}::test_r23_a_table_nobody_checked_says_so",
        "the spot-check is silenced by omitting an optional argument and the record says nothing about it -- "
        "which is the shape of R-12, the problem part A of this same improvement closed"),
    Mutation(
        "B23g", f"{PR}::_require_table_is_the_model",
        "        if not abs(stated - fresh) <= tolerance:\n",
        "        if False:\n",
        f"{T}::test_r23_the_tolerance_is_roundoff_and_a_disagreement_of_one_part_in_a_million_is_refused",
        "the comparison is made and then not acted on, so a table one part in a million away from the model "
        "is reported as the model"),
    Mutation(
        "B23h", f"{PR}::_require_table_is_the_model",
        "        tolerance = TABLE_ROUNDOFF_FACTOR * float(np.finfo(float).eps) * max(abs(stated), abs(fresh), 0.0)\n",
        "        tolerance = 1.0e-3 * max(abs(stated), abs(fresh), 0.0)\n",
        f"{T}::test_r23_the_tolerance_is_roundoff_and_a_disagreement_of_one_part_in_a_million_is_refused",
        "the tolerance becomes a THRESHOLD rather than roundoff, so a table that is wrong by a tenth of a "
        "percent passes -- and `predict` is deterministic, so the only admissible disagreement is roundoff"),
    Mutation(
        "B23i", f"{PR}::_spot_check_nodes",
        "    heaviest = int(np.argmax(np.where(usable, weights, -np.inf)))\n",
        "    heaviest = int(np.argmin(np.where(usable, weights, np.inf)))\n",
        f"{T}::test_r23_the_checked_nodes_are_the_ones_the_reported_numbers_stand_on",
        "the LIGHTEST usable node is checked instead of the heaviest, so the node the reported mean is "
        "dominated by is the one node the check never reads"),
    Mutation(
        "B23j", f"{PR}::_spot_check_nodes",
        "    usable = (np.asarray(posterior.admissible_mask, dtype=bool)\n"
        "              & np.asarray(predictive_table.admissible_mask, dtype=bool)\n"
        "              & (weights > 0.0))\n",
        "    usable = np.ones(len(weights), dtype=bool)\n",
        f"{T}::test_r23_the_checked_nodes_are_the_ones_the_reported_numbers_stand_on",
        "inadmissible and zero-weight nodes enter the choice, so the extreme-value nodes are the table's "
        "padding for refused points rather than anything the reported interval stands on"),
    Mutation(
        "B23k", f"{RT}::routed_predictive_uncertainty",
        "        found = _prediction_domain_reasons(spec, calibration_observations) | _table_reasons(\n"
        "            result.grid, predictive_table, spec, predict)\n",
        "        found = _prediction_domain_reasons(spec, calibration_observations)\n",
        f"{T}::test_r23_the_router_checks_the_table_it_is_handed_beside_a_predict",
        "the ROUTER goes back to accepting `predict` and using it only on the local path, which is where the "
        "audit found this: a grid result read its numbers out of the table with the model sitting unused in "
        "the same call"),
    Mutation(
        "B23l", f"{CS}::_routed",
        "        predict=predict,\n",
        "        predict=None,\n",
        f"{B17}::test_r02_a_predictive_decomposition_carries_its_route_claim_and_reasons",
        "the PRODUCTION study stops handing its own forward model to the check, so every production "
        "predictive record reads PREDICTIVE_TABLE_NOT_CHECKED -- and the study BUILDS the table from that "
        "model, so there is nothing to withhold. This is the reach half of R-23: the rule is on the one "
        "production path to a predictive interval"),
]

_CHANGED_FILES = (PR, RT, CS)


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
    status = run(MUTATIONS, label="BATCH23", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH23_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 23 changed ---", flush=True)
    status |= run(existing, label="BATCH23_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH23_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
