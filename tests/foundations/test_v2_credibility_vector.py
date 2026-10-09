"""Roadmap V2 R7: credibility vectors f(C), r(D), g = r - f on the existing evidence graph (incl. checkpoint-5 review)."""

from __future__ import annotations

import hashlib
import itertools

import pytest

from engcore.claims.credibility_vector import (
    ENVELOPE_SURVIVED, RISK_POLICY_V1, RISK_POLICY_V1_ID, UNKNOWN, VALIDATION_LEVEL_PROJECTION, ClaimNode, Combine, CredibilityRefused,
    DecisionRequirement, Defeater, Factor, FactorClaim, RiskClass, assess_credibility, envelope_digest, register_risk_policy,
)
from engcore.claims.gaps import GapClass
from engcore.claims.redteam import AttackDimension, AttackKind, AttackPlan, AttackSpace, ClaimSubject, Route, RouteResult, Sense, run_red_team
from engcore.credibility.evidence_graph import (
    EvidenceAuthority as A, EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceProvenance, EvidenceRelation as R,
)
from engcore.scientific.results.validation import ValidationLevel as VL

CTX = hashlib.sha256(b"decision-context").hexdigest()
OTHER = hashlib.sha256(b"other-context").hexdigest()


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def node(eid, authority, ctx=CTX, *, provenance=True, issuer=None, digest=None, source=None, trusted=True):
    content = digest or _h(eid)
    prov = None
    if provenance:
        doc = _h("doc:" + (issuer or eid))
        prov = EvidenceProvenance(source_id=f"sid:{issuer or eid}", issuer=issuer or f"iss:{eid}", document_digest=doc, version="1",
                                  locator=f"loc:{eid}", published_at="", retrieved_at="", source_class="test",
                                  pin_issuer=(issuer or f"iss:{eid}") if trusted else "someone-else", pin_document_digest=doc,
                                  pin_version="1", freshness_rule_configured=False, freshness_limit_days=None,
                                  freshness_requires_timestamp=False, assessed_at="2026-10-09T00:00:00+00:00", context_digest=ctx,
                                  claim_digest=content)
    return EvidenceNode(eid, authority, content, source or f"src:{eid}", applicability=ctx, provenance=prov)


BASE = {
    "result": node("result", A.SIMULATION), "domain": node("domain", A.ANALYTICAL), "conv": node("conv", A.SIMULATION),
    "mms": node("mms", A.ANALYTICAL), "bench": node("bench", A.REFERENCE_DATA), "exp": node("exp", A.EXPERIMENT),
    "nuq": node("nuq", A.SIMULATION), "puq": node("puq", A.SIMULATION), "muq": node("muq", A.MEASUREMENT),
    "mfuq": node("mfuq", A.EXPERIMENT), "route_a": node("route_a", A.SIMULATION), "route_b": node("route_b", A.ANALYTICAL),
    "foreign": node("foreign", A.EXPERIMENT, OTHER), "rumour": node("rumour", A.UNKNOWN, provenance=False),
    "cross": node("cross", A.SIMULATION), "domain_out": node("domain_out", A.ANALYTICAL),
}
SUPPORTERS = [k for k in BASE if k not in ("result", "rumour")]


def graph(*extra_edges, nodes=None, drop=(), support=True):
    ns = {k: v for k, v in (nodes or BASE).items() if k not in drop}
    edges = [EvidenceEdge(k, "result", R.SUPPORTS) for k in SUPPORTERS if k in ns and support] if "result" in ns else []
    return EvidenceGraph(tuple(ns.values()), tuple(edges) + tuple(extra_edges))


def full_claims():
    return (FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability"),
            FactorClaim(Factor.VERIFICATION, 2, ("conv", "mms"), VL.ANALYTICALLY_VERIFIED.value),
            FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value),
            FactorClaim(Factor.NUMERICAL_UQ, 1, ("nuq",), "numerical"), FactorClaim(Factor.PARAMETER_UQ, 1, ("puq",), "epistemic_parameter"),
            FactorClaim(Factor.MEASUREMENT_UQ, 1, ("muq",), "aleatoric"), FactorClaim(Factor.MODEL_FORM_UQ, 1, ("mfuq",), "model_form"),
            FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b"), VL.CROSS_SOLVER_VALIDATED.value))


