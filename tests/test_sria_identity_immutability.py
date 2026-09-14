"""Regression tests for SRIA scientific-content and belief immutability."""

import pytest

from engcore.scientific.results.uncertainty import Uncertainty
from engcore.sria.errors import EvidenceError
from engcore.sria.evidence import ClaimBinding, ClaimType, Evidence, EvidenceStatus, SourceClass
from engcore.sria.gateway import BeliefEntry
from engcore.sria.uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)


def _uncertainty() -> UncertaintyDeclaration:
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED),
        channels={UncertaintyChannel.ALEATORIC: Uncertainty.unknown()},
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="e-1",
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(
            subject_kind="component",
            subject_ref="wing",
            qualifiers={"station": "root"},
        ),
        claim_payload={"value": {"samples": [1.0, 2.0]}},
        uncertainty=_uncertainty(),
        provenance_ref="run-1",
        domain_pack_ref="aero@1",
        metadata={"review": {"tags": ["candidate"]}},
    )


def test_evidence_identity_bearing_containers_are_recursively_immutable():
    evidence = _evidence()

    with pytest.raises(TypeError):
        evidence.claim_payload["value"]["samples"][0] = 9.0
    with pytest.raises(TypeError):
        evidence.claim_binding.qualifiers["station"] = "tip"
    with pytest.raises(TypeError):
        evidence.uncertainty.channels[UncertaintyChannel.NUMERICAL] = Uncertainty.unknown()

    assert evidence.record_hash


def test_evidence_serialization_is_detached_from_the_record():
    evidence = _evidence()
    payload = evidence.to_dict()

    payload["claim_payload"]["value"]["samples"][0] = 99.0
    payload["metadata"]["review"]["tags"].append("edited")

    assert evidence.claim_payload["value"]["samples"][0] == 1.0
    assert list(evidence.metadata["review"]["tags"]) == ["candidate"]


def test_record_hash_revalidates_live_scientific_content_before_identity_is_used():
    evidence = _evidence()
    original_hash = evidence.content_hash

    # Deliberately bypass the ordinary frozen-record API. The boundary must
    # still refuse to reuse the old identity/admission for changed content.
    object.__setattr__(evidence, "claim_payload", {"value": {"samples": [999.0]}})

    assert evidence.content_hash == original_hash
    with pytest.raises(EvidenceError, match="no longer matches content_hash"):
        _ = evidence.record_hash


def test_belief_entry_payload_cannot_be_mutated_through_public_read_access():
    entry = BeliefEntry(
        evidence_id="e-1",
        belief_key="qoi_value|component:wing;station=root",
        claim_type="qoi_value",
        content_hash="a" * 64,
        record_hash="b" * 64,
        status=EvidenceStatus.ACCEPTED,
        admitted_by="arbiter-1",
        claim_payload={"value": {"samples": [1.0, 2.0]}},
    )

    with pytest.raises(TypeError):
        entry.claim_payload["value"]["samples"][0] = 5.0

    serialized = entry.to_dict()
    serialized["claim_payload"]["value"]["samples"][0] = 5.0
    assert entry.claim_payload["value"]["samples"][0] == 1.0
