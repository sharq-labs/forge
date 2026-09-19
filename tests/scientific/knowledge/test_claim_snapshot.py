import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.knowledge import KnowledgeClaim, KnowledgeSnapshot
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from tests.scientific.knowledge.helpers import claim, snapshot, source


def test_snapshot_round_trip_and_digest_bind_exact_source_and_claim_bytes():
    snap=snapshot()
    restored=KnowledgeSnapshot.from_dict(snap.to_dict())
    assert restored.to_dict()==snap.to_dict()
    assert restored.digest==snap.digest


def test_snapshot_refuses_claim_whose_source_digest_differs():
    src=source()
    with pytest.raises(InvalidScientificProblem,match="source digest"):
        KnowledgeSnapshot("s",(src,),(claim(source_digest="b"*64),))


def test_numeric_claim_interval_must_contain_claimed_value():
    payload=claim().to_dict()
    payload["numeric_value"]=Quantity(0.80,"watt / meter / kelvin").to_dict()
    with pytest.raises(InvalidScientificProblem,match="must contain"):
        KnowledgeClaim.from_dict(payload)