def leaf(claims=None, nid="c"):
    return ClaimNode(nid, tuple(full_claims() if claims is None else claims), subject_id="result")


def req(risk=RiskClass.HIGH):
    return DecisionRequirement("decision-1", CTX, risk)


def test_the_projection_is_complete_and_a_fully_evidenced_claim_meets_high():
    assert set(VALIDATION_LEVEL_PROJECTION) == set(VL)
    assert VALIDATION_LEVEL_PROJECTION[VL.CROSS_SOLVER_VALIDATED][0] is Factor.INDEPENDENT_ROUTES      # R-39: not validation
    rep = assess_credibility(leaf(), graph(), req())
    assert rep.requirement_met and rep.dominant_blocking_gap is None, rep.notes
    d = rep.to_dict()
    assert d["policy_digest"] and d["required"] and d["context_digest"] == CTX and d["claim_structure_digest"]
    with pytest.raises(CredibilityRefused, match="never asserted"):
        FactorClaim(Factor.VALIDATION, 2, (), VL.EXPERIMENTALLY_VALIDATED.value)
    with pytest.raises(CredibilityRefused, match="does not project"):
        FactorClaim(Factor.VALIDATION, 2, ("cross",), VL.CROSS_SOLVER_VALIDATED.value)
    with pytest.raises(CredibilityRefused, match="channel"):
        FactorClaim(Factor.MODEL_FORM_UQ, 1, ("x",), "numerical")


def test_r_comes_only_from_a_registered_monotone_policy():
    with pytest.raises(TypeError):                                                      # review B1: no caller override
        DecisionRequirement("d", CTX, RiskClass.CRITICAL, required={})
    with pytest.raises(CredibilityRefused, match="no registered risk policy"):
        DecisionRequirement("d", CTX, RiskClass.LOW, policy_id="my-lenient-policy")
    weak = {r: dict(RISK_POLICY_V1[r]) for r in RiskClass}
    weak[RiskClass.CRITICAL] = {Factor.VALIDATION: 0}
    with pytest.raises(CredibilityRefused, match="monotone"):
        register_risk_policy("weaker", weak)
    with pytest.raises(CredibilityRefused, match="already registered"):
        register_risk_policy(RISK_POLICY_V1_ID, {r: {Factor.APPLICABILITY: 1} for r in RiskClass})
    with pytest.raises(TypeError):
        RISK_POLICY_V1[RiskClass.CRITICAL][Factor.VALIDATION] = 0                        # review L1: immutable
    with pytest.raises(CredibilityRefused, match="exactly one"):
        ClaimNode("empty")                                                              # review M6
    with pytest.raises(CredibilityRefused, match="does not combine"):
        ClaimNode("x", (), Combine.AND, subject_id="result")
    for lo, hi in zip(list(RiskClass), list(RiskClass)[1:]):                            # review L5
        assert all(RISK_POLICY_V1[hi].get(f, -1) >= lv for f, lv in RISK_POLICY_V1[lo].items())


def test_unknown_never_satisfies_and_the_policy_never_becomes_evidence():
    rep = assess_credibility(leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability")]), graph(), req())
    gaps = {g.factor: g for g in rep.gaps}
    assert gaps[Factor.VALIDATION].unknown and gaps[Factor.VALIDATION].gap == 3 and not rep.requirement_met
    low = assess_credibility(leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability")]), graph(), req(RiskClass.LOW))
    assert low.vector.levels == rep.vector.levels


def test_levels_need_support_of_the_subject_admissible_authority_context_and_trusted_provenance():
    claims = [FactorClaim(Factor.VALIDATION, 1, ("foreign",), VL.BENCHMARK_VALIDATED.value),          # other context
              FactorClaim(Factor.MEASUREMENT_UQ, 1, ("rumour",), "aleatoric"),                       # unknown authority
              FactorClaim(Factor.MODEL_FORM_UQ, 1, ("conv",), "model_form"),                         # the model's own run
              FactorClaim(Factor.VERIFICATION, 1, ("bench",), VL.NUMERICALLY_CONVERGED.value)]       # a document can't verify
    rep = assess_credibility(leaf(claims), graph(), req())
    assert all(rep.vector.level(f) == UNKNOWN for f in (Factor.VALIDATION, Factor.MEASUREMENT_UQ, Factor.MODEL_FORM_UQ, Factor.VERIFICATION))
    unlinked = assess_credibility(leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)]),
                                  graph(support=False), req())                                       # review H4: no edge to the subject
    assert unlinked.vector.level(Factor.VALIDATION) == UNKNOWN
    untrusted = dict(BASE, exp=node("exp", A.EXPERIMENT, trusted=False))                             # review H5
    rep = assess_credibility(leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)]),
                             graph(nodes=untrusted), req())
    assert rep.vector.level(Factor.VALIDATION) == UNKNOWN
    one_node_many = [FactorClaim(Factor.NUMERICAL_UQ, 1, ("nuq",), "numerical"),
                     FactorClaim(Factor.PARAMETER_UQ, 1, ("nuq",), "epistemic_parameter")]            # one record, two channels
    rep = assess_credibility(leaf(one_node_many), graph(), req())
    assert (rep.vector.level(Factor.NUMERICAL_UQ), rep.vector.level(Factor.PARAMETER_UQ)) == (1, UNKNOWN)


