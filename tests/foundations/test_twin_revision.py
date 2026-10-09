"""Big Rock J: Scientific Twin revisions -- identity, lineage, context-bound evidence, no invention."""

from __future__ import annotations

import pytest

from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import ScientificTwin, TwinDatum, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.systems.twin_revision import (
    ApplicabilityRecord, ApplicabilityState, EvidenceReference, EvidenceRole, TwinRevision, TwinRevisionRefusal,
    UncertaintyReference, UncertaintyStatus, verify_lineage,
)

G1, G2, MAT = "1" * 64, "2" * 64, "3" * 64


def twin(kind=TwinKind.CANDIDATE, thickness=0.01):
    return ScientificTwin("slab", "1", kind, models=(ModelReference("conduction.steady_1d", "1"),),
                          declarations=(TwinDatum("thickness", Quantity(thickness, "m")),))


def rev(**kw):
    base = dict(twin=twin(), geometry_digests=(G1,), material_digests=(MAT,))
    base.update(kw)
    return TwinRevision(**base)


def test_identity_is_deterministic_and_changes_with_any_context_input():
    a = rev()
    assert a.revision_id == rev().revision_id and TwinRevision.from_dict(a.to_dict()).revision_id == a.revision_id
    assert rev(geometry_digests=(G2,)).context_digest != a.context_digest
    assert rev(twin=twin(thickness=0.02)).context_digest != a.context_digest
    assert rev(material_digests=()).context_digest != a.context_digest
    tampered = a.to_dict()
    tampered["context"]["geometry_digests"] = [G2]
    with pytest.raises(TwinRevisionRefusal, match="does not match"):
        TwinRevision.from_dict(tampered)


def test_evidence_is_bound_to_its_context_and_never_transfers():
    a = rev()
    ev = EvidenceReference("run:fea-001", EvidenceRole.VERIFICATION, a.context_digest)
    b = a.with_evidence(ev)
    assert b.parent == a.revision_id and b.evidence == (ev,)
    with pytest.raises(TwinRevisionRefusal, match="another context"):
        rev(geometry_digests=(G2,), evidence=(ev,))
    c = b.derive(geometry_digests=(G2,), change_note="thicker web")
    assert c.evidence == () and c.dropped_evidence == ("run:fea-001",) and c.parent == b.revision_id
    same = b.derive(change_note="no context change")
    assert same.evidence == b.evidence
    store = {x.revision_id: x for x in (a, b, c)}
    assert verify_lineage(c, store) == (a.revision_id, b.revision_id, c.revision_id)
    with pytest.raises(TwinRevisionRefusal, match="missing"):
        verify_lineage(c, {c.revision_id: c})


def test_candidate_stays_candidate_and_cannot_hold_calibration():
    a = rev()
    assert a.is_candidate
    with pytest.raises(TwinRevisionRefusal, match="kind"):
        a.derive(twin=ScientificTwin("slab", "2", TwinKind.REFERENCE, models=(ModelReference("conduction.steady_1d", "1"),)), change_note="x")
    with pytest.raises(TwinRevisionRefusal, match="CALIBRATED"):
        a.with_evidence(EvidenceReference("fit:1", EvidenceRole.CALIBRATION, a.context_digest))
    with pytest.raises(TwinRevisionRefusal, match="re-established"):
        a.derive(evidence=(), change_note="smuggle")


def test_applicability_and_uncertainty_are_never_implied():
    a = rev()
    assert a.applicability_of("conduction.steady_1d", "1").state is ApplicabilityState.NOT_ASSESSED
    assert a.uncertainty_of("heat_flow").status is UncertaintyStatus.UNKNOWN
    with pytest.raises(TwinRevisionRefusal, match="never asserted bare"):
        ApplicabilityRecord("conduction.steady_1d", "1", ApplicabilityState.IN_DOMAIN)
    with pytest.raises(TwinRevisionRefusal, match="does not declare"):
        rev(applicability=(ApplicabilityRecord("cfd.rans", "1", ApplicabilityState.NOT_ASSESSED),))
    with pytest.raises(TwinRevisionRefusal, match="without a reference"):
        UncertaintyReference("heat_flow", UncertaintyStatus.QUANTIFIED)
    assessed = rev(applicability=(ApplicabilityRecord("conduction.steady_1d", "1", ApplicabilityState.IN_DOMAIN, "assess:7"),),
                   uncertainty=(UncertaintyReference("heat_flow", UncertaintyStatus.QUANTIFIED, "uq:3"),))
    moved = assessed.derive(material_digests=(G2,), change_note="other alloy")
    assert moved.applicability_of("conduction.steady_1d", "1").state is ApplicabilityState.NOT_ASSESSED
    assert moved.uncertainty_of("heat_flow").status is UncertaintyStatus.UNKNOWN
