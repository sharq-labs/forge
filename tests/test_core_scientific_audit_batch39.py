"""Core re-audit 2026-09-16, batch 39: a tolerance bounds a magnitude, and a critic says which check did not run.

Problems R-46 (the audit's finding 54) and R-45's third fix direction (finding 87), improvement I-20 part A
of three, under benchmarks/core_v4_false_confidence/BATCH39_THRESHOLD_PROTOCOL.json.

The module's own docstring already describes R-46's defect -- "a check reporting PASS with residual=10.0
beside tolerance=1e-6, seven orders outside its own bound" -- and it comes back with a minus sign, because
the comparison reads the signed number rather than the distance.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
    comparison_met_its_bound,
)


def _check(**kw):
    fields = {"name": "analytic_invariant_agreement", "outcome": ValidationOutcome.PASS,
              "residual": 1.0e-12, "tolerance": 1.0e-6,
              "establishes": ValidationLevel.NUMERICALLY_CONVERGED}
    fields.update(kw)
    return ValidationCheck(**fields)


# ---------------------------------------------------------------------------
# a_tolerance_bounds_a_magnitude
# ---------------------------------------------------------------------------
def test_r46_a_residual_outside_its_bound_on_the_high_side_is_already_refused():
    """The premise: the rule works, in the direction the audit's first reproduction took."""
    with pytest.raises(ScientificValidationError, match="did not succeed"):
        _check(residual=10.0)


def test_r46_the_rule_itself_reads_the_distance_not_the_signed_number():
    assert comparison_met_its_bound(1.0e-12, 1.0e-6) is True
    assert comparison_met_its_bound(10.0, 1.0e-6) is False
    assert comparison_met_its_bound(-10.0, 1.0e-6) is False, (
        "a residual of -10 stands 10 away from its reference, and a tolerance bounds that distance")
    assert comparison_met_its_bound(None, 1.0e-6) is None
    assert comparison_met_its_bound(float("nan"), 1.0e-6) is False


def test_r46_a_pass_whose_residual_misses_its_bound_from_below_is_refused():
    """The audited construction: the same check with a minus sign was built and earned its level."""
    with pytest.raises(ScientificValidationError, match="did not succeed"):
        _check(residual=-10.0)


def test_r46_a_level_declaring_warning_is_held_to_the_distance_too():
    with pytest.raises(ScientificValidationError, match="did not succeed"):
        _check(outcome=ValidationOutcome.WARNING, residual=-10.0)


def test_r46_a_negative_residual_inside_its_bound_still_passes():
    """The control: reading the distance is not reading the absolute value as a failure."""
    check = _check(residual=-1.0e-12)
    assert check.passed and check.earns_its_level and check.outcome_is_earned


# ---------------------------------------------------------------------------
# a_negative_tolerance_is_not_a_bound
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("outcome", [ValidationOutcome.PASS, ValidationOutcome.WARNING,
                                     ValidationOutcome.FAIL, ValidationOutcome.NOT_RUN],
                         ids=["pass", "warning", "fail", "not_run"])
def test_r46_a_negative_tolerance_is_refused_for_every_outcome(outcome):
    establishes = ValidationLevel.NUMERICALLY_CONVERGED if outcome is ValidationOutcome.PASS else None
    with pytest.raises(ScientificValidationError, match="tolerance"):
        _check(outcome=outcome, residual=-3.0, tolerance=-1.0, establishes=establishes)


def test_r46_the_audited_negative_tolerance_construction_no_longer_earns_a_level():
    with pytest.raises(ScientificValidationError, match="tolerance"):
        _check(residual=-3.0, tolerance=-1.0)


def test_r46_a_zero_tolerance_is_still_a_bound():
    """The control: exact agreement is a real bound and 0 is not negative."""
    assert _check(residual=0.0, tolerance=0.0).passed


# ---------------------------------------------------------------------------
# a_critic_says_which_checks_did_not_run
# ---------------------------------------------------------------------------
def _result_with_an_inapplicable_check():
    import tests.test_sria_m3_assurance as T

    result = T.good_result("res-B39")
    report = ValidationReport(checks=(
        *result.validation.checks,
        ValidationCheck(name="voltage_source_relation", outcome=ValidationOutcome.NOT_RUN,
                        detail="the circuit has no voltage source"),
    ))
    return dataclasses.replace(result, validation=report)


def _status_detail(result):
    from engcore.sria.assurance.critics import NumericalCritic

    assessment = NumericalCritic().assess(result, assessment_id="as-b39")
    record = next(c for c in assessment.checks if c.name == "validation_report_status")
    return record


def test_r45_a_report_whose_unrun_check_did_not_apply_is_not_a_report_nobody_ran():
    result = _result_with_an_inapplicable_check()
    assert result.validation.status is ValidationOutcome.NOT_RUN
    record = _status_detail(result)
    assert record.detail != "validation was never run", (
        "five checks ran and passed and one did not apply, and the critic says nobody looked")
    assert "voltage_source_relation" in record.detail, (
        f"the detail does not name the check that did not run: {record.detail!r}")


def test_r45_a_report_with_no_checks_at_all_still_says_validation_was_never_run():
    """The control: the old sentence is true of the report it was written for."""
    from engcore.scientific.results.validation import unverified_report

    import tests.test_sria_m3_assurance as T

    result = dataclasses.replace(T.good_result("res-B39b"), validation=unverified_report())
    record = _status_detail(result)
    assert "never run" in record.detail, record.detail