def test_independence_must_be_shown_positively():
    two = [FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b"), VL.CROSS_SOLVER_VALIDATED.value)]
    assert assess_credibility(leaf(two), graph(), req()).vector.level(Factor.INDEPENDENT_ROUTES) == 2
    shared_issuer = dict(BASE, route_b=node("route_b", A.ANALYTICAL, issuer="iss:route_a"))          # review H2
    assert assess_credibility(leaf(two), graph(nodes=shared_issuer), req()).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    same_record = dict(BASE, route_b=node("route_b", A.SIMULATION, digest=_h("route_a"), source="src:route_a"))
    assert assess_credibility(leaf(two), graph(nodes=same_record), req()).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    no_prov = dict(BASE, route_b=node("route_b", A.ANALYTICAL, provenance=False))
    assert assess_credibility(leaf(two), graph(nodes=no_prov), req()).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    shared_lineage = graph(EvidenceEdge("route_a", "bench", R.VALIDATES), EvidenceEdge("route_b", "bench", R.SUPPORTS))
    assert assess_credibility(leaf(two), shared_lineage, req()).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN


def test_defeaters_block_and_cannot_be_silenced_by_supersession_or_hidden_in_lineage():
    contradicted = assess_credibility(leaf(), graph(EvidenceEdge("bench", "exp", R.CONTRADICTS)), req())
    assert not contradicted.requirement_met and contradicted.dominant_blocking_gap["kind"] == "defeater"
    # review H1: the challenged evidence (or an UNKNOWN node) cannot supersede its contradictor
    for sup in ("exp", "rumour"):
        g = graph(EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge(sup, "bench", R.SUPERSEDES))
        assert not assess_credibility(leaf(), g, req()).requirement_met, sup
    # review M3: a contradiction of evidence the support DERIVES from still counts
    with_raw = dict(BASE, raw=node("raw", A.MEASUREMENT))
    g = graph(EvidenceEdge("exp", "raw", R.DERIVED_FROM), EvidenceEdge("bench", "raw", R.CONTRADICTS), nodes=with_raw)
    assert not assess_credibility(leaf(), g, req()).requirement_met
    # a sub-bar contradiction is a note, not silence
    rumour = assess_credibility(leaf(), graph(EvidenceEdge("rumour", "exp", R.CONTRADICTS)), req())
    assert rumour.requirement_met and any("sub-bar contradiction" in n for n in rumour.notes)
    refuted = assess_credibility(leaf(), graph(), req(),
                                 defeaters=(Defeater("f1@v1", "falsifier_refuted", ("exp",), "sealed falsifier refuted the claim"),))
    assert not refuted.requirement_met
    with pytest.raises(CredibilityRefused, match="kind"):
        Defeater("d", "vibes", (), "x")


def test_an_outside_domain_finding_is_a_defeater_and_dominates():
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    rep = assess_credibility(leaf(claims), graph(), req())                                # review H3: not overridden by 'inside'
    assert not rep.requirement_met and rep.dominant_blocking_gap["defeater"]["kind"] == "outside_domain"
    assert rep.vector.level(Factor.APPLICABILITY) == 0
    gap = next(g for g in rep.gaps if g.factor is Factor.APPLICABILITY)
    assert gap.gap_class is GapClass.MODEL_OUTSIDE_DOMAIN
    empty = assess_credibility(leaf([FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value)]), graph(), req())
    assert empty.dominant_blocking_gap["factor"] == "applicability"                       # review M1: applicability first


