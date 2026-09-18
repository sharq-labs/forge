"""Sprint 3 — source ancestry and fail-closed independence semantics."""

from __future__ import annotations

import hashlib
import json

from engcore.sria import (
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Evidence,
    EvidenceStatus,
    ModelDiscrepancy,
    SourceClass,
    SubjectModel,
    UncertaintyDeclaration,
)
from engcore.sria.gateway import BeliefEntry, ScientificBelief, _TOKEN


def _uncertainty() -> UncertaintyDeclaration:
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(
            kind=DiscrepancyKind.ZERO_DECLARED,
            rationale="lineage fixture only",
        ),
    )


def _evidence(
    evidence_id: str,
    *,
    run: str,
    source_refs=(),
    complete: bool = False,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="temperature"),
        claim_payload={"value": 350.0, "units": "kelvin"},
        uncertainty=_uncertainty(),
        provenance_ref=run,
        domain_pack_ref="thermal",
        context_ref="context:test",
        source_refs=tuple(source_refs),
        source_closure_complete=complete,
    )


def _entry(evidence: Evidence) -> BeliefEntry:
    return BeliefEntry(
        evidence_id=evidence.evidence_id,
        belief_key=evidence.belief_key,
        claim_type=evidence.claim_type.value,
        content_hash=evidence.content_hash,
        record_hash=evidence.record_hash,
        status=EvidenceStatus.ACCEPTED,
        admitted_by="fixture",
        claim_payload=dict(evidence.claim_payload),
        source_roots=evidence.independence_roots,
        source_closure_complete=evidence.source_closure_complete,
    )


def _belief(*evidence: Evidence) -> ScientificBelief:
    belief = ScientificBelief()
    for item in evidence:
        belief._apply(_TOKEN, _entry(item))
    return belief


def test_lineage_is_record_identity_not_claim_content() -> None:
    a = _evidence(
        "a",
        run="run-a",
        source_refs=("dataset:shared",),
        complete=True,
    )
    b = _evidence(
        "b",
        run="run-b",
        source_refs=("dataset:other",),
        complete=True,
    )

    assert a.content_hash == b.content_hash
    assert a.record_hash != b.record_hash


def test_legacy_evidence_hash_is_unchanged_without_lineage_fields() -> None:
    evidence = _evidence("legacy", run="run-legacy")
    expected = hashlib.sha256(
        json.dumps(
            {
                "evidence_id": evidence.evidence_id,
                "source_class": evidence.source_class.value,
                "provenance_ref": evidence.provenance_ref,
                "content_hash": evidence.content_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert evidence.source_refs == ()
    assert evidence.source_closure_complete is False
    assert evidence.record_hash == expected


def test_lineage_round_trip_preserves_roots_and_completeness() -> None:
    evidence = _evidence(
        "round-trip",
        run="run-1",
        source_refs=("dataset:x", "observation:y"),
        complete=True,
    )

    restored = Evidence.from_dict(evidence.to_dict())

    assert restored == evidence
    assert restored.independence_roots == (
        "dataset:x",
        "observation:y",
        "run:run-1",
    )


def test_incomplete_closure_never_proves_two_records_independent() -> None:
    a = _evidence("a", run="run-a", complete=False)
    b = _evidence("b", run="run-b", complete=False)
    belief = _belief(a, b)

    assert len(belief.contributions(a.belief_key)) == 2
    groups = belief.independence_groups(a.belief_key)
    assert len(groups) == 1
    assert belief.independent_source_count(a.belief_key) == 1


def test_shared_atomic_source_is_one_independence_group() -> None:
    a = _evidence(
        "a",
        run="run-a",
        source_refs=("dataset:shared",),
        complete=True,
    )
    b = _evidence(
        "b",
        run="run-b",
        source_refs=("dataset:shared",),
        complete=True,
    )
    belief = _belief(a, b)

    assert belief.independent_source_count(a.belief_key) == 1


def test_disjoint_complete_closures_are_independent_groups() -> None:
    a = _evidence(
        "a",
        run="run-a",
        source_refs=("dataset:a",),
        complete=True,
    )
    b = _evidence(
        "b",
        run="run-b",
        source_refs=("dataset:b",),
        complete=True,
    )
    belief = _belief(a, b)

    groups = belief.independence_groups(a.belief_key)
    assert len(groups) == 2
    assert belief.independent_source_count(a.belief_key) == 2


def test_dependency_grouping_is_transitive() -> None:
    a = _evidence(
        "a",
        run="run-a",
        source_refs=("dataset:a",),
        complete=True,
    )
    b = _evidence(
        "b",
        run="run-b",
        source_refs=("dataset:a", "dataset:b"),
        complete=True,
    )
    c = _evidence(
        "c",
        run="run-c",
        source_refs=("dataset:b",),
        complete=True,
    )
    belief = _belief(a, b, c)

    groups = belief.independence_groups(a.belief_key)
    assert len(groups) == 1
    assert {entry.evidence_id for entry in groups[0]} == {"a", "b", "c"}
