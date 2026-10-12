"""Sensitivity, robustness and challenge -- sensitivity, a bounded robustness envelope, and challenge mode, over real runs."""

from __future__ import annotations

import math

import pytest

from claims_support import et_claim, et_inputs, t3_claim
from engcore.claims import (
    BoundaryKind,
    ChallengeKind,
    ChallengeResult,
    InputDistribution,
    InputUncertainty,
    MeasurementRecord,
    SensitivityError,
    TrustedExternalRegistry,
    TrustedPin,
    UncertaintyDemand,
    assess_claim,
    challenge_claim,
    robustness_envelope,
    sensitivity_study,
)
from engcore.claims.sensitivity import _ratio_scale
from engcore.mcp.capabilities import production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.evidence import SourceClass
from engcore.sria.uncertainty import UncertaintyChannel as C

K = "kelvin"
AMB = "stages[0].body.ambient_temperature"
TCR = "stages[0].conductor.temperature_coefficient"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


@pytest.fixture(scope="module")
def et_supported(registry):
    return assess_claim(et_claim(), registry)


def _with_ambient(value):
    inputs = et_inputs()
    inputs[AMB] = Quantity(value, K)
    return et_claim(known_inputs=inputs)


# ---------------------------------------------------------------------------
# Phase 7: sensitivity
# ---------------------------------------------------------------------------


def test_sensitivity_signs_follow_the_declared_physics(et_supported, registry) -> None:
    report = sensitivity_study(et_supported, registry)
    by_path = {p.path: p for p in report.parameters}
    assert by_path[AMB].monotone == "increasing" and by_path[AMB].derivative > 0
    assert by_path["stages[0].body.ambient_conductance"].derivative < 0
    assert by_path["source_voltage"].derivative > 0
    assert all(p.problem is None for p in report.parameters)
    assert "not a causal relationship" in report.to_dict()["notice"]
    assert report.assessment_digest == et_supported.digest
    assert report.plan_digest == et_supported.plan.digest
    assert report.capability_digest == et_supported.plan.capability_digest
    assert report.to_dict()["report_digest"] == report.digest
    assert report.ranked()[0].path == AMB  # the dominant normalized sensitivity


def test_the_local_slope_is_consistent_with_a_direct_rerun(et_supported, registry) -> None:
    slope = {p.path: p for p in sensitivity_study(et_supported, registry, parameters=(AMB,)).parameters}[AMB].derivative
    base = et_supported.report.values["final_temperature"].magnitude
    moved = assess_claim(_with_ambient(302.0), registry).report.values["final_temperature"].magnitude
    assert moved - base == pytest.approx(2.0 * slope, rel=1e-3)


def test_a_perturbation_that_leaves_the_domain_leaves_the_sensitivity_unknown(et_supported, registry) -> None:
    report = sensitivity_study(et_supported, registry, relative_step=0.49, parameters=(AMB,))
    (entry,) = report.parameters
    assert entry.derivative is None and "not usable" in entry.problem


def test_sensitivity_refuses_what_no_declaration_supports(et_supported, registry) -> None:
    with pytest.raises(SensitivityError):
        sensitivity_study(et_supported, registry, parameters=("stages[0].body.duration",))
    unbound = assess_claim(et_claim(known_inputs={k: v for k, v in et_inputs().items() if k != "source_voltage"}), registry)
    with pytest.raises(SensitivityError):
        sensitivity_study(unbound, registry)


def test_normalized_sensitivity_is_not_formed_for_offset_units() -> None:
    assert _ratio_scale("kelvin") and not _ratio_scale("degree_Celsius") and not _ratio_scale("delta_degree_Celsius")


# ---------------------------------------------------------------------------
# Phase 7: robustness envelope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def envelope(et_supported, registry):
    return robustness_envelope(et_supported, registry, parameters=(AMB, TCR))


