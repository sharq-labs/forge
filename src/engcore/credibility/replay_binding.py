"""Bind assurance and law identities into generic replay artifacts."""

from __future__ import annotations

from ..scientific.equations import LawReference
from ..scientific.replay_core import ArtifactIdentity
from ..scientific.knowledge import KnowledgeSnapshot
from .evidence_graph import EvidenceGraph, evidence_graph_fingerprint
from .assurance_bundle import AssuranceBundle


def assurance_artifact(bundle:AssuranceBundle)->ArtifactIdentity:
    return ArtifactIdentity("assurance_bundle","scientific-assurance",bundle.digest)


def law_artifact(reference:LawReference)->ArtifactIdentity:
    return ArtifactIdentity("scientific_law",reference.law_id,reference.fingerprint)


def knowledge_snapshot_artifact(snapshot: KnowledgeSnapshot) -> ArtifactIdentity:
    return ArtifactIdentity(
        "knowledge_snapshot",
        snapshot.snapshot_id,
        snapshot.digest,
    )


def evidence_graph_artifact(graph: EvidenceGraph) -> ArtifactIdentity:
    return ArtifactIdentity(
        "evidence_graph",
        "scientific-evidence",
        evidence_graph_fingerprint(graph),
    )
