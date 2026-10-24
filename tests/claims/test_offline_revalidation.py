"""Trust Repair Pass 1 (Review 3, R3-01): a consistently rewritten record is not verified support.

The attack: rewrite a record CONSISTENTLY -- every derived part rebuilt with the
same pure function ``verify_assessment`` uses, and the unkeyed bundle digest
recomputed. Before this pass it verified: a NAFEMS T3 record forged to 305 K,
about 95 benchmark tolerances away, was VERIFIED and SUPPORTED with
BENCHMARK_VALIDATED, and an electrothermal record moved from 319.28 K to 299 K
was VERIFIED and SUPPORTED.

Offline verification now separates three things:

- a level re-earned from the stored values against repository-pinned evidence
  (VERIFIED);
- a level only a re-execution can re-earn (REPLAY_REQUIRED, never VERIFIED);
- a stored comparison its pinned evidence no longer reproduces (TAMPERED).
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from claims_support import et_claim, t3_claim
from engcore.claims import ClaimTarget, UncertaintyDemand, assess_claim, verify_assessment
from engcore.claims._records import tagged_digest
from engcore.claims.assessment import AssessmentForgeryError, _build_record
from engcore.claims.compiler import compile_claim
from engcore.claims.external_evidence import PRODUCTION_EXTERNAL_REGISTRY
from engcore.claims.planning import ExperimentPlan
from engcore.claims.replay.bundle import _TAG, BundleStatus, make_bundle, replay_bundle, verify_bundle
from engcore.claims.revalidation import RevalidationStanding
from engcore.credibility.evidence import CredibilityEvidenceReport
from engcore.mcp.capabilities import production_registry
from engcore.scientific import oracles
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel

T3_CHECK = "nafems_t3_external_benchmark"
T3_QOI = "temperature_at_probe"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _forge(record, registry, mutate, *, claim=None):
    """What an adversary does: edit the report, re-derive every derived part with the verifier's own builder."""
    compiled = compile_claim(record["claim"] if claim is None else claim, registry)
    plan = ExperimentPlan.from_dict(record["plan"]) if claim is None else None
    if plan is None:
        from engcore.claims.planning import plan_experiment

        plan = plan_experiment(compiled, registry)
    view = dict(record["execution"])
    report = mutate(CredibilityEvidenceReport.from_dict(record["credibility"]["report"]), plan)
    if claim is not None:
        from engcore.claims.execution import binding_problems

        view.update(run_id=plan.run_id, plan_digest=plan.digest, report_run_id=report.run_id,
                    binding_problems=list(binding_problems(plan, registry, report, dict(compiled.claim.supplied_inputs))))
    rebuilt, _ = _build_record(compiled.claim, compiled, plan, view, report, registry, None, (), PRODUCTION_EXTERNAL_REGISTRY)
    return json.loads(json.dumps(rebuilt))


def _value(qoi, magnitude):
    def mutate(report, _plan):
        values = dict(report.values)
        values[qoi] = Quantity(magnitude, str(values[qoi].units))
        return dataclasses.replace(report, values=values)
    return mutate


def _redigest(bundle):
    body = {k: v for k, v in bundle.items() if k != "bundle_digest"}
    return {**body, "bundle_digest": tagged_digest(_TAG, body)}


def _bundle_around(genuine_bundle, forged_record):
    return _redigest({**copy.deepcopy(genuine_bundle), "record": forged_record})


@pytest.fixture(scope="module")
def t3(registry):
    assessment = assess_claim(t3_claim(), registry)
    return assessment, make_bundle(assessment, registry)


@pytest.fixture(scope="module")
def et300(registry):
    """An electrothermal claim the genuine run CONTRADICTS: 319.28 K is not below 300 K."""
    assessment = assess_claim(et_claim(target=ClaimTarget(value=Quantity(300.0, "kelvin"))), registry)
    assert assessment.to_dict()["verdict"] == "contradicted"
    return assessment, make_bundle(assessment, registry)


# --- 1. T3 forged 305 K ------------------------------------------------------------------------
def test_a_t3_record_forged_to_305_kelvin_is_tampered(t3, registry):
    assessment, bundle = t3
    forged = _forge(assessment.to_dict(), registry, _value(T3_QOI, 305.0))
    with pytest.raises(AssessmentForgeryError, match="does not earn what the record says it earned"):
        verify_assessment(copy.deepcopy(forged), registry)
    check = verify_bundle(_bundle_around(bundle, forged), registry)
    assert check.status is BundleStatus.TAMPERED and check.verdict is None
    assert replay_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.TAMPERED


