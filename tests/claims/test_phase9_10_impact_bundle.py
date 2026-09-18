"""Phases 9 and 10 -- the decision dependency graph, impact analysis, and the replay bundle."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from claims_support import et_claim, et_inputs, t3_claim, t3_point
from engcore.claims import (
    BUILTIN_PROFILES,
    CapabilityRegistry,
    Change,
    ChangeKind,
    DecisionBinding,
    DecisionGraph,
    MeasurementRecord,
    TrustedExternalRegistry,
    TrustedPin,
    UncertaintyDemand,
    assess_claim,
    builtin_context,
    detect_changes,
    impact_of,
    record_digest,
)
from engcore.claims.bundle import (
    BundleStatus,
    ReplayTolerance,
    bundle_from_json,
    bundle_to_json,
    make_bundle,
    replay_bundle,
    verify_bundle,
)
from engcore.mcp.capabilities import ELECTROTHERMAL_CAPABILITY_ID, NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.evidence import SourceClass
from engcore.sria.uncertainty import UncertaintyChannel as C

T3_MODEL = "thermal.nafems_t3.transient_heat_1d"
T3_ORACLE = "nafems.p18.t3.transient_heat_1d"
LUMPED = "thermal.lumped.first_order_capacity"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


@pytest.fixture(scope="module")
def corpus(registry):
    claims = {
        "t3": t3_claim(),
        "t3_policy": t3_claim(decision=DecisionBinding("d-2", "Release the solver."),
                              decision_context=builtin_context("engineering_decision", influence="medium", consequence="medium", owner="o")),
        "et": et_claim(),
        "et_policy": et_claim(decision_context=builtin_context("research_exploration", influence="low", consequence="low", owner="o")),
    }
    return {name: assess_claim(c, registry) for name, c in claims.items()}


@pytest.fixture(scope="module")
def graph(corpus):
    return DecisionGraph([a.to_dict() for a in corpus.values()])


def _digest(assessment):
    return record_digest(assessment.to_dict())


# ---------------------------------------------------------------------------
# Phase 9
# ---------------------------------------------------------------------------


def test_queries_follow_identities_the_records_already_carry(graph, corpus) -> None:
    t3 = {_digest(corpus["t3"]), _digest(corpus["t3_policy"])}
    et = {_digest(corpus["et"]), _digest(corpus["et_policy"])}
    assert {s.digest for s in graph.decisions_depending_on_model(T3_MODEL)} == t3
    assert {s.digest for s in graph.decisions_depending_on_model(T3_MODEL, "1.0.0")} == t3
    assert graph.decisions_depending_on_model(T3_MODEL, "9.9.9") == []
    assert {s.digest for s in graph.decisions_depending_on_model(LUMPED)} == et
    assert {s.digest for s in graph.assessments_depending_on_oracle(T3_ORACLE)} == t3
    assert [s.digest for s in graph.decisions_using_policy("engineering_decision")] == [_digest(corpus["t3_policy"])]
    assert [s.digest for s in graph.decisions_using_policy("research_exploration", "1")] == [_digest(corpus["et_policy"])]


def test_impact_names_every_affected_assessment_with_the_chain_that_links_it(graph, corpus) -> None:
    report = impact_of(graph, [Change(ChangeKind.MODEL, LUMPED, "coefficient revised")])
    affected = {a["assessment"]: a for a in report.to_dict()["requires_reassessment"]}
    assert set(affected) == {_digest(corpus["et"]), _digest(corpus["et_policy"])}
    chain = affected[_digest(corpus["et"])]["because"][0]["chain"]
    assert chain[0].startswith("assessment:") and chain[-1].startswith(f"model:{LUMPED}@")
    assert any(step.startswith("capability:system.electrothermal@") for step in chain)
    assert "not modified" in report.to_dict()["notice"]


def test_impact_analysis_never_edits_a_historical_record(graph, corpus) -> None:
    before = {k: a.to_dict() for k, a in corpus.items()}
    impact_of(graph, [Change(ChangeKind.ORACLE, T3_ORACLE), Change(ChangeKind.POLICY, "engineering_decision")])
    assert {k: a.to_dict() for k, a in corpus.items()} == before


def test_a_changed_capability_is_detected_and_its_assessments_listed(corpus, registry) -> None:
    changed = CapabilityRegistry(replace(d, version="2") if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d for d in registry)
    records = [a.to_dict() for a in corpus.values()]
    changes = detect_changes(records, changed)
    assert [c.kind for c in changes] == [ChangeKind.CAPABILITY]
    affected = {a["assessment"] for a in impact_of(DecisionGraph(records), changes).to_dict()["requires_reassessment"]}
    assert affected == {_digest(corpus["t3"]), _digest(corpus["t3_policy"])}
    assert detect_changes(records, registry) == ()


def test_a_changed_policy_profile_is_detected(corpus, registry) -> None:
    profiles = dict(BUILTIN_PROFILES)
    profiles["engineering_decision"] = replace(BUILTIN_PROFILES["engineering_decision"], version="2")
    changes = detect_changes([a.to_dict() for a in corpus.values()], registry, policy_profiles=profiles)
    assert [c.kind for c in changes] == [ChangeKind.POLICY]

def test_a_changed_external_trust_registry_is_detected_and_impacts_the_bound_assessment(registry) -> None:
    measurement = MeasurementRecord(
        "temperature_at_probe",
        Quantity(309.76, "kelvin"),
        Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(309.66, "kelvin"),
            upper=Quantity(309.86, "kelvin"),
            method="m",
            source_kind=UncertaintySource.MEASUREMENT,
        ),
        "cal:1",
        "lab:1",
        dict(t3_point()),
        "v1",
    )
    old_trust = TrustedExternalRegistry(
        (TrustedPin(measurement.digest, SourceClass.MEASUREMENT, "curator", "reviewed"),)
    )
    assessment = assess_claim(t3_claim(), registry, external=(measurement,), trust=old_trust)
    record = assessment.to_dict()

    assert detect_changes([record], registry, trust_registry=old_trust) == ()

    new_trust = TrustedExternalRegistry(())
    changes = detect_changes([record], registry, trust_registry=new_trust)
    assert [change.kind for change in changes] == [ChangeKind.TRUST_REGISTRY]
    assert changes[0].key == old_trust.digest

    affected = impact_of(DecisionGraph([record]), changes).to_dict()["requires_reassessment"]
    assert [item["assessment"] for item in affected] == [record_digest(record)]


# ---------------------------------------------------------------------------
# Phase 10
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundled(registry):
    claim = t3_claim(uncertainty=UncertaintyDemand(frozenset({C.NUMERICAL}), None, False),
                     decision_context=builtin_context("engineering_decision", influence="medium", consequence="medium", owner="o"))
    assessment = assess_claim(claim, registry)
    return bundle_from_json(bundle_to_json(make_bundle(assessment, registry)))


def test_bundle_environment_carries_a_reproducibility_fingerprint(bundled) -> None:
    environment = bundled["environment"]
    assert environment["schema"] == "engcore.claim_replay_environment/1"
    assert len(environment["fingerprint"]) == 64
    assert set(environment["distribution"]) == {"crafty", "numpy", "scipy", "pint"}
    assert set(environment["python"]) == {"version", "implementation"}
    assert set(environment["platform"]) == {"system", "release", "machine"}
    assert set(environment["git"]) == {"commit", "dirty"}

def test_a_bundle_verifies_without_execution_and_replays_identically(bundled, registry, monkeypatch) -> None:
    import engcore.claims.execution as execution

    def refuse(*a, **k):
        raise AssertionError("verify_bundle executed physics")

    with monkeypatch.context() as patched:
        patched.setattr(execution, "execute_plan", refuse)
        check = verify_bundle(bundled, registry)
    assert check.status is BundleStatus.VERIFIED and check.verdict == "supported"
    replay = replay_bundle(bundled, registry)
    assert replay.status is BundleStatus.VERIFIED and replay.differences == () and replay.compared_numbers > 10


@pytest.mark.parametrize(
    "edit",
    [
        lambda b: b["record"].__setitem__("verdict", "contradicted"),
        lambda b: b["record"]["claim"]["target"]["value"].__setitem__("magnitude", 309.7),
        lambda b: b["record"]["uncertainty_studies"][0]["estimate"].__setitem__("half_width", 1e-9),
        lambda b: b["record"]["result"]["value"].__setitem__("magnitude", 309.8),
        lambda b: b["trust_pins"].append({"record_digest": "0" * 64, "source_class": "measurement", "curator": "x", "rationale": "y"}),
        lambda b: b["capability"].__setitem__("summary", "edited"),
        lambda b: b["environment"].__setitem__("python", "0.0"),
    ],
    ids=["verdict", "claim", "study", "value", "trust", "capability", "environment"],
)
def test_any_edit_to_a_bundle_is_detected(bundled, registry, edit) -> None:
    forged = copy.deepcopy(bundled)
    edit(forged)
    assert verify_bundle(forged, registry).status is BundleStatus.TAMPERED


@pytest.mark.parametrize(
    "edit",
    [
        lambda b: b["record"].__setitem__("verdict", "contradicted"),
        lambda b: b["record"]["policy"].__setitem__("satisfied", False),
        lambda b: b["record"]["evidence_gaps"].__setitem__("gaps", []),
    ],
    ids=["verdict", "policy", "gaps"],
)
def test_an_edit_with_a_recomputed_digest_is_still_refused(bundled, registry, edit) -> None:
    from engcore.claims._records import tagged_digest
    from engcore.claims.bundle import _TAG

    forged = copy.deepcopy(bundled)
    edit(forged)
    forged["bundle_digest"] = tagged_digest(_TAG, {k: v for k, v in forged.items() if k != "bundle_digest"})
    check = verify_bundle(forged, registry)
    assert check.status is BundleStatus.TAMPERED, check.to_dict()


def test_a_changed_registry_is_reported_not_mistaken_for_tampering(bundled, registry) -> None:
    changed = CapabilityRegistry(replace(d, version="2") if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d for d in registry)
    check = verify_bundle(bundled, changed)
    assert check.status is BundleStatus.REGISTRY_CHANGED and check.verdict == "supported"
    assert replay_bundle(bundled, changed).status is BundleStatus.REGISTRY_CHANGED


def test_replay_detects_a_changed_solver_result(bundled, registry) -> None:
    from engcore.claims import CapabilityRun, InstanceReport

    genuine = registry.get(NAFEMS_T3_CAPABILITY_ID).executor

    def drifted(case, *, run_id):
        (item,) = genuine(case, run_id=run_id).reports
        values = dict(item.report.values)
        values["temperature_at_probe"] = Quantity(values["temperature_at_probe"].magnitude + 1e-7, "kelvin")
        return CapabilityRun(reports=(InstanceReport(None, replace(item.report, values=values)),))

    drifting = CapabilityRegistry(replace(d, executor=drifted) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d for d in registry)
    exact = replay_bundle(bundled, drifting)
    assert exact.status is BundleStatus.NOT_REPRODUCIBLE and any("/result/" in d for d in exact.differences)
    tolerant = replay_bundle(bundled, drifting, tolerance=ReplayTolerance(relative=1e-6))
    assert tolerant.status is BundleStatus.VERIFIED


def test_a_bundle_with_external_evidence_carries_its_trust_and_replays(registry) -> None:
    m = MeasurementRecord("temperature_at_probe", Quantity(309.76, "kelvin"),
                          Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(309.66, "kelvin"), upper=Quantity(309.86, "kelvin"),
                                      method="m", source_kind=UncertaintySource.MEASUREMENT),
                          "cal:1", "lab:1", dict(t3_point()), "v1")
    trust = TrustedExternalRegistry((TrustedPin(m.digest, SourceClass.MEASUREMENT, "c", "r"),))
    assessment = assess_claim(t3_claim(), registry, external=(m,), trust=trust)
    bundle = make_bundle(assessment, registry, trust=trust)
    assert verify_bundle(bundle, registry).status is BundleStatus.VERIFIED
    assert replay_bundle(bundle, registry).status is BundleStatus.VERIFIED
    with pytest.raises(Exception):
        make_bundle(assessment, registry)  # the production registry is not the one it was judged under