def test_the_failure_boundary_is_where_a_direct_assessment_flips(envelope, registry) -> None:
    side = envelope.parameters[AMB]["increase"]
    assert side["kind"] == BoundaryKind.FAILS_BEYOND.value
    holds, fails = side["last_holding"], side["first_not_holding"]
    assert holds < fails
    assert assess_claim(_with_ambient(holds), registry).verdict.value == "supported"
    assert assess_claim(_with_ambient(fails), registry).verdict.value == "contradicted"


def test_a_domain_end_is_unknown_beyond_not_holds(envelope, registry) -> None:
    side = envelope.parameters[AMB]["decrease"]
    assert side["kind"] == BoundaryKind.DOMAIN_ENDS.value and side["beyond"] == "unknown"
    assert assess_claim(_with_ambient(side["first_not_holding"]), registry).verdict.value == "insufficient_evidence"


def test_a_non_boundary_parameter_reaches_the_search_limit_and_claims_nothing_beyond(envelope, et_supported) -> None:
    for direction in ("decrease", "increase"):
        side = envelope.parameters[TCR][direction]
        assert side["kind"] == BoundaryKind.SEARCH_LIMIT.value and side["beyond"] == "unknown" and side["first_not_holding"] is None
    assert any("joint variation is not explored" in a for a in envelope.assumptions)
    assert envelope.assessment_digest == et_supported.digest
    assert envelope.plan_digest == et_supported.plan.digest
    assert envelope.capability_digest == et_supported.plan.capability_digest
    assert envelope.to_dict()["report_digest"] == envelope.digest


def test_the_envelope_records_that_it_checks_only_its_probes(envelope) -> None:
    assert any("failure region narrower than the probe spacing can be missed" in a for a in envelope.assumptions)


@pytest.mark.parametrize("bad", [dict(resolution=-1), dict(resolution=True), dict(resolution=2.5), dict(parameters=("stages[0].body.duration",))])
def test_robustness_refuses_what_no_declaration_supports_instead_of_dropping_it(et_supported, registry, bad) -> None:
    with pytest.raises(SensitivityError):
        robustness_envelope(et_supported, registry, **bad)


def test_bisection_stops_at_the_input_resolution_instead_of_rerunning_one_input(et_supported, registry) -> None:
    side = robustness_envelope(et_supported, registry, parameters=(AMB,), resolution=500).parameters[AMB]["increase"]
    inputs = [e["input"] for e in side["evaluations"]]
    assert len(inputs) == len(set(inputs))  # no physical state is run twice
    assert len(inputs) < 4 + 70  # the float bracket collapses long before 500 bisections
    assert side["kind"] == BoundaryKind.FAILS_BEYOND.value
    holds, fails = side["last_holding"], side["first_not_holding"]
    assert holds < fails and math.nextafter(holds, math.inf) >= fails - 2 * math.ulp(fails)
    by_input = {e["input"]: e["state"] for e in side["evaluations"]}
    assert by_input[holds] == "holds" and by_input[fails] == "fails"


def test_there_is_no_envelope_around_a_claim_that_is_not_supported(registry) -> None:
    contradicted = assess_claim(et_claim(target=type(et_claim().target)(value=Quantity(310.0, K))), registry)
    env = robustness_envelope(contradicted, registry)
    assert not env.established and env.parameters == {}


# ---------------------------------------------------------------------------
# Phase 8: challenge mode
# ---------------------------------------------------------------------------


def _ambient_range(lo, hi):
    return InputUncertainty((InputDistribution(AMB, "uniform", Quantity(lo, K), Quantity(hi, K), "declared operating range"),), 93)


def test_a_challenge_never_changes_the_verdict(registry) -> None:
    assessment = assess_claim(t3_claim(tolerance=Quantity(0.0002, K)), registry)
    before = assessment.to_dict()
    report = challenge_claim(assessment, registry)
    assert report.status == "weakened"
    assert assessment.verdict.value == "supported" and assessment.to_dict() == before
    (band,) = [c for c in report.challenges if c.kind is ChallengeKind.UNCERTAINTY_GUARD_BAND]
    assert band.weakened and band.evidence_refs  # the refinement runs that weakened it