# --- 2. 319.28 K -> 299 K, consistently rewritten --------------------------------------------
def test_a_consistently_rewritten_analytic_record_is_never_verified(et300, registry):
    assessment, bundle = et300
    forged = _forge(assessment.to_dict(), registry, _value("final_temperature", 299.0))
    assert forged["verdict"] == "supported"  # the forgery itself is self-consistent and says SUPPORTED
    back = verify_assessment(copy.deepcopy(forged), registry)
    assert back.revalidation.standing is RevalidationStanding.REPLAY_REQUIRED
    assert [s.level for s in back.revalidation.levels] == [ValidationLevel.ANALYTICALLY_VERIFIED]
    check = verify_bundle(_bundle_around(bundle, forged), registry)
    assert check.status is BundleStatus.REPLAY_REQUIRED and check.status is not BundleStatus.VERIFIED
    assert any("only replay_bundle can" in p for p in check.problems)
    replay = replay_bundle(_bundle_around(bundle, forged), registry)
    assert replay.status is BundleStatus.NOT_REPRODUCIBLE  # re-execution gives 319.28 K, not 299 K


# --- 3. changed run id + recomputed digest ----------------------------------------------------
def test_a_changed_run_id_is_tampered_even_with_a_recomputed_digest(t3, registry):
    _, bundle = t3
    forged = copy.deepcopy(bundle)
    forged["record"]["execution"]["run_id"] = "claim-0000000000000000"
    forged["record"]["plan"]["content"]["run_id"] = "claim-0000000000000000"
    assert verify_bundle(_redigest(forged), registry).status is BundleStatus.TAMPERED


# --- 4. changed output + recomputed digest ----------------------------------------------------
@pytest.mark.parametrize("rederived", [False, True], ids=["edited-only", "record-re-derived"])
def test_a_changed_output_is_tampered_with_or_without_re_derivation(t3, registry, rederived):
    assessment, bundle = t3
    if rederived:
        record = _forge(assessment.to_dict(), registry, _value(T3_QOI, 305.0))
    else:
        record = copy.deepcopy(assessment.to_dict())
        record["credibility"]["report"]["values"][T3_QOI]["magnitude"] = 305.0
    assert verify_bundle(_bundle_around(bundle, record), registry).status is BundleStatus.TAMPERED


# --- 5. changed claim + recomputed digest -----------------------------------------------------
def test_a_retargeted_claim_with_a_matching_forged_output_is_tampered(t3, registry):
    assessment, bundle = t3

    def retarget(report, plan):
        values = dict(report.values)
        values[T3_QOI] = Quantity(305.0, "kelvin")
        provenance = dataclasses.replace(report.provenance, run_id=plan.run_id)
        return dataclasses.replace(report, values=values, run_id=plan.run_id, provenance=provenance)

    claim = t3_claim(target=ClaimTarget(value=Quantity(305.0, "kelvin"))).to_dict()
    forged = _forge(assessment.to_dict(), registry, retarget, claim=claim)
    assert forged["verdict"] == "supported"  # self-consistent, and false
    assert verify_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.TAMPERED


# --- 6. a stale oracle check copied to a changed value ----------------------------------------
@pytest.mark.parametrize("magnitude", [305.0, 309.70, 309.80], ids=["far", "edge-of-oracle-band", "inside-claim-band"])
def test_a_genuine_oracle_check_kept_on_a_changed_value_is_tampered(t3, registry, magnitude):
    """309.70 and 309.80 K are inside the claim's own 0.5 K band, so the claim would still read SUPPORTED;
    the stored check's residual is the genuine run's, and the pinned comparison of the new value is not."""
    assessment, bundle = t3
    forged = _forge(assessment.to_dict(), registry, _value(T3_QOI, magnitude))
    assert verify_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.TAMPERED


def test_an_oracle_check_re_issued_from_public_registry_lines_is_tampered(t3, registry):
    """Review 3 S4: the check is written from scratch with the pin's own public strings and residual 0."""
    assessment, bundle = t3
    (key, declaration), = oracles._TRUSTED_ORACLE_DECLARATIONS.items()

    def reissue(report, _plan):
        values = dict(report.values)
        values[T3_QOI] = Quantity(305.0, "kelvin")
        fake = ValidationCheck(
            name=T3_CHECK, outcome=ValidationOutcome.PASS, establishes=ValidationLevel.BENCHMARK_VALIDATED,
            residual=0.0, tolerance=1.0, detail="re-issued",
            evidence=(f"oracle:{key[0]}@{key[1]}", f"sha256:{declaration['evidence_digest']}",
                      f"reference:{declaration['reference']}", f"metrics:{T3_QOI}",
                      "oracle-authority:repository-pinned", "oracle-binding:the prediction names the record it came from"),
        )
        return dataclasses.replace(report, values=values,
                                   validation=tuple(fake if c.name == T3_CHECK else c for c in report.validation))

    forged = _forge(assessment.to_dict(), registry, reissue)
    with pytest.raises(AssessmentForgeryError, match="stored as pass"):
        verify_assessment(copy.deepcopy(forged), registry)
    assert verify_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.TAMPERED


