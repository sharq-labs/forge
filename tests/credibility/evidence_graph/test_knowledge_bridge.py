from datetime import datetime, timezone
import pytest

from engcore.credibility.evidence_graph import (
    EvidenceGraph, EvidenceGraphPolicy, EvidenceNode, assess_graph,
)
from engcore.credibility.knowledge_evidence import evidence_from_knowledge
from engcore.scientific.errors import InvalidScientificProblem
from tests.scientific.knowledge.helpers import CONTEXT, freshness, registry, snapshot


def node():
    return evidence_from_knowledge(
        snapshot(),"claim-1",registry(),freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    )


def test_admitted_knowledge_becomes_typed_provenance_and_strict_graph_evidence():
    evidence=node()
    assert evidence.provenance is not None
    assert evidence.provenance.trusted
    assert evidence.provenance.fresh_enough
    graph=EvidenceGraph((evidence,))
    result=assess_graph(
        graph,
        EvidenceGraphPolicy(
            require_provenance=True,
            require_trusted_provenance=True,
            require_fresh_provenance=True,
        ),
    )
    assert result.admissible


def test_evidence_wire_trust_status_is_rederived_not_trusted():
    payload=node().to_dict()
    payload["provenance"]["trust_status"]="untrusted"
    with pytest.raises(InvalidScientificProblem,match="forged"):
        EvidenceNode.from_dict(payload)


def test_tampered_pin_identity_rederives_untrusted_and_strict_policy_refuses():
    payload=node().to_dict()
    payload["provenance"].pop("trust_status")
    payload["provenance"]["pin_document_digest"]="f"*64
    restored=EvidenceNode.from_dict(payload)
    result=assess_graph(
        EvidenceGraph((restored,)),
        EvidenceGraphPolicy(
            require_provenance=True,
            require_trusted_provenance=True,
        ),
    )
    assert not result.admissible


def test_unadmitted_context_never_crosses_knowledge_to_evidence_bridge():
    with pytest.raises(InvalidScientificProblem,match="not admissible"):
        evidence_from_knowledge(
            snapshot(),"claim-1",registry(),freshness(),
            now=datetime(2026,9,19,tzinfo=timezone.utc),
            target_context_digest="d"*64,
        )