def test_a_claim_that_holds_across_its_declared_range_survives(registry) -> None:
    report = challenge_claim(assess_claim(et_claim(input_uncertainty=_ambient_range(296.0, 304.0)), registry), registry)
    assert report.status == "survived_attempted_challenges"
    kinds = {c.kind for c in report.challenges if c.result is ChallengeResult.SURVIVED}
    assert {ChallengeKind.PARAMETER_BOUNDARY, ChallengeKind.VALIDITY_BOUNDARY_STRESS, ChallengeKind.UNCERTAINTY_GUARD_BAND} <= kinds


def test_a_claim_that_fails_inside_its_own_declared_range_is_weakened_by_execution_records(registry) -> None:
    report = challenge_claim(assess_claim(et_claim(input_uncertainty=_ambient_range(260.0, 340.0)), registry), registry)
    weakened = {c.kind: c for c in report.challenges if c.weakened}
    assert ChallengeKind.PARAMETER_BOUNDARY in weakened and ChallengeKind.VALIDITY_BOUNDARY_STRESS in weakened
    for challenge in weakened.values():
        assert challenge.attempted and challenge.evidence_refs


def test_nothing_weak_or_undeclared_can_weaken_a_claim(registry, et_supported) -> None:
    report = challenge_claim(et_supported, registry)
    assert not any(c.weakened for c in report.challenges)
    (solver,) = [c for c in report.challenges if c.kind is ChallengeKind.INDEPENDENT_SOLVER]
    assert solver.result is ChallengeResult.NOT_ATTEMPTED and not solver.attempted
    alternatives = [
        c for c in report.challenges
        if c.kind is ChallengeKind.ALTERNATIVE_MODEL
    ]
    assert alternatives
    battery = next(c for c in alternatives if c.target == "system.battery")
    assert battery.result is ChallengeResult.INCONCLUSIVE and not battery.weakened
    # Registry growth should increase challenge coverage, not make this test
    # demand that one historical alternative remain the only candidate.
    assert not any(c.weakened for c in alternatives)


def test_a_declared_range_that_cannot_be_stressed_is_reported_not_skipped(registry) -> None:
    duration = et_inputs()["stages[0].body.duration"]
    spec = InputUncertainty((InputDistribution("stages[0].body.duration", "uniform", Quantity(duration.magnitude * 0.9, duration.units),
                                               Quantity(duration.magnitude * 1.1, duration.units), "declared run length"),), 93)
    report = challenge_claim(assess_claim(et_claim(input_uncertainty=spec), registry), registry)
    (stress,) = [c for c in report.challenges if c.kind is ChallengeKind.VALIDITY_BOUNDARY_STRESS]
    assert stress.target == "stages[0].body.duration"
    assert stress.result is ChallengeResult.NOT_ATTEMPTED and not stress.attempted and not stress.weakened
    assert "not perturbable" in stress.detail


def test_a_range_declared_in_another_unit_is_stressed_in_the_stated_unit(registry) -> None:
    # 260 K .. 340 K written in degC around the stated 300 K: support fails at ~336 K, inside the range,
    # and the domain end at ~240 K lies outside it.
    spec = InputUncertainty((InputDistribution(AMB, "uniform", Quantity(260.0 - 273.15, "degree_Celsius"),
                                               Quantity(340.0 - 273.15, "degree_Celsius"), "declared operating range"),), 93)
    report = challenge_claim(assess_claim(et_claim(input_uncertainty=spec), registry), registry)
    (stress,) = [c for c in report.challenges if c.kind is ChallengeKind.VALIDITY_BOUNDARY_STRESS]
    assert stress.result is ChallengeResult.WEAKENED
    assert "increase: fails_beyond" in stress.detail and "decrease" not in stress.detail
    assert "[260, 340]" in stress.detail