# --- 7. valid untouched bundles ---------------------------------------------------------------
def test_an_untouched_benchmark_bundle_is_scientifically_revalidated(t3, registry):
    assessment, bundle = t3
    back = verify_assessment(json.loads(json.dumps(assessment.to_dict())), registry)
    assert back.revalidation.standing is RevalidationStanding.SCIENTIFICALLY_REVALIDATED
    (level,) = back.revalidation.levels
    assert level.level is ValidationLevel.BENCHMARK_VALIDATED and level.check_name == T3_CHECK
    check = verify_bundle(json.loads(json.dumps(bundle)), registry)
    # Offline verification never says VERIFIED: that the report is the planned run is not re-earnable.
    assert check.status is BundleStatus.SCIENTIFICALLY_REVALIDATED and check.verdict == "supported"
    assert any("needs replay_bundle" in p for p in check.problems)


def test_a_genuine_report_of_another_run_is_never_verified_offline(t3, registry):
    """Review round 2: the default-grid T3 report (160 cells) carried under a claim planned at 40 cells, whose
    real run is INSUFFICIENT_EVIDENCE. Every pinned check passes. Only re-execution tells the runs apart, so
    offline verification must not call it VERIFIED, and replay must refuse it."""
    from engcore.claims import assess_claim as assess

    assessment, bundle = t3
    claim = t3_claim(known_inputs={"numerics.n_cells": 40, "numerics.n_steps": 8})
    assert assess(claim, registry).to_dict()["verdict"] == "insufficient_evidence"

    def substitute(report, plan):
        provenance = dataclasses.replace(report.provenance, run_id=plan.run_id)
        return dataclasses.replace(report, run_id=plan.run_id, provenance=provenance)

    forged = _forge(assessment.to_dict(), registry, substitute, claim=claim.to_dict())
    assert forged["verdict"] == "supported"
    check = verify_bundle(_bundle_around(bundle, forged), registry)
    assert check.status is not BundleStatus.VERIFIED
    assert check.status is BundleStatus.SCIENTIFICALLY_REVALIDATED  # what the pinned evidence can say, and no more
    assert replay_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.NOT_REPRODUCIBLE


def test_offline_verification_never_returns_verified(t3, registry):
    _, bundle = t3
    et = make_bundle(assess_claim(et_claim(), registry), registry)
    for candidate in (bundle, et):
        assert verify_bundle(candidate, registry).status is not BundleStatus.VERIFIED
        assert replay_bundle(candidate, registry).status is BundleStatus.VERIFIED


def test_an_untouched_analytic_bundle_is_consistent_and_still_needs_replay(registry):
    assessment = assess_claim(et_claim(), registry)
    assert assessment.to_dict()["verdict"] == "supported"
    check = verify_bundle(make_bundle(assessment, registry), registry)
    assert check.status is BundleStatus.REPLAY_REQUIRED and check.verdict == "supported"


def test_a_demanded_run_quantified_uncertainty_channel_needs_replay(registry):
    """A narrower stored interval would turn a band comparison 'satisfied'; offline it is consistency only."""
    claim = t3_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), None, False))
    assessment = assess_claim(claim, registry)
    back = verify_assessment(assessment.to_dict(), registry)
    assert back.revalidation.standing is RevalidationStanding.REPLAY_REQUIRED
    assert [c for c, _ in back.revalidation.channels] == ["numerical"]
    assert verify_bundle(make_bundle(assessment, registry), registry).status is BundleStatus.REPLAY_REQUIRED


# --- 8. valid replayed bundles ----------------------------------------------------------------
def test_replay_re_earns_what_offline_verification_cannot(t3, registry):
    _, bundle = t3
    assert replay_bundle(bundle, registry).status is BundleStatus.VERIFIED
    et = make_bundle(assess_claim(et_claim(), registry), registry)
    assert verify_bundle(et, registry).status is BundleStatus.REPLAY_REQUIRED
    replay = replay_bundle(et, registry)
    assert replay.status is BundleStatus.VERIFIED and replay.differences == ()


