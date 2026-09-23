from engcore.scientific.knowledge import (
    KnowledgeConflictStatus, compare_claims,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from tests.scientific.knowledge.helpers import claim


def interval(lo,hi):
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(lo,"watt / meter / kelvin"),
        upper=Quantity(hi,"watt / meter / kelvin"),
        method="published interval",
    )


def test_explicit_overlapping_intervals_are_not_called_agreement_or_conflict():
    left=claim(value=0.60)
    payload=claim(value=0.62).to_dict()
    payload["claim_id"]="claim-2"
    payload["uncertainty"]=interval(0.58,0.66).to_dict()
    right=type(left).from_dict(payload)
    assert compare_claims(left,right).status is KnowledgeConflictStatus.OVERLAPPING_INTERVALS


def test_nonoverlapping_explicit_intervals_are_recorded_as_disagreement():
    left=claim(value=0.60)
    # Build the changed value and its interval atomically in the wire payload.
    # Constructing claim(value=0.80) first is now correctly refused because the
    # helper's default [0.55, 0.65] interval does not contain 0.80.
    payload=claim(value=0.60).to_dict()
    payload["claim_id"]="claim-2"
    payload["numeric_value"]["magnitude"]=0.80
    payload["uncertainty"]=interval(0.75,0.85).to_dict()
    right=type(left).from_dict(payload)
    assert compare_claims(left,right).status is KnowledgeConflictStatus.DISAGREEMENT


def test_different_values_without_comparable_uncertainty_are_incomparable_not_auto_conflict():
    left=claim(value=0.60)
    payload=claim(value=0.70).to_dict()
    payload["claim_id"]="claim-2"
    payload["uncertainty"]=None
    right=type(left).from_dict(payload)
    assert compare_claims(left,right).status is KnowledgeConflictStatus.INCOMPARABLE
