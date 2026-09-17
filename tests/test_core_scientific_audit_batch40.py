"""Core re-audit 2026-09-16, batch 40: a change of meaning gets a version, and "did not apply" is not "nobody ran".

Problem R-45 (the audit's findings 53 and 87, and finding 90's first item), improvement I-20 part B of
three, under benchmarks/core_v4_false_confidence/BATCH40_THRESHOLD_PROTOCOL.json.

CORE-013 reordered the status precedence and left the schema string at `validation_report/1`, and the reader
compares a stored status with the recomputed one. So every report the pre-CORE-013 tree wrote with a PASS and
a NOT_RUN check -- which is what any conduction1d slab solve writes -- is refused on read.
"""

from __future__ import annotations

import copy

import pytest

from engcore.scientific.errors import ScientificCoreError, ScientificValidationError
from engcore.scientific.results import validation as V
from engcore.scientific.results.validation import (
    REPORT_SCHEMA,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)


def _symbol(name):
    assert hasattr(V, name), (
        f"engcore.scientific.results.validation has no {name!r}; it is preregistered in "
        f"BATCH40_THRESHOLD_PROTOCOL.json"
    )
    return getattr(V, name)


def _mixed_report():
    """The shape the pre-CORE-013 tree wrote on every conduction1d solve: passing checks and an unrun one."""
    return ValidationReport(checks=(
        ValidationCheck(name="dimensional_consistency", outcome=ValidationOutcome.PASS,
                        establishes=ValidationLevel.DIMENSIONALLY_VALID, evidence=("T=kelvin",)),
        ValidationCheck(name="linear_system_residual", outcome=ValidationOutcome.PASS,
                        residual=0.0, tolerance=1.0e-9,
                        establishes=ValidationLevel.NUMERICALLY_CONVERGED),
        ValidationCheck(name="analytic_invariant_agreement", outcome=ValidationOutcome.NOT_RUN,
                        detail="no analytic invariant declared"),
    ))


def _legacy_payload(status="pass"):
    """That report as the pre-CORE-013 writer serialized it: schema /1, status by the old precedence."""
    payload = copy.deepcopy(_mixed_report().to_dict())
    payload["schema"] = "validation_report/1"
    payload["status"] = status
    return payload


# ---------------------------------------------------------------------------
# a_change_of_meaning_gets_a_version
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-45 finding 53: CORE-013 changed what status means under an unchanged schema string")
def test_r45_the_status_precedence_change_is_named_by_a_version():
    assert REPORT_SCHEMA == "validation_report/2", (
        "CORE-013 changed what `status` means and the schema string still says /1")
    assert _mixed_report().to_dict()["schema"] == "validation_report/2"


def test_r45_a_current_record_round_trips():
    """The premise, and the control for every rule below."""
    report = _mixed_report()
    assert report.status is ValidationOutcome.NOT_RUN
    assert ValidationReport.from_dict(report.to_dict()) == report


# ---------------------------------------------------------------------------
# a_legacy_report_is_read_under_the_precedence_it_was_written_with
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-45 as audited: the record any pre-CORE-013 conduction1d solve wrote is refused on read")
def test_r45_the_pre_core013_record_reads_back_with_its_status_re_derived():
    """The audited record: 'pass' is what the old precedence gave over these exact checks."""
    try:
        read = ValidationReport.from_dict(_legacy_payload("pass"))
    except ScientificValidationError as exc:
        pytest.fail(f"the record the pre-CORE-013 tree wrote is refused rather than read: {exc}")
    assert [c.name for c in read.checks] == ["dimensional_consistency", "linear_system_residual",
                                             "analytic_invariant_agreement"]
    assert read.status is ValidationOutcome.NOT_RUN, (
        "the stored status is explained, not believed: the current rule is what the reader reports")
    assert read.claims(ValidationLevel.DIMENSIONALLY_VALID)


def test_r45_a_legacy_record_whose_status_is_the_current_answer_still_reads():
    try:
        read = ValidationReport.from_dict(_legacy_payload("not_run"))
    except ScientificValidationError as exc:  # pragma: no cover - the premise
        pytest.fail(f"a legacy payload agreeing with the current rule is refused: {exc}")
    assert read.status is ValidationOutcome.NOT_RUN


@pytest.mark.xfail(strict=True, reason="R-45: the refusal names a contradiction rather than the precedence change that caused it")
def test_r45_a_legacy_status_that_matches_neither_precedence_is_refused_and_says_so():
    with pytest.raises(ScientificValidationError) as raised:
        ValidationReport.from_dict(_legacy_payload("fail"))
    message = str(raised.value)
    assert "not_run" in message and "pass" in message, message
    assert "precedence" in message, (
        f"the refusal does not say that two precedences exist and this status is neither: {message}")


