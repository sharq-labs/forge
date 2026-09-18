"""Batch-20 guard mutations (I-08 part A, the route's independence from declared units): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch20_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch20.py"
C = "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py"
LR = "tests/hybrid_uq/test_hybrid_uq_local_route.py"

MUTATIONS = [
    # --- R-16: the probe basis ---
    Mutation(
        "B20a", f"{LG}::local_gaussian_posterior",
        "    lam, vec = _invariant_basis(cov)\n",
        "    lam, vec = np.linalg.eigh(cov)\n",
        f"{C}::test_r16_restating_a_parameter_in_another_unit_changes_no_claim_and_no_diagnostic",
        "R-16, the audited case restored exactly: the probe basis goes back to eigh(cov) in declared units, "
        "and the same model and data are SUPPORTED in one unit and REFUSED in another"),
    Mutation(
        "B20b", f"{LG}::_invariant_basis",
        "    correlation = cov / np.outer(safe, safe)\n",
        "    correlation = cov\n",
        f"{T}::test_r16_the_basis_is_the_same_points_under_a_diagonal_reparameterization",
        "the correlation matrix stops being formed, so the eigenbasis is the covariance's again and rotates "
        "under a per-parameter unit change -- the defect, reached by another route"),
    Mutation(
        "B20c", f"{LG}::_invariant_basis",
        "    return mu, sd[:, None] * w\n",
        "    return mu, w\n",
        f"{T}::test_r16_every_probe_axis_has_mahalanobis_length_one",
        "the correlation eigenvectors are returned unscaled, so the probes no longer have Mahalanobis length "
        "1 and PROBE_SD ** 2 is not what their rise should be compared with"),
    Mutation(
        "B20d", f"{LG}::_invariant_basis",
        "    sd = np.sqrt(np.clip(np.diag(cov), 0.0, None))\n",
        "    sd = np.ones(len(cov))\n",
        f"{T}::test_r16_the_basis_is_the_same_points_under_a_diagonal_reparameterization",
        "the marginal sds drop out of the scaling, so `correlation` is the covariance again and the basis is "
        "eigh(cov)'s -- the defect exactly. Repointed: it first named the uncorrelated-posterior guard, and "
        "SURVIVED there, because for a DIAGONAL covariance the two formulas coincide -- which is the property "
        "that guard exists to pin and the reason it cannot see this mutation"),
    Mutation(
        "B20e", f"{LG}::local_gaussian_posterior",
        "        axis = math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k]\n",
        "        _l, _v = np.linalg.eigh(cov)\n        axis = math.sqrt(max(float(_l[k]), 0.0)) * _v[:, k]\n",
        f"{T}::test_r16_restating_a_unit_moves_no_dimensionless_diagnostic",
        "the TAIL probes go back to eigh(cov) in declared units while the nonlinearity probes stay "
        "invariant, so minimum_tail_rise_ratio moves under a pure unit restatement again. Repointed: the "
        "first form sent the tail probes to the declared COORDINATE axes, which SURVIVED -- and rightly, "
        "because sd_k * e_k is itself invariant under a per-parameter rescaling. The defect is eigh(cov), "
        "not off-eigenbasis"),
    # --- R-26: the scaling downgrade ---
    Mutation(
        "B20f", f"{LG}",
        "POORLY_SCALED_CONDITION_LIMIT = math.sqrt(NONLINEARITY_DOWNGRADE) * NUMERICAL_CONDITION_LIMIT",
        "POORLY_SCALED_CONDITION_LIMIT = NUMERICAL_CONDITION_LIMIT",
        f"{T}::test_r26_the_limit_is_the_two_constants_this_module_already_declares",
        "the downgrade limit is raised onto the refusal, so the band between 'no correct digits' and 'the "
        "error the route already accepts' has nothing in it -- an equilibrated condition of 4e7 reads clean"),
    Mutation(
        "B20g", f"{LG}::local_gaussian_posterior",
        "    if condition > POORLY_SCALED_CONDITION_LIMIT:\n        downgrades.append(RouteReason.POORLY_SCALED_PARAMETERIZATION)\n",
        "    if raw_condition > NUMERICAL_CONDITION_LIMIT:\n        downgrades.append(RouteReason.POORLY_SCALED_PARAMETERIZATION)\n",
        f"{C}::test_r26_a_smaller_unit_does_not_downgrade_an_exactly_gaussian_result",
        "R-26, the audited case restored exactly: the downgrade goes back onto the RAW condition number, and "
        "a slope declared in nanovolts downgrades an exactly Gaussian result"),
    Mutation(
        "B20h", f"{LG}::local_gaussian_posterior",
        "    if condition > POORLY_SCALED_CONDITION_LIMIT:\n",
        "    if False:\n",
        f"{T}::test_r26_an_ill_conditioned_parameterization_is_downgraded_end_to_end",
        "the scaling downgrade is never emitted at all, so the route stops saying anything about a "
        "parameterization whose conditioning costs the covariance a tenth of its digits. It SURVIVED its "
        "first target -- a test that asserts the downgrade is ABSENT on a well-conditioned fit cannot see "
        "the rule deleted -- and every other R-26 guard works on a hand-edited record. The quartic case "
        "added for it routes a genuinely ill-conditioned problem and reads what the route said; the "
        "read-back rule then refuses the record the mutated route writes, which is the pair the fix is"),
    Mutation(
        "B20i", f"{LG}::_require_reasons_follow_measurements",
        "        if condition > POORLY_SCALED_CONDITION_LIMIT:\n            downgrades.add(RouteReason.POORLY_SCALED_PARAMETERIZATION)\n",
        "        if False:\n            downgrades.add(RouteReason.POORLY_SCALED_PARAMETERIZATION)\n",
        f"{T}::test_r26_an_equilibrated_condition_above_the_limit_must_carry_the_downgrade",
        "the READ-BACK rule stops re-deriving the scaling downgrade, so a record with an equilibrated "
        "condition of 3e7 and no downgrade reads back as SUPPORTED -- the emission rule and the read-back "
        "rule must be the same rule"),
    Mutation(
        "B20j", f"{LG}::_require_reasons_follow_measurements",
        '        if math.isnan(raw):\n            problems.append("the raw Jacobian condition is not recorded")\n',
        "        if False:\n            pass\n",
        f"{T}::test_r26_a_record_that_does_not_carry_its_raw_condition_is_refused",
        "a non-refused record may omit the raw condition number, which the route computes on every "
        "non-refused path -- a record that does not carry a number it claims to record"),
    Mutation(
        "B20k", f"{LG}",
        '        "at_bound_relative": AT_BOUND_RELATIVE, "numerical_condition_limit": NUMERICAL_CONDITION_LIMIT,\n',
        '        "at_bound_relative": AT_BOUND_RELATIVE, "numerical_condition_limit": NUMERICAL_CONDITION_LIMIT,\n'
        '        "poorly_scaled_condition_limit": POORLY_SCALED_CONDITION_LIMIT,\n',
        f"{T}::test_r26_the_recorded_thresholds_map_gains_no_key",
        "the new constant is added to the SERIALIZED thresholds map, which is re-derived exactly on "
        "read-back -- every record ever written under hybrid_uq.route_diagnostics/2 stops reading back. The "
        "one compatibility decision this batch makes, mutated in the direction that breaks it"),
]

_CHANGED_FILES = (LG,)


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
    status = run(MUTATIONS, label="BATCH20", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH20_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 20 changed ---", flush=True)
    status |= run(existing, label="BATCH20_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH20_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
