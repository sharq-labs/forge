from engcore.credibility.evidence_graph import EvidenceGraph
from engcore.credibility.knowledge_evidence import evidence_from_knowledge
from engcore.credibility.replay_binding import (
    evidence_graph_artifact, knowledge_snapshot_artifact,
)
from datetime import datetime, timezone
from tests.scientific.knowledge.helpers import CONTEXT, freshness, registry, snapshot


def test_knowledge_snapshot_and_evidence_graph_are_content_addressed_replay_artifacts():
    snap=snapshot()
    evidence=evidence_from_knowledge(
        snap,"claim-1",registry(),freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    )
    assert knowledge_snapshot_artifact(snap).digest==snap.digest
    graph_artifact=evidence_graph_artifact(EvidenceGraph((evidence,)))
    assert len(graph_artifact.digest)==64