def test_a_range_the_search_cannot_reach_is_inconclusive_not_survived(registry) -> None:
    tcr = et_inputs()[TCR]
    spec = InputUncertainty((InputDistribution(TCR, "uniform", Quantity(tcr.magnitude * 0.01, tcr.units),
                                               Quantity(tcr.magnitude * 1.99, tcr.units), "a range wider than the 95 % search cap"),), 93)
    report = challenge_claim(assess_claim(et_claim(input_uncertainty=spec), registry), registry)
    (stress,) = [c for c in report.challenges if c.kind is ChallengeKind.VALIDITY_BOUNDARY_STRESS]
    # The claim held on every probe, but the probes stop at 95 % of the nominal: both edges stay unexamined.
    assert stress.result is ChallengeResult.INCONCLUSIVE
    assert stress.attempted and not stress.weakened
    assert "decrease: shown to hold only to" in stress.detail and "increase: shown to hold only to" in stress.detail


def _side(kind, last, beyond=None):
    return {"kind": kind.value, "last_holding": last, "first_not_holding": beyond}


def test_a_failure_at_the_range_edge_itself_is_inside_not_unreached() -> None:
    from engcore.claims.analysis.challenge import _side_against_range

    edge_probe = math.nextafter(260.0, 0.0)  # the edge, one rounding below
    found = _side_against_range("decrease", _side(BoundaryKind.FAILS_BEYOND, 261.0, edge_probe), 300.0, 260.0, 340.0)
    assert found is not None and found[0] == "inside"
    assert _side_against_range("increase", _side(BoundaryKind.SEARCH_LIMIT, math.nextafter(340.0, 0.0)), 300.0, 260.0, 340.0) is None
    found = _side_against_range("increase", _side(BoundaryKind.FAILS_BEYOND, 339.0, 341.0), 300.0, 260.0, 340.0)
    assert found is not None and found[0] == "unreached"  # the bracket straddles the edge


def test_a_negative_stated_value_is_judged_against_the_edge_its_side_moves_toward() -> None:
    from engcore.claims.analysis.challenge import _side_against_range

    # x0 = -10 scaled down by 20 % is -8: "decrease" moves toward hi.
    assert _side_against_range("decrease", _side(BoundaryKind.SEARCH_LIMIT, -8.0), -10.0, -12.0, -8.0) is None
    assert _side_against_range("increase", _side(BoundaryKind.SEARCH_LIMIT, -12.0), -10.0, -12.0, -8.0) is None
    found = _side_against_range("decrease", _side(BoundaryKind.FAILS_BEYOND, -9.5, -9.0), -10.0, -12.0, -8.0)
    assert found is not None and found[0] == "inside"


def _measure(value, lo, hi):
    from claims_support import t3_point

    return MeasurementRecord("temperature_at_probe", Quantity(value, K),
                             Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, K), upper=Quantity(hi, K), method="m", source_kind=UncertaintySource.MEASUREMENT),
                             "cal:1", "lab:1", dict(t3_point()), "v1")


def test_admissible_external_evidence_that_disagrees_weakens_and_weak_evidence_cannot(registry) -> None:
    far = _measure(309.40, 309.35, 309.45)
    claim = t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False))
    pinned = TrustedExternalRegistry((TrustedPin(far.digest, SourceClass.MEASUREMENT, "c", "r"),))
    report = challenge_claim(assess_claim(claim, registry, external=(far,), trust=pinned), registry)
    measured = [c for c in report.challenges if c.kind is ChallengeKind.EXTERNAL_ORACLE and c.target.startswith("measurement")]
    assert measured and measured[0].weakened
    unpinned = challenge_claim(assess_claim(claim, registry, external=(far,)), registry)
    measured = [c for c in unpinned.challenges if c.kind is ChallengeKind.EXTERNAL_ORACLE and c.target.startswith("measurement")]
    assert measured and not measured[0].weakened and measured[0].result is ChallengeResult.NOT_ATTEMPTED