def test_r45_a_current_record_whose_status_disagrees_is_still_refused():
    """The control: nothing weakens for records written from here on."""
    payload = _mixed_report().to_dict()
    payload["status"] = "pass"
    with pytest.raises(ScientificValidationError, match="does not match the status its checks produce"):
        ValidationReport.from_dict(payload)


def test_r45_an_unknown_version_is_still_refused():
    payload = _legacy_payload()
    payload["schema"] = "validation_report/999"
    with pytest.raises(ScientificCoreError):
        ValidationReport.from_dict(payload)


# ---------------------------------------------------------------------------
# a_check_that_did_not_apply_is_not_a_check_nobody_ran
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-45 finding 87: there is no representation for a check that did not apply")
def test_r45_there_is_a_way_to_say_a_check_did_not_apply():
    outcome = getattr(ValidationOutcome, "NOT_APPLICABLE", None)
    assert outcome is not None, "ValidationOutcome has no NOT_APPLICABLE; it is preregistered"
    assert outcome.value == "not_applicable"
    assert list(ValidationOutcome)[:4] == [ValidationOutcome.PASS, ValidationOutcome.FAIL,
                                           ValidationOutcome.WARNING, ValidationOutcome.NOT_RUN], (
        "the new member must be appended: the member order is frozen")


def _not_applicable():
    assert hasattr(ValidationOutcome, "NOT_APPLICABLE"), (
        "ValidationOutcome has no NOT_APPLICABLE; it is preregistered in BATCH40_THRESHOLD_PROTOCOL.json")
    return ValidationOutcome.NOT_APPLICABLE


def _inapplicable(name="voltage_source_relation"):
    return ValidationCheck(name=name, outcome=_not_applicable(),
                           detail="circuit contains no voltage sources")


@pytest.mark.xfail(strict=True, reason="R-45 finding 87: an inapplicable check is recorded as NOT_RUN, so the report is permanently NOT_RUN")
def test_r45_an_inapplicable_check_is_not_missing_evidence():
    report = ValidationReport(checks=(
        ValidationCheck(name="linear_system_residual", outcome=ValidationOutcome.PASS,
                        residual=0.0, tolerance=1.0e-9,
                        establishes=ValidationLevel.NUMERICALLY_CONVERGED),
        _inapplicable(),
    ))
    assert report.status is ValidationOutcome.PASS, (
        "a check with no evidence to gather is not a check whose evidence was not gathered")
    assert report.not_run == ()
    assert [c.name for c in report.not_applicable] == ["voltage_source_relation"]
    assert report.claims(ValidationLevel.NUMERICALLY_CONVERGED)


@pytest.mark.xfail(strict=True, reason="R-45: the new outcome does not exist, so nothing refuses a level on it")
def test_r45_an_inapplicable_check_still_establishes_nothing():
    with pytest.raises(ScientificValidationError, match="not_applicable|did not apply"):
        ValidationCheck(name="voltage_source_relation",
                        outcome=_not_applicable(),
                        residual=0.0, tolerance=1.0,
                        establishes=ValidationLevel.NUMERICALLY_CONVERGED)


@pytest.mark.xfail(strict=True, reason="R-45: the new outcome does not exist")
def test_r45_a_report_of_nothing_but_inapplicable_checks_established_nothing():
    report = ValidationReport(checks=(_inapplicable(), _inapplicable("resistor_metric_consistency")))
    assert report.status is ValidationOutcome.NOT_RUN, (
        "a report that established nothing is NOT_RUN, which is the empty report's own answer")


@pytest.mark.xfail(strict=True, reason="R-45: the new outcome does not exist")
def test_r45_a_failure_and_an_unrun_check_still_outrank_an_inapplicable_one():
    """The control: excluding NOT_APPLICABLE does not touch the precedence between the others."""
    failing = ValidationReport(checks=(
        ValidationCheck(name="power_balance", outcome=ValidationOutcome.FAIL, residual=1.0, tolerance=1e-9),
        _inapplicable(),
    ))
    assert failing.status is ValidationOutcome.FAIL and not failing.is_usable
    unrun = ValidationReport(checks=(
        ValidationCheck(name="analytic_invariant_agreement", outcome=ValidationOutcome.NOT_RUN),
        _inapplicable(),
    ))
    assert unrun.status is ValidationOutcome.NOT_RUN


