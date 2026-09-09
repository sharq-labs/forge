"""Fully specified traces: every stage asserted, not only the verdict.

WHY THIS MODULE EXISTS
----------------------
A golden test that asserts a final verdict cannot tell a right answer from two
wrong stages that cancelled. The hard benchmark is exactly that test, 1400
times: it compares one enum per case. It found real defects and it is
structurally blind to a class of them -- and this round measured that blindness
rather than assuming it. In the ``adv_unsound:small_overshoot`` family, four of
the forty-nine dev cases scored as caught are caught by a condition the case's
own truth does not name. The verdict was right; the reason was not; the score
could not see the difference.

So these cases assert the intermediate state: which models were assessed, which
conditions were satisfied, violated or unknown, **why** each unknown is unknown,
what the coupling observed, which checks ran and what each established -- and
then the verdict. A stage that starts lying fails here even when the verdict
survives.

WHAT THE CASES ARE FOR
----------------------
Eight cases from the two benchmarks' own files, chosen to cover the distinct
paths rather than to sample them evenly. Nothing here rewrites a case; the
payloads are read off disk.

===========  ==================================================================
S00013       the *supported* path, and a boundary: the linearization band is
             cleared by 0.2 %
U00002       the *refusal* path, and the mirror boundary: Biot is exceeded by
             0.2 %. Also pins that ONE violated condition carries three models
U00004       a missing declaration becomes UNKNOWN(``not_supplied``), never a
             default and never a pass
U00005       a *conservative screen*: UNKNOWN(``conservative_screen``), which
             the 2026-09-09 adjudication established must not be NOT_SUPPORTED
U00048       the coupling refuses a transfer -- negative resistance, two FAILing
             checks, and no thermal march at all
U00204       a former false accept, now agreeing with its adjudicated truth
U01001       the same, and the residual gap the adjudication did not close
B00006       the battery gap, stated rather than hidden
===========  ==================================================================

THE FALSE ACCEPTS ARE PINNED ON PURPOSE
---------------------------------------
Both were pinned here to what Forge does, which was not what their truth said.
That is what made the disagreement impossible to move quietly, and it worked:
adjudicating ``U00204`` turned this module red and forced the change to be
stated rather than absorbed into a benchmark count.

Both now assert agreement, and every number either one checks is the number it
checked before its adjudication -- the runs did not change, the answer key did.

Neither adjudication closed the residual `U01001` names: the asymptote this
run is heading for DOES exceed the declared ceiling, and no condition reads it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.engcore.mcp.battery import run_battery_case
from src.engcore.mcp.evidence import CredibilityVerdict
from src.engcore.mcp.problem import run_electrothermal_case

HARD = pathlib.Path("benchmarks/hard/cases_hard")
BATTERY = pathlib.Path("benchmarks/hard/cases_battery")

#: The three checks every completed electro-thermal march emits. Named once so
#: a case that grows or loses one is visible as a difference from this tuple.
STANDARD_CHECKS = (
    "lumped_balance_residual",
    "analytic_reference_agreement",
    "declared_limits_are_mutually_consistent",
)


def _case(directory: pathlib.Path, case_id: str) -> dict:
    return json.loads(
        (directory / f"{case_id}.json").read_text(encoding="utf-8")
    )


def _electrothermal(case_id: str):
    case = _case(HARD, case_id)
    return case, run_electrothermal_case(case["payload"], run_id=case_id)


def _assessment(report, model_id):
    for record in report.validity:
        if record.model_id == model_id:
            return record.assessment
    raise AssertionError(
        f"{model_id} is not in the report; it has "
        f"{[r.model_id for r in report.validity]}"
    )


def _outcomes(report):
    return {check.name: check.outcome.value for check in report.validation}


def _levels(report):
    return {
        check.name: getattr(check.establishes, "value", None)
        for check in report.validation
    }


def _unknown_reasons(assessment):
    return {
        condition.name: condition.reason.value
        for condition in (assessment.unknown_reasons or ())
    }


# =====================================================================
# S00013 -- supported, and a boundary cleared by 0.2 %
# =====================================================================

def test_s00013_is_supported_and_every_stage_says_why():
    case, run = _electrothermal("S00013")
    assert case["ground_truth"]["expected_verdict"] == "SUPPORTED"
    assert case["ground_truth"]["should_be_caught_by"] == (
        "linearization_excursion_ratio"
    )

    # Stage: coupling reached its own criterion.
    assert run.run.outcome.name == "CRITERION_MET"
    assert len(run.reports) == 1
    report = run.reports[0]
    assert report.coupling.outcome == "criterion_met"
    assert (
        report.coupling.largest_iterate_change.magnitude
        <= report.coupling.tolerance.magnitude
    )

    # Stage: the operating point, and the asymptote it is NOT.
    assert report.values["final_temperature"].magnitude == pytest.approx(
        319.04202247209315, rel=1e-12
    )
    assert report.values[
        "steady_state_temperature"
    ].magnitude == pytest.approx(319.0698038959096, rel=1e-12)
    assert report.values["time_constant"].units == "second"

    # Stage: applicability. Nothing violated, nothing unknown, on any model --
    # which is what makes this the supported path rather than a quiet gap.
    assert len(report.validity) == 6
    for record in report.validity:
        assert record.assessment.status.value == "in_domain", record.model_id
        assert record.assessment.violated == ()
        assert record.assessment.unknown == ()

    # The boundary this case exists for is SATISFIED, not absent.
    rated = _assessment(report, "electrical.material.rated_linear_tcr_resistance")
    assert "linearization_excursion_ratio" in rated.satisfied

    # Stage: validation -- and the one level the reference path can attain.
    assert tuple(_outcomes(report)) == STANDARD_CHECKS
    assert set(_outcomes(report).values()) == {"pass"}
    assert _levels(report)["analytic_reference_agreement"] == (
        "analytically_verified"
    )
    assert _levels(report)["lumped_balance_residual"] is None

    # Stage: nothing took part that nothing assessed.
    assert report.unassessed_models == ()

    assert report.verdict is CredibilityVerdict.SUPPORTED


# =====================================================================
# U00002 -- the mirror boundary, exceeded by 0.2 %
# =====================================================================

def test_u00002_refuses_on_one_condition_that_carries_three_models():
    case, run = _electrothermal("U00002")
    assert case["ground_truth"]["expected_verdict"] == "NOT_SUPPORTED"

    report = run.reports[0]
    assert run.run.outcome.name == "CRITERION_MET"

    # The declared catcher is violated...
    thermal = _assessment(report, "thermal.lumped.first_order_capacity")
    assert thermal.status.value == "outside_validated_domain"
    assert thermal.violated == ("biot_number",)
    assert thermal.unknown == ()

    # ...and so is `temperature` on both material models, because 621.9 K is
    # outside the range the linear TCR form is declared over at all. Asserting
    # this is the point: the verdict would be identical with only one of them,
    # so only an intermediate assertion can tell which fired.
    for model_id in (
        "electrical.material.linear_tcr_resistance",
        "electrical.material.rated_linear_tcr_resistance",
    ):
        assessment = _assessment(report, model_id)
        assert assessment.status.value == "outside_validated_domain"
        assert assessment.violated == ("temperature",)

    # The electrical models are untouched by a thermal excursion.
    for model_id in ("electrical.dc.kcl", "electrical.dc.resistor_ohm"):
        assert _assessment(report, model_id).status.value == "in_domain"

    # Every check still PASSES. The refusal is applicability, not validation --
    # and a reader who only saw the checks would conclude the opposite.
    assert set(_outcomes(report).values()) == {"pass"}
    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


# =====================================================================
# U00004 -- a missing declaration is UNKNOWN, not a default
# =====================================================================

def test_u00004_turns_a_missing_declaration_into_a_named_unknown():
    case, run = _electrothermal("U00004")
    assert case["ground_truth"]["expected_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "melting_temperature" in case["ground_truth"]["defect"]

    report = run.reports[0]
    thermal = _assessment(report, "thermal.lumped.first_order_capacity")
    assert thermal.status.value == "unknown"
    assert thermal.violated == ()
    assert thermal.unknown == ("melting_temperature_utilization",)
    # WHY it is unknown, not merely that it is.
    assert _unknown_reasons(thermal) == {
        "melting_temperature_utilization": "not_supplied"
    }

    # The check that compares declared limits cannot run without the limit, so
    # it is absent rather than passing vacuously.
    assert "declared_limits_are_mutually_consistent" not in _outcomes(report)

    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# U00005 -- a conservative screen is a gap, never a finding against
# =====================================================================

def test_u00005_reports_a_conservative_screen_as_insufficient_evidence():
    """The rule the 2026-09-09 adjudication landed, asserted at the stage.

    Under the Fourier floor the criterion observed nothing, so there is no
    evidence for the model and none against it. NOT_SUPPORTED would assert
    evidence against a design that has none to assert.
    """
    case, run = _electrothermal("U00005")
    assert case["ground_truth"]["expected_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert case["ground_truth"]["should_be_caught_by"] == (
        "internal_fourier_number"
    )

    report = run.reports[0]
    thermal = _assessment(report, "thermal.lumped.first_order_capacity")
    assert thermal.status.value == "unknown"
    assert thermal.violated == (), "a screen must not be reported as a finding"
    assert thermal.unknown == ("internal_fourier_number",)
    assert _unknown_reasons(thermal) == {
        "internal_fourier_number": "conservative_screen"
    }

    # This case is also the clearest example of the two temperatures being
    # genuinely different: the horizon stops 89 K short of the asymptote.
    assert report.values["final_temperature"].magnitude == pytest.approx(
        338.48933428969406, rel=1e-12
    )
    assert report.values[
        "steady_state_temperature"
    ].magnitude == pytest.approx(427.67045569116965, rel=1e-12)

    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# U00048 -- the coupling refuses, and nothing downstream pretends otherwise
# =====================================================================

def test_u00048_refuses_the_transfer_and_never_marches_the_body():
    case, run = _electrothermal("U00048")
    assert case["ground_truth"]["expected_verdict"] == "NOT_SUPPORTED"

    assert run.run.outcome.name == "TRANSFER_REFUSED"
    report = run.reports[0]

    # A negative resistance is REPORTED rather than swallowed or clamped.
    assert report.values["resistance"].magnitude == pytest.approx(
        -798.0111286140271, rel=1e-12
    )
    # And no thermal march happened, so its metrics are absent entirely.
    assert "final_temperature" not in report.values
    assert "steady_state_temperature" not in report.values

    rated = _assessment(report, "electrical.material.rated_linear_tcr_resistance")
    assert rated.status.value == "outside_validated_domain"
    assert rated.violated == ("linear_resistance_ratio",)

    outcomes = _outcomes(report)
    assert outcomes["resistance_strictly_positive"] == "fail"
    assert outcomes["coupling_transfer_refused"] == "fail"
    # A dimensional check still earns its level: it did what it claims to do.
    assert _levels(report)["metric_dimensions"] == "dimensionally_valid"

    assert report.verdict is CredibilityVerdict.NOT_SUPPORTED


# =====================================================================
# The two false accepts, pinned as current behaviour
# =====================================================================

def test_u00204_agrees_with_its_truth_now_that_the_truth_was_adjudicated():
    """Adjudicated by `2026-09-09.u00204.runaway-that-does-not-run-away`.

    This test used to pin a disagreement: Forge said SUPPORTED and the case
    said NOT_SUPPORTED. Nothing about the run changed -- every number asserted
    below is the number it asserted before. What changed is the answer key,
    because the case's stated reason ("the loop does not contract") is false
    for this design: the ODE rises monotonically to a stable equilibrium at
    355.8326 K that the generator's own solver also finds.

    So the assertion that moved is the expected verdict, and it moved in
    `ADJUDICATIONS.json` rather than here.
    """
    case, run = _electrothermal("U00204")
    assert case["ground_truth"]["expected_verdict"] == "SUPPORTED"
    assert case["ground_truth"]["label"] == "valid"
    # The defect family is deliberately NOT revised: the split stratifies on
    # it, so moving it would reallocate sealed seats.
    assert case["ground_truth"]["defect"] == "runaway"

    assert run.run.outcome.name == "CRITERION_MET"
    report = run.reports[0]
    assert report.coupling.iterations_run == 123
    assert report.coupling.iterations_run < report.coupling.iteration_limit

    # The operating point is far inside every declared limit.
    final = report.values["final_temperature"].magnitude
    assert final == pytest.approx(355.7381904607981, rel=1e-12)
    ceiling = float(
        case["payload"]["stages"][0]["conductor"]["limits"][
            "maximum_operating_temperature"
        ].split()[0]
    )
    assert final / ceiling < 0.32

    # Nothing is violated and nothing is unknown, on any model.
    for record in report.validity:
        assert record.assessment.violated == ()
        assert record.assessment.unknown == ()

    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.verdict.name == case["ground_truth"]["expected_verdict"], (
        "Forge and the adjudicated truth now agree; if this ever fails again "
        "read the adjudication before changing either side"
    )


def test_u01001_agrees_with_its_truth_now_that_the_truth_was_adjudicated():
    """Adjudicated by `2026-09-09.u01001.ceiling-sized-against-the-asymptote`.

    The ceiling sits between the endpoint and the asymptote, and the three
    numbers below are the whole argument, so they are asserted together.
    Moving the condition to the asymptote would fix this case and break
    eighteen that a landed adjudication requires to stay
    INSUFFICIENT_EVIDENCE -- so the truth moved and the runtime did not.

    The residual this does NOT close: `steady_state_temperature` exceeds the
    ceiling and no condition reads it, so a design whose equilibrium is above a
    declared hard limit is flagged nowhere. That is recorded as a capability
    gap, not waived.
    """
    case, run = _electrothermal("U01001")
    assert case["ground_truth"]["expected_verdict"] == "SUPPORTED"
    assert case["ground_truth"]["label"] == "valid"
    assert case["ground_truth"]["defect"] == "adv_unsound:small_overshoot"

    report = run.reports[0]
    endpoint = report.values["final_temperature"].magnitude
    asymptote = report.values["steady_state_temperature"].magnitude
    ceiling = float(
        case["payload"]["stages"][0]["conductor"]["limits"][
            "maximum_operating_temperature"
        ].split()[0]
    )

    assert endpoint == pytest.approx(428.0256665841501, rel=1e-12)
    assert asymptote == pytest.approx(428.281910187297, rel=1e-12)
    assert ceiling == pytest.approx(428.1227789)
    assert endpoint < ceiling < asymptote, (
        "the case's whole character is that the ceiling sits between the "
        "state the run reaches and the state it is heading for"
    )

    # The condition is evaluated at the endpoint, so it is SATISFIED.
    rated = _assessment(report, "electrical.material.rated_linear_tcr_resistance")
    assert "operating_temperature_utilization" in rated.satisfied
    assert rated.status.value == "in_domain"

    assert report.verdict is CredibilityVerdict.SUPPORTED


# =====================================================================
# B00006 -- the battery gap, stated rather than hidden
# =====================================================================

def test_b00006_shows_the_battery_thermal_gap_the_scorer_works_around():
    """Four battery models in domain, and a thermal body nobody can declare.

    `run_self_heating_discharge` accepts no applicability declaration for the
    body it marches, so the lumped model in every battery report is honestly
    UNKNOWN and the whole-report verdict can never be SUPPORTED. `score_hard`
    therefore scores battery cases over the battery models alone and says so.
    This pins both halves: the scoped answer AND the gap that makes the scoping
    necessary, so closing the gap shows up here rather than only as a moved
    number.
    """
    case = _case(BATTERY, "B00006")
    assert case["ground_truth"]["expected_verdict"] == "SUPPORTED"

    report = run_battery_case(case["payload"], run_id="B00006").report

    battery_models = {
        record.model_id: record.assessment.status.value
        for record in report.validity
        if record.model_id.startswith("battery.")
    }
    assert battery_models == {
        "battery.cell.constant_current_runtime": "in_domain",
        "battery.cell.coulomb_counting": "in_domain",
        "battery.cell.peukert_capacity_derating": "in_domain",
        "battery.cell.rint_ocv": "in_domain",
    }

    # The gap, named at the condition rather than as a status alone.
    thermal = _assessment(report, "thermal.lumped.first_order_capacity")
    assert thermal.status.value == "unknown"
    assert thermal.violated == ()
    assert {"biot_number", "internal_fourier_number"} <= set(thermal.unknown)

    # So the scoped verdict and the whole-report verdict differ, and that
    # difference is the finding the benchmark README carries.
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