def test_and_takes_the_weakest_and_or_takes_one_whole_independent_branch():
    weak = leaf([FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value)], "weak")
    strong = leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)], "strong")
    g = graph()
    assert assess_credibility(ClaimNode("and", combine=Combine.AND, children=(weak, strong)), g, req()).vector.level(Factor.VALIDATION) == 1
    assert assess_credibility(ClaimNode("or", combine=Combine.OR, children=(weak, strong)), g, req()).vector.level(Factor.VALIDATION) == 2
    # review H3: OR never mixes factors across branches
    a = leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)], "a")
    b = leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability")], "b")
    mixed = assess_credibility(ClaimNode("or", combine=Combine.OR, children=(a, b)), g, req()).vector
    assert not (mixed.level(Factor.VALIDATION) == 2 and mixed.level(Factor.APPLICABILITY) == 1)
    dependent = graph(EvidenceEdge("exp", "bench", R.DERIVED_FROM))
    rep = assess_credibility(ClaimNode("or", combine=Combine.OR, children=(weak, strong)), dependent, req())
    assert rep.vector.level(Factor.VALIDATION) == 1 and any("not shown independent" in n for n in rep.notes)
    # review M2: dropping a conjunct changes the claim identity
    one = assess_credibility(ClaimNode("x", combine=Combine.AND, children=(weak,)), g, req())
    both = assess_credibility(ClaimNode("x", combine=Combine.AND, children=(weak, strong)), g, req())
    assert one.claim_structure_digest != both.claim_structure_digest


def test_adversarial_standing_comes_from_the_envelope_itself():
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("beam", (x,))
    routes = (Route("a", "f", 1, lambda p: RouteResult(0.1)), Route("b", "g", 2, lambda p: RouteResult(0.1)))
    survived = run_red_team(ClaimSubject("beam", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    nodes = dict(BASE, rt=node("rt", A.SIMULATION, digest=envelope_digest(survived)))
    claim = leaf(list(full_claims()) + [FactorClaim(Factor.ADVERSARIAL, 1, ("rt",), ENVELOPE_SURVIVED)])
    SUPPORTERS.append("rt")
    try:
        g = graph(nodes=nodes)
        assert assess_credibility(claim, g, req(RiskClass.CRITICAL), red_team=(survived,)).vector.level(Factor.ADVERSARIAL) == 1
        assert assess_credibility(claim, g, req(RiskClass.CRITICAL)).vector.level(Factor.ADVERSARIAL) == UNKNOWN  # review M4
        broken = (Route("a", "f", 1, lambda p: RouteResult(5.0)), Route("b", "g", 2, lambda p: RouteResult(5.0)))
        falsified = run_red_team(ClaimSubject("beam", "y", "1", Sense.AT_MOST, 1.0, broken, "a"), space, AttackPlan(space.digest, 200, "s"))
        rep = assess_credibility(claim, g, req(RiskClass.CRITICAL), red_team=(survived, falsified))
        assert not rep.requirement_met and any(d.kind == "red_team_falsified" for d in rep.open_defeaters)
    finally:
        SUPPORTERS.remove("rt")


def test_removing_evidence_never_raises_any_factor_or_meets_a_requirement():
    claims = full_claims()
    base = assess_credibility(leaf(claims), graph(), req())
    ids = sorted({e for c in claims for e in c.evidence_ids})
    for k in (1, 2):
        for removed in itertools.combinations(ids, k):
            vec = assess_credibility(leaf(claims), graph(drop=removed), req()).vector
            assert all(vec.level(f) <= base.vector.level(f) for f in Factor), removed
    # removing a CONTRADICTION is the one removal that can raise the outcome: it is a different graph (bound fingerprint)
    contradicted = assess_credibility(leaf(claims), graph(EvidenceEdge("bench", "exp", R.CONTRADICTS)), req())
    assert contradicted.graph_digest != base.graph_digest and not contradicted.requirement_met
