"""Roadmap V2 R7: credibility vectors f(C), r(D), g = r - f on the existing evidence graph."""

from __future__ import annotations

import hashlib
import itertools

import pytest

from engcore.claims.credibility_vector import (
    UNKNOWN, ClaimNode, Combine, CredibilityRefused, DecisionRequirement, Defeater, Factor, FactorClaim, RiskClass,
    assess_credibility,
)
from engcore.claims.gaps import GapClass
from engcore.credibility.evidence_graph import EvidenceAuthority as A, EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceRelation as R

CTX = hashlib.sha256(b"decision-context").hexdigest()
OTHER = hashlib.sha256(b"other-context").hexdigest()


def node(eid, authority, ctx=CTX):
    return EvidenceNode(eid, authority, hashlib.sha256(eid.encode()).hexdigest(), f"src:{eid}", applicability=ctx)


NODES = {
    "domain": node("domain", A.ANALYTICAL), "conv": node("conv", A.SIMULATION), "mms": node("mms", A.ANALYTICAL),
    "bench": node("bench", A.REFERENCE_DATA), "exp": node("exp", A.EXPERIMENT), "cross": node("cross", A.SIMULATION),
    "nuq": node("nuq", A.SIMULATION), "puq": node("puq", A.SIMULATION), "muq": node("muq", A.MEASUREMENT),
    "mfuq": node("mfuq", A.SIMULATION), "route_a": node("route_a", A.SIMULATION), "route_b": node("route_b", A.ANALYTICAL),
    "redteam": node("redteam", A.SIMULATION), "foreign": node("foreign", A.EXPERIMENT, OTHER), "rumour": node("rumour", A.UNKNOWN),
}


def graph(*extra_edges, drop=()):
    return EvidenceGraph(tuple(n for k, n in NODES.items() if k not in drop), tuple(extra_edges))


def full_claims():
    return (FactorClaim(Factor.APPLICABILITY, 1, ("domain",)), FactorClaim(Factor.VERIFICATION, 2, ("conv", "mms")),
            FactorClaim(Factor.VALIDATION, 2, ("exp",)), FactorClaim(Factor.NUMERICAL_UQ, 1, ("nuq",)),
            FactorClaim(Factor.PARAMETER_UQ, 1, ("puq",)), FactorClaim(Factor.MEASUREMENT_UQ, 1, ("muq",)),
            FactorClaim(Factor.MODEL_FORM_UQ, 1, ("mfuq",)), FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b")),
            FactorClaim(Factor.ADVERSARIAL, 1, ("redteam",)))


def req(risk=RiskClass.HIGH):
    return DecisionRequirement("decision-1", CTX, risk)


def test_a_fully_evidenced_claim_meets_a_critical_requirement_and_every_level_is_earned():
    rep = assess_credibility(ClaimNode("c", full_claims()), graph(), req(RiskClass.CRITICAL))
    assert rep.requirement_met and rep.dominant_blocking_gap is None and rep.to_dict()["schema"]
    with pytest.raises(CredibilityRefused, match="never asserted"):
        FactorClaim(Factor.VALIDATION, 2, ())


def test_unknown_never_satisfies_and_the_policy_never_becomes_evidence():
    rep = assess_credibility(ClaimNode("c", (FactorClaim(Factor.APPLICABILITY, 1, ("domain",)),)), graph(), req())
    gaps = {g.factor: g for g in rep.gaps}
    assert gaps[Factor.VALIDATION].unknown and gaps[Factor.VALIDATION].attained == UNKNOWN and gaps[Factor.VALIDATION].gap == 3
    assert not rep.requirement_met and rep.vector.level(Factor.VALIDATION) == UNKNOWN
    low = assess_credibility(ClaimNode("c", (FactorClaim(Factor.APPLICABILITY, 1, ("domain",)),)), graph(), req(RiskClass.LOW))
    assert low.vector.levels == rep.vector.levels                                           # the bar moved; the evidence did not


