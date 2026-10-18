"""Replay needs executed, bound results even when refusal records agree."""
from dataclasses import replace

import pytest

from claims_support import t3_claim
from engcore.claims import CapabilityRegistry, UncertaintyDemand, assess_claim
from engcore.claims.errors import CapabilityExecutionRefused, CapabilityInputError
from engcore.claims.replay.bundle import BundleStatus, make_bundle, replay_bundle
from engcore.credibility.evidence import CredibilityEvidenceError
from engcore.product.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.scientific.errors import InvalidModelRealization
from engcore.sria.uncertainty import UncertaintyChannel


@pytest.mark.parametrize("outcome", ["refused", "wrong_run", "not_planned"])
def test_matching_nonexecutions_cannot_receive_scientific_replay_verification(outcome):
    calls = []
    production = production_registry()
    genuine = production.get(NAFEMS_T3_CAPABILITY_ID).executor

    def executor(case, *, run_id):
        calls.append(run_id)
        if outcome == "refused":
            raise CapabilityExecutionRefused("deliberate admissibility refusal")
        return genuine(case, run_id="another-run")

    registry = CapabilityRegistry(
        replace(d, executor=executor) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d
        for d in production
    )
    claim = t3_claim(operating_context={}) if outcome == "not_planned" else t3_claim()
    assessment = assess_claim(claim, registry)
    record = assessment.to_dict()
    assert record["verdict"] == "insufficient_evidence"
    if outcome == "wrong_run":
        assert record["result"] is not None and record["credibility"] is not None
        assert record["execution"]["binding_problems"] and record["basis"]["bound"] is False
    else:
        assert record["result"] is None and record["credibility"] is None
    if outcome == "not_planned":
        assert record["execution"] is None and calls == []
    else:
        assert len(calls) == 1
    replay = replay_bundle(make_bundle(assessment, registry), registry)
    assert replay.status is BundleStatus.NOT_REPRODUCIBLE
    assert any("completed, bound scientific result" in problem for problem in replay.differences)
    assert len(calls) == (0 if outcome == "not_planned" else 2)


def test_real_bound_insufficient_result_replays_without_becoming_supported():
    registry = production_registry()
    claim = t3_claim(uncertainty=UncertaintyDemand(frozenset({UncertaintyChannel.MODEL_FORM}), None, False))
    assessment = assess_claim(claim, registry)
    record = assessment.to_dict()
    assert record["execution"]["outcome"] == "completed"
    assert record["basis"]["bound"] is True and record["result"] is not None
    assert record["verdict"] == "insufficient_evidence"
    bundle = make_bundle(assessment, registry)
    assert replay_bundle(bundle, registry).status is BundleStatus.VERIFIED
    assert bundle["record"]["verdict"] == "insufficient_evidence"
    assert assess_claim(claim, registry).to_dict()["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize("fault", (CredibilityEvidenceError, InvalidModelRealization))
def test_structural_scientific_faults_propagate_instead_of_minting_refusal_records(fault):
    def broken(case, *, run_id):
        raise fault("deliberate structural fault")

    registry = CapabilityRegistry(
        replace(d, executor=broken) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d
        for d in production_registry()
    )
    with pytest.raises(fault, match="structural fault"):
        assess_claim(t3_claim(), registry)


@pytest.mark.parametrize("fault", (CapabilityExecutionRefused, CapabilityInputError))
def test_expected_input_refusals_remain_insufficient(fault):
    def refused(case, *, run_id):
        raise fault("deliberate expected refusal")

    registry = CapabilityRegistry(
        replace(d, executor=refused) if d.capability_id == NAFEMS_T3_CAPABILITY_ID else d
        for d in production_registry()
    )
    record = assess_claim(t3_claim(), registry).to_dict()
    assert record["execution"]["outcome"] == "refused_by_system"
    assert record["verdict"] == "insufficient_evidence"
    assert record["result"] is None and record["evidence"] is None