@pytest.mark.xfail(strict=True, reason="R-45: the new outcome does not exist")
def test_r45_an_inapplicable_check_round_trips():
    report = ValidationReport(checks=(_inapplicable(),))
    assert ValidationReport.from_dict(report.to_dict()) == report


# ---------------------------------------------------------------------------
# a_gate_says_which_of_the_two_it_means, and the declaration that follows it
# ---------------------------------------------------------------------------
def _current_source_only_result():
    from engcore.domains.electrical.dc import (
        DCCircuit,
        DCCurrentSource,
        ElectricalNode,
        Resistor,
        solve_circuit,
    )
    from engcore.scientific.units import Quantity

    circuit = DCCircuit(
        circuit_id="b40-isource-only",
        nodes=(ElectricalNode("a"), ElectricalNode("g", is_reference=True)),
        resistors=(Resistor("R1", "a", "g", Quantity(10.0, "ohm")),),
        current_sources=(DCCurrentSource("I1", "g", "a", Quantity(1.0, "ampere")),),
    )
    return solve_circuit(circuit, run_id="b40")


@pytest.mark.xfail(strict=True, reason="R-45 as audited: a clean current-source circuit reports a NOT_RUN validation status")
def test_r45_a_clean_circuit_with_no_voltage_source_reports_pass():
    """The production shape the audit names, end to end."""
    result = _current_source_only_result()
    report = result.validation
    outcomes = {c.name: c.outcome.value for c in report.checks}
    assert outcomes["voltage_source_relation"] == "not_applicable", outcomes
    assert report.status is ValidationOutcome.PASS, (
        f"a clean solve still reports a NOT_RUN validation status: {outcomes}")
    assert result.validation.not_run == ()


@pytest.mark.xfail(strict=True, reason="R-45, found while reproducing: build_dc_problem demands a PASSING voltage_source_relation from a circuit that has no voltage source")
def test_r45_the_problem_stops_demanding_a_check_its_circuit_cannot_produce():
    from engcore.domains.electrical.dc import build_dc_problem
    from engcore.domains.electrical.dc import DCCircuit, DCCurrentSource, ElectricalNode, Resistor
    from engcore.scientific.units import Quantity

    circuit = DCCircuit(
        circuit_id="b40-isource-only",
        nodes=(ElectricalNode("a"), ElectricalNode("g", is_reference=True)),
        resistors=(Resistor("R1", "a", "g", Quantity(10.0, "ohm")),),
        current_sources=(DCCurrentSource("I1", "g", "a", Quantity(1.0, "ampere")),),
    )
    declared = set(build_dc_problem(circuit).validation_requirements)
    assert "voltage_source_relation" not in declared, (
        "the problem demands a PASSING check of a circuit that has no voltage source to check")
    assert "resistor_metric_consistency" in declared and "power_balance" in declared


def test_r45_a_divider_still_declares_and_passes_the_voltage_source_check():
    """The control: nothing is dropped from a circuit that does have the element."""
    from engcore.domains.electrical.dc import build_dc_problem
    from engcore.domains.electrical.dc import DCCircuit, DCVoltageSource, ElectricalNode, Resistor
    from engcore.scientific.units import Quantity
    from engcore.domains.electrical.dc import solve_circuit

    circuit = DCCircuit(
        circuit_id="b40-divider",
        nodes=(ElectricalNode("a"), ElectricalNode("m"), ElectricalNode("g", is_reference=True)),
        resistors=(Resistor("R1", "a", "m", Quantity(100.0, "ohm")),
                   Resistor("R2", "m", "g", Quantity(100.0, "ohm"))),
        voltage_sources=(DCVoltageSource("V1", "a", "g", Quantity(10.0, "volt")),),
    )
    assert "voltage_source_relation" in set(build_dc_problem(circuit).validation_requirements)
    report = solve_circuit(circuit, run_id="b40d").validation
    assert {c.name: c.outcome.value for c in report.checks}["voltage_source_relation"] == "pass"
    assert report.status is ValidationOutcome.PASS


@pytest.mark.xfail(strict=True, reason="R-45 finding 87: the critic reports NOT_ASSESSED because the report status is NOT_RUN")
def test_r45_the_critic_reports_pass_for_a_report_where_everything_applicable_ran():
    from engcore.sria.assurance.critics import NumericalCritic

    result = _current_source_only_result()
    assessment = NumericalCritic().assess(result, assessment_id="as-b40")
    record = next(c for c in assessment.checks if c.name == "validation_report_status")
    assert record.outcome.value == "pass", (
        f"the critic still reports {record.outcome.value!r}: {record.detail!r}")
