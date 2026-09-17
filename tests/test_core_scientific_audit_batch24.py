"""Batch 24 of the 2026-09-16 core re-audit: agreement between two solvers is verification (I-12 part A).

**R-39.** `VALIDATION_LEVELS` puts `CROSS_SOLVER_VALIDATED` beside BENCHMARK_VALIDATED and
EXPERIMENTALLY_VALIDATED as a level that compares a result with something outside the model that produced
it, and `evidence_basis` returns VALIDATED whenever any of them is attained. Agreement between two solvers
of ONE declared model does not compare it with anything outside itself. So a DC result whose only other
levels are dimensional validity and convergence moved from VERIFICATION_ONLY to VALIDATED the moment a
cross-solver check was attached -- and a circuit declared with a wrong resistor value read VALIDATED,
because both solvers agree about the wrong model. All three contributing DC models report
`validation_status` SELF_CONSISTENT in the same report.

The classification contradicted three statements the code already makes about itself: `evidence_basis`'s own
docstring ("compare it with something outside itself"), `scientific/consensus.py` (two routes may "realize
the same mathematical formulation" and still count as independent, because only shared ARITHMETIC is
excluded), and `domains/electrical/dc/models.py` (the KCL/Ohm/source relations are SELF_CONSISTENT, "not
BENCHMARK_VALIDATED ... certainly not EXPERIMENTALLY_VALIDATED"). This removes the contradiction rather than
adding a judgement.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH24_THRESHOLD_PROTOCOL.json`. No threshold: a
classification, and an import-time completeness check over it.
"""

from __future__ import annotations

import pytest

from engcore.scientific.results import validation as V
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    route_declarations_for_tests,
)
from engcore.scientific.results.validation import (
    VALIDATION_LEVELS,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)

CONVERGED = ValidationCheck("mesh_convergence", ValidationOutcome.PASS,
                            establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-4, tolerance=1e-3)
def _cross_solver_check():
    """A REAL cross-solver check, from a real consensus.

    A hand-built `ValidationCheck(establishes=CROSS_SOLVER_VALIDATED)` is already refused -- VAL-01 holds the
    three issued levels to their issuer's own record in the evidence -- so this reproduction cannot forge
    one, and should not: what R-39 is about is the KIND a genuinely issued level is counted as. The fixture
    is `tests/test_cross_solver_consensus.py`'s own, whose routes are PINNED in
    `tests/route_declarations_for_tests.py`, because a route nothing pinned earns nothing either.
    """
    from test_cross_solver_consensus import ALPHA, BETA, _consensus, _route

    consensus = _consensus((_route("a", ALPHA, "a:rhs"), _route("b", BETA, "b:rhs")),
                           {"a": {"x": 1.0}, "b": {"x": 1.0}})
    check = consensus.to_check(name="cross_solver_agreement")
    assert check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED, check.detail
    return check


def _symbol(name):
    """A named constant, asserted rather than assumed, so a reproduction fails on its assertion."""
    value = getattr(V, name, None)
    assert value is not None, f"engcore.scientific.results.validation.{name} is what part A adds"
    return value


# =====================================================================
# R-39: the classification
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_cross_solver_agreement_is_not_a_validation_level():
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in VALIDATION_LEVELS
    assert ValidationLevel.CROSS_SOLVER_VALIDATED in _symbol("VERIFICATION_LEVELS")


@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_both_kinds_are_named_and_every_level_is_in_exactly_one():
    """One kind was a set and the other was "the rest", so a level added later was silently verification."""
    verification = _symbol("VERIFICATION_LEVELS")
    assert not (set(verification) & set(VALIDATION_LEVELS)), sorted(
        level.value for level in set(verification) & set(VALIDATION_LEVELS))
    classified = set(verification) | set(VALIDATION_LEVELS)
    unclassified = {level for level in ValidationLevel if level is not ValidationLevel.UNVERIFIED} - classified
    assert unclassified == set(), sorted(level.value for level in unclassified)
    assert ValidationLevel.UNVERIFIED not in classified


@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_a_report_whose_validating_evidence_is_agreement_between_solvers_is_verification_only():
    """The audited reproduction, at the core: the same report with and without the consensus check."""
    without = ValidationReport(checks=(CONVERGED,))
    with_consensus = ValidationReport(checks=(CONVERGED, _cross_solver_check()))
    assert without.evidence_basis == "VERIFICATION_ONLY"
    assert with_consensus.evidence_basis == "VERIFICATION_ONLY", with_consensus.evidence_basis
    # the level is still ATTAINED and still says what it says; what changed is the KIND it is counted as
    assert ValidationLevel.CROSS_SOLVER_VALIDATED in with_consensus.attained_levels


@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_the_mcp_side_derives_the_same_word_from_the_same_rule():
    from engcore.mcp.evidence import evidence_basis_of

    assert evidence_basis_of({ValidationLevel.CROSS_SOLVER_VALIDATED}) == "VERIFICATION_ONLY"
    assert evidence_basis_of({ValidationLevel.CROSS_SOLVER_VALIDATED,
                              ValidationLevel.NUMERICALLY_CONVERGED}) == "VERIFICATION_ONLY"


@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_demanding_validation_is_no_longer_met_by_agreement_between_two_solvers():
    """`required_evidence_basis='VALIDATED'` meant something and was being met by something else."""
    from engcore.mcp.evidence import EVIDENCE_BASIS_ORDER, evidence_basis_of

    attained = {ValidationLevel.CROSS_SOLVER_VALIDATED, ValidationLevel.NUMERICALLY_CONVERGED}
    assert EVIDENCE_BASIS_ORDER[evidence_basis_of(attained)] < EVIDENCE_BASIS_ORDER["VALIDATED"]


@pytest.mark.xfail(strict=True, reason="I-12 part A not implemented yet (batch 24 preregistration)")
def test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers():
    from engcore.mcp.server import _BASIS_MEANS

    means = _BASIS_MEANS["VERIFICATION_ONLY"].lower()
    assert "solver" in means, _BASIS_MEANS["VERIFICATION_ONLY"]


# Already held at the baseline and unmarked at preregistration: it is the no-regression half. A comparison
# against something outside the model -- a benchmark dataset or an experiment -- is still VALIDATED, and a
# reclassification that moved those too would be a different and wrong change.
def test_r39_a_comparison_with_something_outside_the_model_is_still_validated():
    from engcore.mcp.evidence import evidence_basis_of

    assert ValidationLevel.EXPERIMENTALLY_VALIDATED in VALIDATION_LEVELS
    assert ValidationLevel.BENCHMARK_VALIDATED in VALIDATION_LEVELS
    # over the rule rather than over a report, because neither level can be ISSUED in this tree:
    # `oracles._TRUSTED_ORACLE_DECLARATIONS` is empty, so a check claiming one names no verifiable issuer
    # and a report carrying it is refused. That is the residual this batch's protocol states -- after the
    # reclassification, VALIDATED is unreachable in production, which is the honest state of the tree.
    for level in (ValidationLevel.EXPERIMENTALLY_VALIDATED, ValidationLevel.BENCHMARK_VALIDATED):
        assert evidence_basis_of({level, ValidationLevel.NUMERICALLY_CONVERGED}) == "VALIDATED"
