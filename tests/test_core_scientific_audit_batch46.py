"""Core re-audit 2026-09-16, batch 46: admission is bound to the source result it is about.

Problem R-71 (the audit's finding 98), improvement I-28 part C of three, under
benchmarks/core_v4_false_confidence/BATCH46_THRESHOLD_PROTOCOL.json.

The boundary that is supposed to stop a single usable solve from certifying its own numerical adequacy checks
only a report object the caller hands over, and that report is never linked to the source. So an iterative
solve whose OWN report claims NUMERICALLY_CONVERGED is admitted as "analytic" if the caller attaches a report
that reaches DIMENSIONALLY_VALID; the numerical route accepts the source's own single-solve report as the
sequence's; a source with no models crosses either route; and `binding_ref` binds nothing.

Recorded as strict xfails in commit 86cbdc26, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import dataclasses

import pytest

import tests.test_core_trust_closure as T
from engcore.inference.admissibility import (
    AdmissibleAnalyticPrediction,
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
)
from engcore.scientific import ConvergenceState, ValidationLevel
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)

BINDING = "synthetic.admission@1"
SEQUENCE = ValidationReport(checks=(ValidationCheck(
    name="tolerance_ladder", outcome=ValidationOutcome.PASS,
    establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-10, tolerance=1e-8,
    evidence=("run:ladder-1", "run:ladder-2")),))
NUMERICAL_REPORT = ValidationReport(checks=(ValidationCheck(
    name="linear_system_residual", outcome=ValidationOutcome.PASS,
    establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-12, tolerance=1e-9),))


def _source(**overrides):
    source = T._source(None)
    return dataclasses.replace(source, **overrides) if overrides else source


def _analytic(source=None, **overrides):
    fields = dict(
        prediction_id="p", domain="synthetic", adapter_id="adapter", binding_ref=BINDING,
        verification_ref="verification:p", source_result=source if source is not None else _source(),
        observable_names=("y",), validation=T._DIMENSIONAL,
        analytic_basis="closed form y = f(x) for this fixture",
    )
    fields.update(overrides)
    return AdmissibleAnalyticPrediction(**fields)


def _numerical(source=None, **overrides):
    fields = dict(
        prediction_id="p", domain="synthetic", adapter_id="adapter", binding_ref=BINDING,
        verification_ref="verification:p", source_result=source if source is not None else _source(),
        observable_names=("y",), sequence_validation=SEQUENCE,
    )
    fields.update(overrides)
    return AdmissibleNumericalPrediction(**fields)


# ---------------------------------------------------------------------------
# the_analytic_route_reads_the_sources_own_record
# ---------------------------------------------------------------------------
def test_r71_an_honest_analytic_prediction_is_unchanged():
    """The control: a closed-form source with nothing to converge still crosses."""
    assert _analytic().admission_route == "analytic"


def test_r71_an_analytic_prediction_over_an_iterative_solve_is_refused():
    """The audited case: the source's OWN report claims NUMERICALLY_CONVERGED and the route admits it."""
    source = _source(validation=NUMERICAL_REPORT, convergence=ConvergenceState.CONVERGED)
    assert source.validation.claims(ValidationLevel.NUMERICALLY_CONVERGED)
    with pytest.raises(InferenceAdmissibilityError, match="converge"):
        _analytic(source)


def test_r71_an_analytic_prediction_over_a_converged_source_is_refused_even_without_the_level():
    """A converged solve is an iterative solve whether or not its report says so."""
    source = _source(convergence=ConvergenceState.CONVERGED)
    with pytest.raises(InferenceAdmissibilityError, match="converge|NOT_APPLICABLE"):
        _analytic(source)


def test_r71_the_dimensional_level_has_to_be_in_the_sources_own_report():
    source = _source(validation=ValidationReport(checks=(ValidationCheck(
        name="dimensional_consistency", outcome=ValidationOutcome.NOT_RUN,
        detail="nobody checked the dimensions of this fixture"),)))
    with pytest.raises(InferenceAdmissibilityError, match="DIMENSIONALLY_VALID|source"):
        _analytic(source)


# ---------------------------------------------------------------------------
# a_sequence_report_is_not_the_single_solves_own_report
# ---------------------------------------------------------------------------
def test_r71_an_honest_numerical_prediction_is_unchanged():
    assert _numerical().admission_route == "numerical"


def test_r71_the_sources_own_report_is_not_its_sequence_report():
    """As audited: the numerical route accepts the source's own single-solve report."""
    source = _source(validation=NUMERICAL_REPORT, convergence=ConvergenceState.CONVERGED)
    with pytest.raises(InferenceAdmissibilityError, match="own|single"):
        _numerical(source, sequence_validation=source.validation)


def test_r71_a_sequence_report_names_at_least_two_members():
    one_member = ValidationReport(checks=(ValidationCheck(
        name="tolerance_ladder", outcome=ValidationOutcome.PASS,
        establishes=ValidationLevel.NUMERICALLY_CONVERGED, residual=1e-10, tolerance=1e-8,
        evidence=("run:ladder-1",)),))
    with pytest.raises(InferenceAdmissibilityError, match="sequence|member"):
        _numerical(sequence_validation=one_member)


# ---------------------------------------------------------------------------
# an_admitted_source_names_at_least_one_model
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("route", ["analytic", "numerical"])
def test_r71_a_source_that_names_no_model_is_refused(route):
    """As audited: the applicability loop iterates over result.models, which is empty."""
    source = _source(models=(), validity_not_assessed={})
    builder = _analytic if route == "analytic" else _numerical
    with pytest.raises(InferenceAdmissibilityError, match="model"):
        builder(source)


# ---------------------------------------------------------------------------
# a_binding_reference_names_something_the_source_carries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("route", ["analytic", "numerical"])
def test_r71_a_binding_reference_that_names_nothing_in_the_source_is_refused(route):
    builder = _analytic if route == "analytic" else _numerical
    with pytest.raises(InferenceAdmissibilityError, match="binding"):
        builder(binding_ref="binding:p")


@pytest.mark.parametrize("ref", ["synthetic.admission", "synthetic.admission@1",
                                 "admission-source", "admission-run", "algebraic"],
                         ids=["model", "model_at_version", "result_id", "run_id", "solver"])
def test_r71_the_references_the_in_tree_producers_write_are_accepted(ref):
    """The control: the candidates are what the producers already write, not a new convention."""
    assert _analytic(binding_ref=ref) is not None


# ---------------------------------------------------------------------------
# cases added while running this batch's guard mutations, to separate two rules
# that both fire on the reproductions above
# ---------------------------------------------------------------------------
def test_r71_a_source_whose_own_report_claims_convergence_is_refused_at_not_applicable_too():
    """Only the report rule sees this record: the convergence state says NOT_APPLICABLE and the report
    claims NUMERICALLY_CONVERGED, which is a record contradicting itself -- and either half of it is
    enough to say the source has something to converge."""
    source = _source(validation=NUMERICAL_REPORT)
    assert source.convergence is ConvergenceState.NOT_APPLICABLE
    with pytest.raises(InferenceAdmissibilityError, match="OWN validation claims NUMERICALLY_CONVERGED"):
        _analytic(source)


def test_r71_the_sources_own_report_is_refused_even_when_it_names_two_members():
    """Only the identity rule sees this one: the report would satisfy the member count, and it is still
    the single solve's own report rather than the sequence's."""
    source = _source(validation=SEQUENCE, convergence=ConvergenceState.CONVERGED)
    with pytest.raises(InferenceAdmissibilityError, match="own validation report"):
        _numerical(source, sequence_validation=source.validation)
