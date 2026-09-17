"""Core re-audit 2026-09-16, batch 49: the production crossing carries what the producing side said.

Problem R-58 (the audit's finding 71), improvement I-27 part C of three, under
benchmarks/core_v4_false_confidence/BATCH49_THRESHOLD_PROTOCOL.json.

The coupled run's provenance carries `QuantityTransfer` records -- what crossed, from which record, at which
instant -- and nothing beside them. No uncertainty, no validity verdict, no validation state, and
`engcore.uq.cross_domain` has no caller in `src/` at all, which is why the guard reach ledger has been
calling R-58 LIBRARY_ONLY while the audit calls the problem reached.

Recorded as strict xfails in commit 5cbbc997, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import importlib

import pytest

from engcore.scientific.composition.dependency import QuantityDependency
from engcore.scientific.composition.transfer import QuantityTransfer
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ConvergenceState, ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity
from engcore.uq import cross_domain

MODEL = ("synthetic.thermal", "1.0.0")
RECORD = "thermal-result"
DIMENSIONAL = ValidationReport(checks=(ValidationCheck(
    name="dimensional_consistency", outcome=ValidationOutcome.PASS,
    establishes=ValidationLevel.DIMENSIONALLY_VALID, evidence=("fixture: kelvin declared",)),))


def _symbol(name: str):
    """The symbol, or None -- so a missing name is an assertion and not an AttributeError."""
    return getattr(cross_domain, name, None)


def _result(**overrides) -> ScientificResult:
    fields = dict(
        result_id=RECORD, problem_id="thermal.a",
        values={"temperature": Quantity(350.0, "kelvin")},
        models=(MODEL,),
        validity_not_assessed={MODEL[0]: "a fixture: nothing asked whether the model applied"},
        solver=SolverIdentity("algebraic", "1.0.0"),
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=DIMENSIONAL,
        uncertainty={"temperature": Uncertainty.unknown("no quantification is performed here")},
        provenance=ProvenanceRecord(run_id="thermal-run", models=(MODEL,),
                                    solvers=(("algebraic", "1.0.0"),)),
    )
    fields.update(overrides)
    return ScientificResult(**fields)


def _transfer(**overrides) -> QuantityTransfer:
    dependency = QuantityDependency(
        source_problem_id="thermal.a", source_quantity="temperature",
        target_problem_id="electrical.b", target_quantity="ambient_temperature",
        unit_exemplar="kelvin",
    )
    fields = dict(dependency=dependency, value=Quantity(350.0, "kelvin"),
                  source_record_id=RECORD, instant="coupled_iteration:3")
    fields.update(overrides)
    return QuantityTransfer(**fields)


def _crossed(transfer=None, result=None):
    crossing = _symbol("CrossedQuantity")
    if crossing is None:
        pytest.fail("engcore.uq.cross_domain has no CrossedQuantity: a crossing carries a value and "
                    "nothing the producing side said about it")
    return crossing.from_result(
        transfer if transfer is not None else _transfer(),
        result if result is not None else _result(),
    )


# ---------------------------------------------------------------------------
# a_crossing_carries_what_the_producing_side_said_about_its_value
# ---------------------------------------------------------------------------
def test_r58_a_crossing_carries_the_uncertainty_the_producer_declared():
    crossed = _crossed()
    assert crossed.uncertainty_transfer.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert "no quantification is performed here" in crossed.uncertainty_transfer.uncertainty.notes


def test_r58_a_crossing_carries_the_sources_validity_verdict():
    crossed = _crossed()
    assert dict(crossed.source_validity) == {MODEL[0]: "not_assessed"}


def test_r58_a_crossing_carries_the_sources_validation_and_convergence_state():
    crossed = _crossed()
    assert crossed.source_validation_status == "pass"
    assert crossed.source_convergence == "not_applicable"


# ---------------------------------------------------------------------------
# a_crossing_is_bound_to_the_record_it_came_from
# ---------------------------------------------------------------------------
def test_r58_a_crossing_cannot_be_built_against_another_record():
    other = _result(result_id="some-other-result")
    with pytest.raises(InvalidScientificProblem, match="not the record|names"):
        _crossed(result=other)


def test_r58_a_crossing_names_every_model_the_source_declares():
    crossing = _symbol("CrossedQuantity")
    if crossing is None:
        pytest.fail("no CrossedQuantity record exists to hold a verdict per model")
    honest = _crossed()
    with pytest.raises(InvalidScientificProblem, match="model"):
        crossing(
            uncertainty_transfer=honest.uncertainty_transfer,
            source_validity=(),
            source_validation_status=honest.source_validation_status,
            source_convergence=honest.source_convergence,
        )


# ---------------------------------------------------------------------------
# an_absent_uncertainty_entry_is_not_no_uncertainty
# ---------------------------------------------------------------------------
def test_r58_a_result_that_says_nothing_about_its_uncertainty_is_refused():
    silent = _result(uncertainty={})
    with pytest.raises(InvalidScientificProblem, match="uncertainty"):
        _crossed(result=silent)


def test_r58_a_configured_input_crossing_carries_an_undeclared_uncertainty():
    # The record does not PRODUCE the quantity -- that is what a configured input of the problem it
    # answers means, and part A's own check_against_result requires it.
    imposed_on = _result(
        values={"heat_flow": Quantity(1.5, "watt")},
        uncertainty={"heat_flow": Uncertainty.unknown("no quantification is performed here")},
    )
    crossed = _crossed(transfer=_transfer(
        value_origin=QuantityTransfer.VALUE_ORIGIN_CONFIGURED_INPUT,
    ), result=imposed_on)
    assert crossed.uncertainty_transfer.uncertainty.kind is UncertaintyKind.UNKNOWN
    assert "configur" in crossed.uncertainty_transfer.uncertainty.notes


# ---------------------------------------------------------------------------
# the_production_coupling_records_its_crossings
# ---------------------------------------------------------------------------
def test_r58_the_production_coupling_records_a_crossing_per_transfer():
    et = importlib.import_module("engcore.systems.electrothermal.coupled")
    vertical = importlib.import_module("tests.test_electrothermal_vertical")
    run, _problems, _plan = vertical.execute(vertical.NOMINAL, run_id="r58-part-c")
    crossings = getattr(run, "crossings", None)
    assert crossings, (
        "the production coupled run records QuantityTransfer records and nothing beside them: "
        f"{len(run.provenance.transfers)} transfer(s), no crossing")
    assert {c.uncertainty_transfer.transfer.key for c in crossings} == {
        t.key for t in run.provenance.transfers}
    assert all(
        c.source_validation_status in {o.value for o in ValidationOutcome} for c in crossings)
    assert et is not None


def test_r58_a_run_cannot_carry_a_partial_set_of_crossings():
    vertical = importlib.import_module("tests.test_electrothermal_vertical")
    run, _problems, _plan = vertical.execute(vertical.NOMINAL, run_id="r58-part-c-partial")
    crossings = getattr(run, "crossings", None)
    if not crossings:
        pytest.fail("the production run carries no crossings at all, so no set can be partial")
    import dataclasses

    with pytest.raises(InvalidScientificProblem, match="crossing"):
        dataclasses.replace(run, crossings=crossings[:-1])