def test_levels_need_admissible_context_bound_unsuperseded_evidence():
    claims = (FactorClaim(Factor.VALIDATION, 2, ("cross",)),        # cross-solver agreement is not experimental validation
              FactorClaim(Factor.VALIDATION, 1, ("foreign",)),      # another context's experiment
              FactorClaim(Factor.MEASUREMENT_UQ, 1, ("rumour",)))   # unknown authority
    rep = assess_credibility(ClaimNode("c", claims), graph(), req())
    assert rep.vector.level(Factor.VALIDATION) == UNKNOWN and rep.vector.level(Factor.MEASUREMENT_UQ) == UNKNOWN
    assert len(rep.vector.rejected) == 3
    stale = assess_credibility(ClaimNode("c", (FactorClaim(Factor.VALIDATION, 2, ("exp",)),)),
                               graph(EvidenceEdge("bench", "exp", R.SUPERSEDES)), req())
    assert stale.vector.level(Factor.VALIDATION) == UNKNOWN
    # two "independent" routes that derive from one source are one route
    shared = assess_credibility(ClaimNode("c", (FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b")),)),
                                graph(EvidenceEdge("route_b", "route_a", R.DERIVED_FROM)), req())
    assert shared.vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN


def test_defeaters_block_and_dominate():
    contradicted = assess_credibility(ClaimNode("c", full_claims()), graph(EvidenceEdge("bench", "exp", R.CONTRADICTS)),
                                      req(RiskClass.CRITICAL))
    assert not contradicted.requirement_met and contradicted.dominant_blocking_gap["kind"] == "defeater"
    refuted = assess_credibility(ClaimNode("c", full_claims()), graph(), req(RiskClass.CRITICAL),
                                 defeaters=(Defeater("f1@v1", "falsifier_refuted", ("exp",), "sealed falsifier refuted the claim"),))
    assert not refuted.requirement_met and refuted.open_defeaters
    rumour = assess_credibility(ClaimNode("c", full_claims()), graph(EvidenceEdge("rumour", "exp", R.CONTRADICTS)), req(RiskClass.CRITICAL))
    assert rumour.requirement_met                                       # a contradiction needs admissible evidence
    with pytest.raises(CredibilityRefused, match="not in the graph"):
        assess_credibility(ClaimNode("c", full_claims()), graph(), req(), defeaters=(Defeater("d", "x", ("ghost",), "?"),))


def test_the_dominant_gap_is_the_largest_and_maps_onto_the_gap_vocabulary():
    claims = tuple(c for c in full_claims() if c.factor not in (Factor.VALIDATION, Factor.NUMERICAL_UQ))
    rep = assess_credibility(ClaimNode("c", claims), graph(), req())
    dom = rep.dominant_blocking_gap
    assert dom["factor"] == "validation" and dom["gap_class"] == GapClass.VALIDATION_LEVEL_MISSING.value


def test_and_takes_the_weakest_or_the_stronger_only_with_graph_independence():
    weak = ClaimNode("weak", (FactorClaim(Factor.VALIDATION, 1, ("bench",)),))
    strong = ClaimNode("strong", (FactorClaim(Factor.VALIDATION, 2, ("exp",)),))
    g = graph()
    assert assess_credibility(ClaimNode("and", combine=Combine.AND, children=(weak, strong)), g, req()).vector.level(Factor.VALIDATION) == 1
    assert assess_credibility(ClaimNode("or", combine=Combine.OR, children=(weak, strong)), g, req()).vector.level(Factor.VALIDATION) == 2
    dependent = graph(EvidenceEdge("exp", "bench", R.DERIVED_FROM))
    rep = assess_credibility(ClaimNode("or", combine=Combine.OR, children=(weak, strong)), dependent, req())
    assert rep.vector.level(Factor.VALIDATION) == 1 and any("independence not supported" in n for n in rep.notes)


def test_removing_evidence_never_raises_any_factor():
    claims = full_claims()
    base = assess_credibility(ClaimNode("c", claims), graph(), req(RiskClass.CRITICAL)).vector
    ids = sorted({e for c in claims for e in c.evidence_ids})
    for k in (1, 2):
        for removed in itertools.combinations(ids, k):
            kept = tuple(c for c in claims if not set(c.evidence_ids) & set(removed))
            if not kept:
                continue
            vec = assess_credibility(ClaimNode("c", kept), graph(drop=removed), req(RiskClass.CRITICAL)).vector
            assert all(vec.level(f) <= base.level(f) for f in Factor), removed
    # and a claim whose node vanished from the graph earns nothing for it
    gone = assess_credibility(ClaimNode("c", claims), graph(drop=("exp",)), req(RiskClass.CRITICAL))
    assert gone.vector.level(Factor.VALIDATION) == UNKNOWN and not gone.requirement_met