# --- review round: a check re-issued CONSISTENTLY inside the oracle band ------------------------
def _consistent(magnitude):
    """Value moved inside the oracle band and the check's residual recomputed for it, as a careful forger would."""
    def mutate(report, plan):
        values = dict(report.values)
        values[T3_QOI] = Quantity(magnitude, "kelvin")
        checks = tuple(
            dataclasses.replace(c, residual=abs(magnitude - 309.75) / 0.05) if c.name == T3_CHECK else c
            for c in report.validation
        )
        provenance = dataclasses.replace(report.provenance, run_id=plan.run_id)
        return dataclasses.replace(report, values=values, validation=checks, run_id=plan.run_id, provenance=provenance)
    return mutate


@pytest.mark.parametrize("claim_kwargs, magnitude, forged_verdict", [
    # Review 3 follow-up F1 / adversary C1: the genuine run (309.750 K) contradicts "T > 309.795 K".
    (dict(kind="threshold", operator=">", target=309.795), 309.7999, "supported"),
    # adversary C1b: the genuine run supports "T < 309.78 K"; the forger flips it to contradicted.
    (dict(kind="threshold", operator="<", target=309.78), 309.79, "contradicted"),
    # a band that excludes the benchmark value but lies inside the oracle's own band.
    (dict(kind="tolerance_band", operator="==", target=309.799, tolerance=0.0005), 309.799, "supported"),
], ids=["gt-309.795", "lt-309.78-flipped", "narrow-band"])
def test_a_verdict_decided_inside_the_oracle_band_is_never_verified(t3, registry, claim_kwargs, magnitude, forged_verdict):
    from engcore.claims import ClaimKind
    from engcore.scientific.ir.constraints import ConstraintOperator

    assessment, bundle = t3
    claim = t3_claim(
        kind=ClaimKind(claim_kwargs["kind"]),
        operator=ConstraintOperator(claim_kwargs["operator"]),
        target=ClaimTarget(value=Quantity(claim_kwargs["target"], "kelvin")),
        tolerance=None if "tolerance" not in claim_kwargs else Quantity(claim_kwargs["tolerance"], "kelvin"),
    )
    forged = _forge(assessment.to_dict(), registry, _consistent(magnitude), claim=claim.to_dict())
    assert forged["verdict"] == forged_verdict
    back = verify_assessment(copy.deepcopy(forged), registry)  # self-consistent, and its level IS re-earned
    assert back.revalidation.standing is RevalidationStanding.REPLAY_REQUIRED
    assert any("decision boundary" in reason for reason in back.revalidation.reasons)
    check = verify_bundle(_bundle_around(bundle, forged), registry)
    assert check.status is BundleStatus.REPLAY_REQUIRED
    assert replay_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.NOT_REPRODUCIBLE


def test_a_true_claim_on_a_value_the_benchmark_admits_is_the_documented_authenticity_limit(t3, registry):
    """309.78 K is inside the benchmark's band, and "309.75 +/- 0.5 K" holds for EVERY value that band admits, so
    the comparison is what the pinned benchmark decides: SCIENTIFICALLY_REVALIDATED, never VERIFIED, because
    nothing offline shows the run produced 309.78 K. Replay does."""
    assessment, bundle = t3
    forged = _forge(assessment.to_dict(), registry, _consistent(309.78))
    check = verify_bundle(_bundle_around(bundle, forged), registry)
    assert check.status is BundleStatus.SCIENTIFICALLY_REVALIDATED and check.verdict == "supported"
    assert replay_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.NOT_REPRODUCIBLE


def test_a_forged_insufficient_verdict_cannot_hide_a_real_contradiction(et300, registry):
    """Adversary P2: deleting the analytic check and moving the value turns a genuine CONTRADICTED into INSUFFICIENT."""
    assessment, bundle = et300

    def hide(report, _plan):
        values = dict(report.values)
        values["final_temperature"] = Quantity(299.0, "kelvin")
        return dataclasses.replace(report, values=values,
                                   validation=tuple(c for c in report.validation if c.establishes is None))

    forged = _forge(assessment.to_dict(), registry, hide)
    assert forged["verdict"] == "insufficient_evidence"
    assert verify_bundle(_bundle_around(bundle, forged), registry).status is BundleStatus.REPLAY_REQUIRED


def test_a_level_claimed_without_the_bound_prediction_line_is_refuted(t3, registry):
    """Review follow-up F2: the issuer rule does not read the binding line; revalidation does."""
    assessment, bundle = t3

    def unbind(report, _plan):
        checks = tuple(
            dataclasses.replace(c, evidence=tuple(
                "oracle-binding:withheld:the prediction does not name the record it was computed from"
                if line.startswith("oracle-binding:") else line for line in c.evidence))
            if c.name == T3_CHECK else c
            for c in report.validation
        )
        return dataclasses.replace(report, validation=checks)

    forged = _forge(assessment.to_dict(), registry, unbind)
    with pytest.raises(AssessmentForgeryError, match="bound-prediction"):
        verify_assessment(copy.deepcopy(forged), registry)


