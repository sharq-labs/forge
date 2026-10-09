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
    assert a.revision_id == rev().revision_id and TwinRevision.from_dict(a.serialize()).revision_id == a.revision_id
    assert rev(geometry_digests=(G2,)).context_digest != a.context_digest
    assert rev(twin=twin(thickness=0.02)).context_digest != a.context_digest
    assert rev(material_digests=()).context_digest != a.context_digest
    tampered = a.serialize()
    tampered["context"]["geometry_digests"] = [G2]
    with pytest.raises(TwinRevisionRefusal, match="does not match"):
        TwinRevision.from_dict(tampered)
    smuggled = a.serialize()
    smuggled["evidence"].append({"ref": "x", "role": "verification", "context_digest": a.context_digest})
    with pytest.raises(TwinRevisionRefusal, match="revision id"):
        TwinRevision.from_dict(smuggled)
    with pytest.raises(TwinRevisionRefusal, match="revision id"):
        TwinRevision.from_dict(a.to_dict())
    # descriptive edits are not a new context, so they cannot be used to shed evidence
    import dataclasses
    assert rev(twin=dataclasses.replace(twin(), description="renamed")).context_digest == a.context_digest


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
    for role in (EvidenceRole.CALIBRATION, EvidenceRole.VALIDATION, EvidenceRole.MEASUREMENT):
        with pytest.raises(TwinRevisionRefusal, match="no physical article"):
            a.with_evidence(EvidenceReference("x:1", role, a.context_digest))
    embedded = ScientificTwin("slab", "1", TwinKind.CANDIDATE, models=(ModelReference("conduction.steady_1d", "1"),),
                              calibration_evidence_refs=("fit:1",))
    with pytest.raises(TwinRevisionRefusal, match="no context-bound"):
        rev(twin=embedded)
    calibrated = ScientificTwin("slab", "1", TwinKind.CALIBRATED, models=(ModelReference("conduction.steady_1d", "1"),),
                                calibration_evidence_refs=("fit:1",))
    with pytest.raises(TwinRevisionRefusal, match="no context-bound"):
        rev(twin=calibrated)
    ctx = TwinRevision.context_digest_for(calibrated, geometry_digests=(G1,), material_digests=(MAT,))
    good = rev(twin=calibrated, evidence=(EvidenceReference("fit:1", EvidenceRole.CALIBRATION, ctx),))
    assert good.context_digest == ctx
    with pytest.raises(TwinRevisionRefusal, match="no context-bound"):
        good.derive(geometry_digests=(G2,), change_note="new geometry drops the calibration; the twin's ref cannot stay")
    cal_twin = ScientificTwin("slab", "1", TwinKind.REFERENCE, models=(ModelReference("conduction.steady_1d", "1"),))
    upgraded = rev(twin=cal_twin, parent=a.revision_id)
    with pytest.raises(TwinRevisionRefusal, match="changes the twin kind"):
        verify_lineage(upgraded, {a.revision_id: a})
    with pytest.raises(TwinRevisionRefusal, match="re-established"):
        a.derive(evidence=(), change_note="smuggle")


def test_evidence_pointers_are_checked_against_their_records():
    a = rev()
    b = a.with_evidence(EvidenceReference("run:1", EvidenceRole.PROVIDER_RUN, a.context_digest))
    b.verify_evidence({"run:1": {"context_digest": a.context_digest, "role": "provider_run"}})
    with pytest.raises(TwinRevisionRefusal, match="another context or role"):
        b.verify_evidence({"run:1": {"context_digest": a.context_digest, "role": "validation"}})
    with pytest.raises(TwinRevisionRefusal, match="no available record"):
        b.verify_evidence({})


def test_applicability_and_uncertainty_are_never_implied():
    a = rev()
    assert a.applicability_of("conduction.steady_1d", "1").state is ApplicabilityState.NOT_ASSESSED
    assert a.uncertainty_of("heat_flow").status is UncertaintyStatus.UNKNOWN
    with pytest.raises(TwinRevisionRefusal, match="never asserted bare"):
        ApplicabilityRecord("conduction.steady_1d", "1", ApplicabilityState.IN_DOMAIN)
    with pytest.raises(TwinRevisionRefusal, match="another context"):
        rev(geometry_digests=(G2,), applicability=(ApplicabilityRecord("conduction.steady_1d", "1", ApplicabilityState.IN_DOMAIN, "assess:G1",
                                                                       a.context_digest),))
    with pytest.raises(TwinRevisionRefusal, match="does not declare"):
        rev(applicability=(ApplicabilityRecord("cfd.rans", "1", ApplicabilityState.NOT_ASSESSED),))
    with pytest.raises(TwinRevisionRefusal, match="without a reference"):
        UncertaintyReference("heat_flow", UncertaintyStatus.QUANTIFIED)
    with pytest.raises(TwinRevisionRefusal, match="another context"):
        rev(geometry_digests=(G2,), uncertainty=(UncertaintyReference("heat_flow", UncertaintyStatus.QUANTIFIED, "uq:3", a.context_digest),))
    assessed = a.with_assessments(
        applicability=(ApplicabilityRecord("conduction.steady_1d", "1", ApplicabilityState.IN_DOMAIN, "assess:7", a.context_digest),),
        uncertainty=(UncertaintyReference("heat_flow", UncertaintyStatus.QUANTIFIED, "uq:3", a.context_digest),))
    moved = assessed.derive(material_digests=(G2,), change_note="other alloy")
    assert moved.applicability_of("conduction.steady_1d", "1").state is ApplicabilityState.NOT_ASSESSED
    assert moved.uncertainty_of("heat_flow").status is UncertaintyStatus.UNKNOWN
