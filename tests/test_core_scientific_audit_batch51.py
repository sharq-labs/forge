"""Core re-audit 2026-09-16, batch 51: an oracle comparison is about the point the prediction was computed at.

Problems R-49 (the audit's finding 59) and R-53 (finding 65), improvement I-26, under
benchmarks/core_v4_false_confidence/BATCH51_THRESHOLD_PROTOCOL.json.

`compare` takes the operating point as the caller's assertion about a bare mapping of numbers, so a
prediction computed at 400 K passes at a stated 300 K; a stated condition the evidence does not describe is
ignored; and evidence that declares no point at all compares anywhere. In the other direction it loses
justified comparisons: a metric the prediction does not carry scores FAIL -- which reads as NOT_SUPPORTED --
and a set holding readings at two operating points, the normal shape of an experimental dataset, can never
be compared at all.
"""

from __future__ import annotations

import inspect

import pytest

import engcore.scientific.oracles as oracle_module
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.oracles import (
    OracleEvidenceSet,
    OracleKind,
    OracleObservation,
)
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ConvergenceState, ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = ("synthetic.cell", "1.0.0")
AT_300 = {"temperature": Quantity(300.0, "kelvin")}
AT_400 = {"temperature": Quantity(400.0, "kelvin")}


def _observation(metric="voltage", expected=3.70, unit="volt", tolerance=0.05, conditions=None):
    return OracleObservation(
        metric=metric, expected=Quantity(expected, unit),
        absolute_tolerance=Quantity(tolerance, unit),
        conditions=AT_300 if conditions is None else conditions,
    )


def _oracle(*observations, kind=OracleKind.EXPERIMENTAL_DATASET) -> OracleEvidenceSet:
    return OracleEvidenceSet.create(
        oracle_id="lab.cell.discharge.001", version="1", kind=kind,
        reference="doi:10.example/dataset",
        observations=observations or (_observation(),),
    )


def _trust(monkeypatch, oracle: OracleEvidenceSet) -> None:
    monkeypatch.setattr(
        oracle_module, "_TRUSTED_ORACLE_DECLARATIONS",
        {oracle.identity.key: {
            "kind": oracle.identity.kind.value,
            "evidence_digest": oracle.identity.evidence_digest,
            "reference": oracle.identity.reference,
            "declared_by": "tests.test_core_scientific_audit_batch51",
        }},
    )


def _result(values, conditions=AT_300, result_id="cell-result") -> ScientificResult:
    return ScientificResult(
        result_id=result_id, problem_id="cell",
        values=dict(values), conditions=dict(conditions),
        models=(MODEL,),
        validity_not_assessed={MODEL[0]: "a fixture: nothing asked whether the model applied"},
        solver=SolverIdentity("algebraic", "1.0.0"),
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(checks=(ValidationCheck(
            name="dimensional_consistency", outcome=ValidationOutcome.PASS,
            establishes=ValidationLevel.DIMENSIONALLY_VALID, evidence=("fixture",)),)),
        uncertainty={name: Uncertainty.unknown("no quantification here") for name in values},
        provenance=ProvenanceRecord(run_id="cell-run", models=(MODEL,),
                                    solvers=(("algebraic", "1.0.0"),)),
    )


# ---------------------------------------------------------------------------
# an_unpredicted_metric_is_not_evidence_against_the_model
# ---------------------------------------------------------------------------
def test_r53_a_prediction_that_misses_its_tolerance_is_still_a_failure():
    """The control: a comparison that was MADE and disagreed is the one thing that is evidence against."""
    check = _oracle().compare({"voltage": Quantity(3.0, "volt")}, conditions=AT_300)
    assert check.outcome is ValidationOutcome.FAIL


@pytest.mark.xfail(strict=True, reason="R-53 finding 65 as audited: a metric the prediction does not carry is recorded as 'z:missing' and the check is FAIL, which derive_verdict reads as NOT_SUPPORTED although no comparison was made")
def test_r53_an_unpredicted_metric_is_not_run_rather_than_failed():
    oracle = _oracle(_observation(), _observation(metric="capacity", expected=2.5, unit="ampere * hour",
                                                  tolerance=0.1))
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300)
    assert check.outcome is ValidationOutcome.NOT_RUN, check.detail
    assert check.establishes is None


@pytest.mark.xfail(strict=True, reason="R-53: and with the oracle pinned, that FAIL is a NOT_SUPPORTED verdict built out of an absence")
def test_r53_an_unpredicted_metric_awards_no_level_and_accuses_nothing(monkeypatch):
    oracle = _oracle(_observation(), _observation(metric="capacity", expected=2.5, unit="ampere * hour",
                                                  tolerance=0.1))
    _trust(monkeypatch, oracle)
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300)
    assert check.outcome is not ValidationOutcome.FAIL
    assert check.establishes is None


