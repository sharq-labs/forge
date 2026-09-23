"""Quantitative UQ -- production quantitative UQ: numerical (refinement) and parameter (propagation), end to end.

Every quantified channel here comes from real executions of a production capability: the NAFEMS T3
refinement ladder for NUMERICAL, and seeded propagation through the electrothermal system for
EPISTEMIC_PARAMETER. Nothing is injected into a report.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import replace

import pytest

from claims_support import et_claim, et_inputs, t3_claim
from engcore.claims import (
    AssessmentForgeryError,
    CapabilityDeclarationError,
    CapabilityRegistry,
    CapabilityRun,
    ClaimContractError,
    ClaimKind,
    ClaimTarget,
    EstimateStatus,
    InputDistribution,
    InputUncertainty,
    InstanceReport,
    NumericalUQError,
    PropagatedRun,
    RefinementLevel,
    RefinementStudy,
    UncertaintyCapability,
    UncertaintyDemand,
    assess_claim,
    draw_samples,
    estimate_numerical_uncertainty,
    estimate_parameter_uncertainty,
    verify_assessment,
    wilks_confidence,
)
from engcore.claims.parameter_uq import minimum_samples
from engcore.mcp.capabilities import ELECTROTHERMAL_CAPABILITY_ID, NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.mcp.sria_bridge import evidence_from_credibility_report
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel as C

K = "kelvin"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _levels(values, ratio=2):
    return [RefinementLevel(k, v, {"n": 64 // ratio**k}, f"r{k}") for k, v in enumerate(values)]


def _est(values, **kw):
    args = dict(quantity="q", units=K, refinement_ratio=2.0, formal_order=2.0, order_tolerance=0.25)
    args.update(kw)
    return estimate_numerical_uncertainty(_levels(values), **args)


# ---------------------------------------------------------------------------
# 2A: the estimator's rules
# ---------------------------------------------------------------------------


def test_a_second_order_sequence_is_quantified_and_brackets_the_exact_value() -> None:
    exact, c = 300.0, 0.8
    values = [exact + c * 1e-3 * (2**k) ** 2 for k in range(4)]  # finest first: error c*h**2, h doubling
    est = _est(values)
    assert est.status is EstimateStatus.QUANTIFIED
    assert abs(est.observed_orders[0] - 2.0) < 1e-9
    record = est.to_uncertainty()
    assert record.source_kind is UncertaintySource.NUMERICAL and record.kind is UncertaintyKind.INTERVAL
    assert record.lower.magnitude < exact < record.upper.magnitude
    assert record.confidence_level is None  # no coverage probability is claimed


@pytest.mark.parametrize(
    "values, fragment",
    [
        ([300.0, 300.1], "at least three"),
        ([300.0, 300.1, 299.8], "oscillatory"),
        ([300.0, 300.2, 300.3], "do not shrink"),
        ([300.0, 300.0, 300.0], "round-off"),
        ([300.0, 300.0 + 1e-15, 300.0 + 2e-15], "round-off"),
        ([300.0, 300.001, 300.009], "outside the declared formal order"),  # p ~ 3
        ([300.0, 300.001, 300.005, 300.013], "disagree"),  # p1 = 2.0, p2 = 1.0
        ([300.0, None, 300.1], "no finite value"),
        ([300.0, float("inf"), 300.1], "no finite value"),
    ],
)
def test_every_rule_failure_is_unknown_never_zero(values, fragment) -> None:
    est = _est(values)
    assert est.status is EstimateStatus.UNKNOWN
    assert fragment in est.failure_reason
    record = est.to_uncertainty()
    assert not record.is_quantified and record.lower is None and record.upper is None


def test_the_used_order_is_never_above_the_formal_order() -> None:
    values = [300.0, 300.001, 300.001 + 0.001 * 2**2.2]
    est = _est(values)
    assert est.status is EstimateStatus.QUANTIFIED and est.observed_orders[0] > 2.0 and est.order_used == 2.0


@pytest.mark.parametrize("bad", [dict(refinement_ratio=1.0), dict(formal_order=0.0), dict(order_tolerance=-1.0)])
def test_an_undeclared_or_meaningless_study_is_refused(bad) -> None:
    with pytest.raises(NumericalUQError):
        _est([300.0, 300.001, 300.004], **bad)


# ---------------------------------------------------------------------------
# 2B: the propagation estimator
# ---------------------------------------------------------------------------


def test_wilks_needs_93_runs_for_two_sided_95_95() -> None:
    assert minimum_samples() == 93
    assert wilks_confidence(93) >= 0.95 > wilks_confidence(92)


def _runs(values, usable=True):
    return [PropagatedRun(i, f"p{i}", {}, v, usable, None if usable else "outside") for i, v in enumerate(values)]


def test_propagation_is_quantified_only_with_every_run_usable_and_the_nominal_inside() -> None:
    values = [300.0 + 0.01 * i for i in range(93)]
    ok = estimate_parameter_uncertainty(_runs(values), quantity="q", units=K, nominal=300.2)
    assert ok.quantified and ok.to_uncertainty().source_kind is UncertaintySource.PARAMETER
    bad = _runs(values)
    bad[5] = replace(bad[5], usable=False, problem="model x is outside_validated_domain")
    dropped = estimate_parameter_uncertainty(bad, quantity="q", units=K, nominal=300.2)
    assert not dropped.quantified and "bias" in dropped.failure_reason
    outside = estimate_parameter_uncertainty(_runs(values), quantity="q", units=K, nominal=299.0)
    assert not outside.quantified
    few = estimate_parameter_uncertainty(_runs(values[:50]), quantity="q", units=K, nominal=300.2)
    assert not few.quantified and not few.to_uncertainty().is_quantified


def test_input_distributions_are_declarations_bound_to_stated_values() -> None:
    inputs = et_inputs()
    amb = inputs["stages[0].body.ambient_temperature"]
    good = InputUncertainty((InputDistribution("stages[0].body.ambient_temperature", "normal", amb, Quantity(1.0, K), "spec"),), 93)
    et_claim(input_uncertainty=good)  # accepted
    off = InputUncertainty((InputDistribution("stages[0].body.ambient_temperature", "normal", Quantity(301.0, K), Quantity(1.0, K), "x"),), 93)
    with pytest.raises(ClaimContractError, match="centered"):
        et_claim(input_uncertainty=off)
    unstated = InputUncertainty((InputDistribution("stages[0].body.not_an_input", "normal", amb, Quantity(1.0, K), "x"),), 93)
    with pytest.raises(ClaimContractError, match="does not state"):
        et_claim(input_uncertainty=unstated)
    with pytest.raises(ClaimContractError):
        InputUncertainty(good.distributions, 50)
    with pytest.raises(ClaimContractError):
        InputDistribution("stages[0].body.ambient_temperature", "normal", amb, Quantity(-1.0, K), "x")


def test_draws_are_seeded_by_the_plan_and_reproducible() -> None:
    inputs = et_inputs()
    amb = inputs["stages[0].body.ambient_temperature"]
    spec = InputUncertainty((InputDistribution("stages[0].body.ambient_temperature", "normal", amb, Quantity(1.0, K), "x"),), 93)
    assert draw_samples(spec, "a") == draw_samples(spec, "a")
    assert draw_samples(spec, "a") != draw_samples(spec, "b")


def test_a_claim_with_input_uncertainty_round_trips_and_changes_identity() -> None:
    inputs = et_inputs()
    amb = inputs["stages[0].body.ambient_temperature"]
    spec = InputUncertainty((InputDistribution("stages[0].body.ambient_temperature", "uniform", Quantity(299.0, K), Quantity(301.0, K), "x"),), 93)
    plain, with_uq = et_claim(), et_claim(input_uncertainty=spec)
    assert plain.identity_digest != with_uq.identity_digest
    assert "input_uncertainty" not in plain.to_dict()  # old claims keep their identity
    from engcore.claims import ScientificClaim

    assert ScientificClaim.from_dict(json.loads(json.dumps(with_uq.to_dict()))) == with_uq


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def test_a_channel_cannot_be_declared_quantifiable_without_a_study_behind_it(registry) -> None:
    t3 = registry.get(NAFEMS_T3_CAPABILITY_ID)
    with pytest.raises(CapabilityDeclarationError, match="NUMERICAL"):
        replace(t3, refinement=None)
    et = registry.get(ELECTROTHERMAL_CAPABILITY_ID)
    with pytest.raises(CapabilityDeclarationError, match="EPISTEMIC_PARAMETER"):
        replace(et, perturbable=())
    with pytest.raises(CapabilityDeclarationError, match="not a declared NUMERICS count"):
        replace(t3, refinement=replace(t3.refinement, refined_inputs={"length": 5}))
    with pytest.raises(CapabilityDeclarationError, match="no ladder"):
        replace(t3, refinement=replace(t3.refinement, levels=9))
    with pytest.raises(CapabilityDeclarationError, match="at least 3"):
        RefinementStudy(frozenset({"q"}), {"n": 8}, 2, 2, 2.0, 0.25, "b")


def test_declarations_with_studies_round_trip_and_capabilities_without_keep_their_digest(registry) -> None:
    from engcore.claims import CapabilityDeclaration

    for d in registry:
        back = CapabilityDeclaration.from_dict(json.loads(json.dumps(d.to_dict())))
        assert back.digest == d.digest
    battery = registry.get("system.battery").to_dict()
    assert "refinement" not in battery
    assert battery["perturbable"]
    cstr = registry.get("kinetics.cstr.production").to_dict()
    assert "refinement" not in cstr and "perturbable" not in cstr


# ---------------------------------------------------------------------------
# 2C: closure, end to end on the production T3 vertical
# ---------------------------------------------------------------------------


def _numerical(**kw):
    return t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False), **kw)


@pytest.fixture(scope="module")
def t3_supported(registry):
    return assess_claim(_numerical(), registry)


def test_known_numerical_uncertainty_safely_inside_the_band_is_supported(t3_supported, registry) -> None:
    record = t3_supported.to_dict()
    assert record["verdict"] == "supported"
    assert record["comparison"]["rule"] == "guard_band_linear_sum"
    assert record["uncertainty"]["channels"] == {"numerical": True}
    assert record["assurance"]["verdict"] == "valid"
    (study,) = record["uncertainty_studies"]
    assert study["estimate"]["status"] == "quantified"
    assert abs(study["estimate"]["observed_orders"][0] - 2.0) < 0.1
    assert [r["run_id"].rsplit("~", 1)[-1] for r in study["runs"]] == ["0", "1", "2"]
    assert all(r["usable"] for r in study["runs"])
    # Every variant run is named by the evidence it supports.
    assert len(t3_supported.evidence.source_refs) == 3
    verify_assessment(json.loads(json.dumps(record)), registry)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(tolerance=Quantity(0.0002, K)),  # point inside a 0.2 mK band, GCI ~3.7 mK
        dict(kind=ClaimKind.THRESHOLD, operator=ConstraintOperator.LESS_THAN, tolerance=None,
             target=ClaimTarget(value=Quantity(309.7520, K))),  # point below, band crosses
    ],
    ids=["tolerance_band", "threshold"],
)
def test_an_interval_that_crosses_the_boundary_is_insufficient(registry, overrides) -> None:
    record = assess_claim(_numerical(**overrides), registry).to_dict()
    assert record["comparison"]["point_satisfied"] is True
    assert record["comparison"]["outcome"] == "undecided"
    assert record["verdict"] == "insufficient_evidence"


def test_removing_uq_evidence_cannot_improve_the_verdict(t3_supported, registry) -> None:
    record = t3_supported.to_dict()
    stripped = json.loads(json.dumps(record))
    stripped["uncertainty_studies"] = []
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(stripped, registry)
    widened = json.loads(json.dumps(record))
    widened["uncertainty_studies"][0]["estimate"]["half_width"] = 0.0
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(widened, registry)
    moved = json.loads(json.dumps(record))
    moved["uncertainty_studies"][0]["runs"][1]["value"] += 0.001
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(moved, registry)
    # The same claim against a capability with no study: never better than with one.
    t3 = registry.get(NAFEMS_T3_CAPABILITY_ID)
    none = CapabilityRegistry(
        replace(d, refinement=None, uncertainty=UncertaintyCapability({}, "none")) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d
        for d in registry
    )
    assert assess_claim(_numerical(), none).to_dict()["verdict"] == "insufficient_evidence"


def test_numerical_uq_cannot_satisfy_model_form(registry) -> None:
    only_model_form = assess_claim(t3_claim(uncertainty=UncertaintyDemand(frozenset({C.MODEL_FORM}), None, False)), registry).to_dict()
    assert only_model_form["verdict"] == "insufficient_evidence"
    assert only_model_form["uncertainty_studies"] == []  # no study quantifies MODEL_FORM
    both = assess_claim(t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL, C.MODEL_FORM}), None, False)), registry).to_dict()
    assert both["uncertainty"]["channels"] == {"numerical": True, "model_form": False}
    assert both["verdict"] == "insufficient_evidence"
    assert "uncertainty:model_form" in both["assurance"]["unmet_obligations"]


def test_combined_uncertainty_cannot_masquerade_as_a_single_channel(registry, t3_supported) -> None:
    report = t3_supported.report
    combined = Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(309.7, K), upper=Quantity(309.8, K), method="m", source_kind=UncertaintySource.COMBINED)
    parameter = replace(combined, source_kind=UncertaintySource.PARAMETER)
    unknown = Uncertainty.unknown("nothing")
    for record in (combined, parameter, unknown):
        with pytest.raises(ValueError):
            evidence_from_credibility_report(
                report, quantity_name="temperature_at_probe", evidence_id="e", domain_pack_ref="p",
                context_ref="c", channel_records={C.NUMERICAL: record},
            )


def test_a_report_record_and_a_study_record_in_one_channel_are_refused_not_merged(registry) -> None:
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor
    own = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.001, K), method="own", source_kind=UncertaintySource.NUMERICAL)

    def run(case, *, run_id):
        (item,) = genuine(case, run_id=run_id).reports
        return CapabilityRun(reports=(InstanceReport(None, replace(item.report, uncertainty={"temperature_at_probe": own})),))

    wrapped = CapabilityRegistry(replace(d, executor=run) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d for d in registry)
    record = assess_claim(_numerical(), wrapped).to_dict()
    assert record["verdict"] == "insufficient_evidence" and record["evidence"] is None


def _wrap_t3(registry, transform):
    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def run(case, *, run_id):
        return transform(genuine, case, run_id)

    return CapabilityRegistry(replace(d, executor=run) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d for d in registry)


def test_a_refused_level_makes_the_channel_unknown(registry) -> None:
    from engcore.claims.errors import CapabilityExecutionRefused

    def refuse_coarsest(genuine, case, run_id):
        if run_id.endswith("~numerical~2"):
            raise CapabilityExecutionRefused("no")
        return genuine(case, run_id=run_id)

    record = assess_claim(_numerical(), _wrap_t3(registry, refuse_coarsest)).to_dict()
    (study,) = record["uncertainty_studies"]
    assert "level 2 is not usable" in study["problem"]
    assert record["uncertainty"]["channels"] == {"numerical": False}
    assert record["verdict"] == "insufficient_evidence"


def test_a_study_whose_finest_level_is_not_the_reported_run_is_unknown(registry) -> None:
    def drift_level_zero(genuine, case, run_id):
        run = genuine(case, run_id=run_id)
        if not run_id.endswith("~numerical~0"):
            return run
        (item,) = run.reports
        values = dict(item.report.values)
        values["temperature_at_probe"] = Quantity(values["temperature_at_probe"].magnitude + 1e-6, K)
        return CapabilityRun(reports=(InstanceReport(None, replace(item.report, values=values)),))

    record = assess_claim(_numerical(), _wrap_t3(registry, drift_level_zero)).to_dict()
    assert "does not reproduce the reported value" in record["uncertainty_studies"][0]["problem"]
    assert record["verdict"] == "insufficient_evidence"


def test_a_stated_grid_that_admits_no_ladder_leaves_the_channel_unavailable(registry) -> None:
    point = dict(t3_claim().operating_context)
    record = assess_claim(_numerical(operating_context=point, known_inputs={"numerics.n_cells": 90}), registry).to_dict()
    step = next(s for s in record["plan"]["steps"] if s["step_id"] == "uncertainty:numerical")
    assert step["availability"] == "unavailable" and "not divisible" in step["detail"]["unavailable_reason"]
    assert record["verdict"] == "insufficient_evidence"


# ---------------------------------------------------------------------------
# 2B end to end on the production electrothermal vertical
# ---------------------------------------------------------------------------


def _parameter_claim(sigma=1.0, **kw):
    inputs = et_inputs()
    amb = inputs["stages[0].body.ambient_temperature"]
    rr = inputs["stages[0].conductor.reference_resistance"]
    spec = InputUncertainty(
        (
            InputDistribution("stages[0].body.ambient_temperature", "normal", amb, Quantity(sigma, K), "sensor datasheet"),
            InputDistribution("stages[0].conductor.reference_resistance", "uniform",
                              Quantity(rr.magnitude * 0.98, rr.units), Quantity(rr.magnitude * 1.02, rr.units), "2% part tolerance"),
        ),
        93,
    )
    demand = kw.pop("demand", UncertaintyDemand(frozenset({C.EPISTEMIC_PARAMETER}), None, False))
    return et_claim(uncertainty=demand, input_uncertainty=spec, **kw)


@pytest.fixture(scope="module")
def et_propagated(registry):
    return assess_claim(_parameter_claim(), registry)


def test_parameter_propagation_supports_a_claim_through_real_runs(et_propagated, registry) -> None:
    record = et_propagated.to_dict()
    assert record["verdict"] == "supported"
    (study,) = record["uncertainty_studies"]
    est = study["estimate"]
    assert est["quantified"] and len(est["runs"]) == 93 and est["confidence"] >= 0.95
    assert est["lower"] <= record["result"]["value"]["magnitude"] <= est["upper"]
    assert est["upper"] - est["lower"] > 0.0
    assert record["uncertainty"]["channels"] == {"epistemic_parameter": True}
    verify_assessment(json.loads(json.dumps(record)), registry)


def test_editing_a_propagated_run_or_its_inputs_is_refused(et_propagated, registry) -> None:
    record = et_propagated.to_dict()
    moved = copy.deepcopy(record)
    moved["uncertainty_studies"][0]["estimate"]["runs"][7]["value"] += 1.0
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(moved, registry)
    redrawn = copy.deepcopy(record)
    redrawn["uncertainty_studies"][0]["estimate"]["runs"][0]["inputs"]["stages[0].body.ambient_temperature"]["magnitude"] = 300.0
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(redrawn, registry)


def test_a_distribution_that_leaves_the_validated_domain_is_unknown_not_truncated(registry) -> None:
    record = assess_claim(_parameter_claim(sigma=400.0), registry).to_dict()
    est = record["uncertainty_studies"][0]["estimate"]
    assert not est["quantified"] and "not usable" in est["failure_reason"]
    assert record["verdict"] == "insufficient_evidence"


def test_parameter_uq_cannot_satisfy_a_numerical_demand(registry) -> None:
    demand = UncertaintyDemand(frozenset({C.NUMERICAL, C.EPISTEMIC_PARAMETER}), None, False)
    record = assess_claim(_parameter_claim(demand=demand), registry).to_dict()
    assert record["uncertainty"]["channels"] == {"epistemic_parameter": True, "numerical": False}
    assert record["verdict"] == "insufficient_evidence"