def test_a_route_cannot_answer_with_anything_but_its_trusted_pin(registry):
    """Why review follow-up F4 cannot be built today: a declaration refuses a route that answers with ANOTHER
    oracle, or with other content under the pin's own id. Together with the issuer rule (which refuses a check
    whose digest is not the trusted one) a planned check always names its route's pin."""
    from engcore.claims.errors import CapabilityDeclarationError
    from engcore.domains.thermal_models.nafems_t3_oracle import CONDITIONS, ORACLE_ID, ORACLE_VERSION, REFERENCE
    from engcore.scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation

    other = OracleEvidenceSet.create(
        oracle_id=ORACLE_ID, version=ORACLE_VERSION, kind=OracleKind.BENCHMARK_DATASET, reference=REFERENCE,
        observations=(OracleObservation(metric=T3_QOI, expected=Quantity(300.0, "kelvin"),
                                        absolute_tolerance=Quantity(0.05, "kelvin"), conditions=CONDITIONS),),
    )
    declaration = registry.get("benchmark.nafems_t3")
    routes = tuple(dataclasses.replace(r, oracle_provider=(lambda: other)) if r.oracle_provider is not None else r
                   for r in declaration.routes)
    with pytest.raises(CapabilityDeclarationError, match="not trusted"):
        dataclasses.replace(declaration, routes=routes)


def test_a_planned_oracle_check_the_route_does_not_answer_for_is_refuted_not_downgraded(t3, registry, monkeypatch):
    """F4, defence in depth: should a planned oracle check ever name evidence the plan's route does not answer
    with, the record is refused as a forgery -- never quietly downgraded to REPLAY_REQUIRED."""
    from engcore.claims import revalidation

    assessment, _ = t3
    monkeypatch.setattr(revalidation, "_routed_evidence", lambda *a, **k: None)
    with pytest.raises(AssessmentForgeryError, match="does not route to"):
        verify_assessment(copy.deepcopy(assessment.to_dict()), registry)


@pytest.mark.parametrize("record", [[], None, "x"], ids=["list", "none", "string"])
def test_a_malformed_record_is_tampered_not_a_crash(t3, registry, record):
    _, bundle = t3
    forged = _redigest({**copy.deepcopy(bundle), "record": record})
    assert verify_bundle(forged, registry).status is BundleStatus.TAMPERED


# --- 9. single-field tamper -------------------------------------------------------------------
@pytest.mark.parametrize("edit", [
    lambda r: r.__setitem__("verdict", "contradicted"),
    lambda r: r["verification"].__setitem__("attained", []),   # F4: the benchmark level is a verification level
    lambda r: r["credibility"]["report"]["validity"][0].__setitem__("version", "0.9.0"),
    lambda r: r["claim"]["tolerance"].__setitem__("magnitude", 50.0),
], ids=["verdict", "attained-levels", "model-version", "tolerance"])
def test_a_single_field_edit_with_a_recomputed_digest_is_tampered(t3, registry, edit):
    _, bundle = t3
    forged = copy.deepcopy(bundle)
    edit(forged["record"])
    assert verify_bundle(_redigest(forged), registry).status is BundleStatus.TAMPERED


def test_coupled_replay_precondition_keeps_parent_and_subresult_identities_distinct(et300):
    from engcore.claims.replay.bundle import _has_bound_replay_result

    record = et300[0].to_dict()
    assert record["execution"]["run_id"] != record["execution"]["report_run_id"]
    assert _has_bound_replay_result(record)


@pytest.mark.parametrize("path,value", [
    (("execution", "run_id"), "another-parent"),
    (("execution", "report_run_id"), "another-report"),
    (("result", "report_run_id"), "another-report"),
    (("credibility", "report", "run_id"), "another-report"),
    (("credibility", "report", "provenance", "run_id"), "another-parent"),
    (("credibility", "report", "provenance"), None),
    (("execution", "outcome"), "refused"),
    (("execution", "binding_problems"), ["unbound"]),
    (("basis", "executed"), False),
    (("basis", "bound"), False),
])
def test_coupled_replay_precondition_refuses_each_broken_identity_or_execution_link(et300, path, value):
    from engcore.claims.replay.bundle import _has_bound_replay_result

    record = copy.deepcopy(et300[0].to_dict())
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert not _has_bound_replay_result(record)