# ---------------------------------------------------------------------------
# multi_point_evidence_is_compared_point_by_point
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-53 as audited: observations inside one set must have unique METRICS, so the same reading at two operating points cannot be recorded at all")
def test_r53_one_metric_at_two_operating_points_is_two_observations():
    try:
        oracle = _oracle(_observation(), _observation(expected=3.55, conditions=AT_400))
    except ScientificValidationError as refusal:
        oracle = None
        assert oracle is not None, f"one reading at two operating points is refused as a duplicate: {refusal}"
    assert len(oracle.observations) == 2


@pytest.mark.xfail(strict=True, reason="R-53 as audited: compare requires one stated point to match EVERY observation's conditions, so a two-point set is always NOT_RUN and every justified comparison is lost")
def test_r53_a_two_point_set_is_compared_at_the_point_the_prediction_states():
    try:
        oracle = _oracle(_observation(), _observation(expected=3.55, conditions=AT_400))
    except ScientificValidationError as refusal:
        pytest.fail(f"a two-point evidence set cannot even be built: {refusal}")
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300)
    assert check.outcome is ValidationOutcome.PASS, check.detail
    assert "voltage" in check.detail or any("voltage" in e for e in check.evidence)


# ---------------------------------------------------------------------------
# a_stated_point_the_evidence_does_not_describe_is_not_a_comparison
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-49 finding 59's second gap as audited: a stated condition the observation does not declare is ignored silently, so an observation at T only is compared against a prediction at P = 50 bar")
def test_r49_a_stated_condition_the_evidence_does_not_describe_stops_the_comparison():
    oracle = _oracle()
    check = oracle.compare(
        {"voltage": Quantity(3.70, "volt")},
        conditions={**AT_300, "pressure": Quantity(50.0, "bar")},
    )
    assert check.outcome is ValidationOutcome.NOT_RUN, check.detail
    assert "pressure" in check.detail


# ---------------------------------------------------------------------------
# evidence_that_does_not_say_where_it_was_observed_awards_no_level
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-49 finding 59's third gap as audited: an observation with no conditions -- every record written before the field existed -- compares at any operating point, and earns the level there")
def test_r49_evidence_with_no_declared_point_awards_no_level(monkeypatch):
    oracle = _oracle(_observation(conditions={}))
    _trust(monkeypatch, oracle)
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_400)
    assert check.outcome is ValidationOutcome.PASS, check.detail
    assert check.establishes is None, "the record does not say where it was observed"


# ---------------------------------------------------------------------------
# a_level_requires_the_prediction_to_say_where_it_was_computed
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-49 finding 59's first claim as audited: the operating point is the caller's assertion about a bare mapping, so a prediction computed at 400 K passes -- and earns the level -- at a stated 300 K")
def test_r49_a_level_needs_the_record_the_prediction_came_from(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    if "predicted_from" not in inspect.signature(oracle.compare).parameters:
        pytest.fail("compare cannot be told which record the prediction came from, so the operating point "
                    "is the caller's word about a mapping of numbers")
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300)
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None, "no record was named, so no level is awarded"


@pytest.mark.xfail(strict=True, reason="R-49: and the record the prediction came from is what makes the stated point checkable at all")
def test_r49_the_named_record_must_have_been_computed_at_the_stated_point(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    if "predicted_from" not in inspect.signature(oracle.compare).parameters:
        pytest.fail("compare takes no record to check the stated point against")
    computed_elsewhere = _result({"voltage": Quantity(3.70, "volt")}, conditions=AT_400)
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300,
                           predicted_from=computed_elsewhere)
    assert check.outcome is ValidationOutcome.NOT_RUN, check.detail
    assert check.establishes is None


@pytest.mark.xfail(strict=True, reason="R-49: with the record named and its point agreeing, the comparison is what it always claimed to be")
def test_r49_a_bound_prediction_at_the_observed_point_earns_the_level(monkeypatch):
    oracle = _oracle()
    _trust(monkeypatch, oracle)
    if "predicted_from" not in inspect.signature(oracle.compare).parameters:
        pytest.fail("compare takes no record to bind the prediction to")
    computed_here = _result({"voltage": Quantity(3.70, "volt")}, conditions=AT_300)
    check = oracle.compare({"voltage": Quantity(3.70, "volt")}, conditions=AT_300,
                           predicted_from=computed_here)
    assert check.outcome is ValidationOutcome.PASS, check.detail
    assert check.establishes is ValidationLevel.EXPERIMENTALLY_VALIDATED
