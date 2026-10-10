"""Roadmap V2 R7: credibility vectors f(C), r(D), g = r - f on the existing evidence graph (incl. the checkpoint-5 review
and its two confirmation reviews).  Strong levels are backed by genuinely ISSUED ValidationChecks (pinned oracles, an earned
consensus), applicability and UQ by existing ApplicabilityReport / ChannelEntry records, and provenance is pinned by a
TrustedSourceRegistry -- never by a record's own fields."""

from __future__ import annotations

import hashlib
import itertools

import pytest

import engcore.scientific.oracles as oracle_module
from engcore.claims.credibility_vector import (
    ENVELOPE_SURVIVED, RISK_POLICY_V1, RISK_POLICY_V1_ID, UNKNOWN, VALIDATION_LEVEL_PROJECTION, ClaimNode, Combine, CredibilityRefused,
    DecisionRequirement, Defeater, Factor, FactorClaim, RiskClass, assess_credibility, check_digest, envelope_digest, record_digest,
    register_risk_policy,
)
from engcore.claims.gaps import GapClass
from engcore.claims.redteam import (
    AttackDimension, AttackKind, AttackPlan, AttackSpace, ClaimSubject, EnvelopeOutcome, Route, RouteResult, Sense, TrustEnvelope,
    run_red_team,
)
from engcore.credibility.evidence_graph import (
    EvidenceAuthority as A, EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceProvenance, EvidenceRelation as R,
)
from engcore.scientific.knowledge.trust import SourcePin, TrustedSourceRegistry
from engcore.scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource as US
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel as VL, ValidationOutcome
from engcore.sria.assurance.uncertainty_budget import ChannelEntry, ChannelState
from engcore.sria.uncertainty import UncertaintyChannel as UC
from engcore.system_runtime.records import ApplicabilityReport
from tests.route_declarations_for_tests import earned_consensus, route, route_declarations_for_tests  # noqa: F401 - autouse
from engcore.scientific.units.quantity import Quantity
from tests.authority_helpers import World as AuthorityWorld
from tests.test_audit_consensus_level_issuers import AT, _oracle_check

CTX = hashlib.sha256(b"decision-context").hexdigest()
OTHER = hashlib.sha256(b"other-context").hexdigest()


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _prov(eid, ctx, digest, *, issuer=None, version="1", source_id=None):
    doc = _h("doc:" + (source_id or issuer or eid) + version)
    return EvidenceProvenance(source_id=source_id or f"sid:{issuer or eid}", issuer=issuer or f"iss:{eid}", document_digest=doc,
                              version=version, locator=f"loc:{eid}", published_at="", retrieved_at="", source_class="test",
                              pin_issuer=issuer or f"iss:{eid}", pin_document_digest=doc, pin_version=version,
                              freshness_rule_configured=False, freshness_limit_days=None, freshness_requires_timestamp=False,
                              assessed_at="2026-10-09T00:00:00+00:00", context_digest=ctx, claim_digest=digest)


def quantified(channel, source, state=ChannelState.KNOWN):
    return ChannelEntry(channel, state, Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "volt"),
                                                    method="m", source_kind=source), source="test")


RESULT_DIGEST = _h("result")


def node(eid, authority, ctx=CTX, *, provenance=True, digest=None, source=None, **prov_kw):
    content = digest or _h(eid)
    return EvidenceNode(eid, authority, content, source or f"src:{eid}", applicability=ctx,
                        provenance=_prov(eid, ctx, content, **prov_kw) if provenance else None)


@pytest.fixture()
def world(monkeypatch):
    """Issued checks, the graph nodes that carry them, and the trusted-source registry that pins the provenance."""
    def _oracle(kind):                       # one oracle identity per kind (the trust registry is keyed by id + version)
        return OracleEvidenceSet.create(
            oracle_id=f"lab.{kind.value}.001", version="1", kind=kind, reference=f"doi:10.example/{kind.value}",
            observations=(OracleObservation("voltage", Quantity(3.70, "volt"), Quantity(0.05, "volt"), conditions=AT),))
    oracles = {k: _oracle(k) for k in (OracleKind.EXPERIMENTAL_DATASET, OracleKind.BENCHMARK_DATASET, OracleKind.ANALYTIC_REFERENCE)}
    monkeypatch.setattr(oracle_module, "_TRUSTED_ORACLE_DECLARATIONS", {
        o.identity.key: {"kind": o.identity.kind.value, "evidence_digest": o.identity.evidence_digest,
                         "reference": o.identity.reference} for o in oracles.values()})
    checks = {
        "exp": _oracle_check(oracles[OracleKind.EXPERIMENTAL_DATASET]),
        "bench": _oracle_check(oracles[OracleKind.BENCHMARK_DATASET]),
        "mms": _oracle_check(oracles[OracleKind.ANALYTIC_REFERENCE]),
        "conv": ValidationCheck("conv", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.001, tolerance=0.01,
                                evidence=("richardson:3-level",)),
    }
    from engcore.domains.electrical import dc_consensus as dcc
    for name, val in (("route_a", 1.0), ("route_b", 2.0)):
        checks[name] = earned_consensus((route("a"), route("b")), {"a": {"v": val}, "b": {"v": val}}, thresholds=dcc.DC_CONSENSUS_THRESHOLDS,
                                        tolerance_key="agreement_rel_tol", required=("v",)).to_check()
    authority = {"exp": A.EXPERIMENT, "bench": A.REFERENCE_DATA, "mms": A.ANALYTICAL, "conv": A.SIMULATION, "route_a": A.SIMULATION,
                 "route_b": A.ANALYTICAL}
    nodes = {k: node(k, authority[k], digest=check_digest(c)) for k, c in checks.items()}
    within = ApplicabilityReport("domain.check", "within", RESULT_DIGEST, "inside the declared envelope")
    entries = {"nuq": quantified(UC.NUMERICAL, US.NUMERICAL), "puq": quantified(UC.EPISTEMIC_PARAMETER, US.PARAMETER),
               "muq": quantified(UC.ALEATORIC, US.MEASUREMENT), "mfuq": quantified(UC.MODEL_FORM, US.MODEL_FORM)}
    nodes.update({"result": node("result", A.SIMULATION), "domain": node("domain", A.ANALYTICAL, digest=record_digest(within)),
                  "nuq": node("nuq", A.SIMULATION, digest=record_digest(entries["nuq"])),
                  "puq": node("puq", A.SIMULATION, digest=record_digest(entries["puq"])),
                  "muq": node("muq", A.MEASUREMENT, digest=record_digest(entries["muq"])),
                  "mfuq": node("mfuq", A.EXPERIMENT, digest=record_digest(entries["mfuq"])), "domain_out": node("domain_out", A.ANALYTICAL),
                  "foreign": node("foreign", A.EXPERIMENT, OTHER), "rumour": node("rumour", A.UNKNOWN, provenance=False)})
    pins = TrustedSourceRegistry(tuple(SourcePin(n.provenance.source_id, n.provenance.issuer, n.provenance.document_digest,
                                                 n.provenance.version) for n in nodes.values() if n.provenance is not None))
    return {"checks": tuple(checks.values()), "nodes": nodes, "pins": pins, "reports": (within,), "entries": tuple(entries.values())}


def graph(w, *extra_edges, nodes=None, drop=(), support=True):
    ns = {k: v for k, v in (nodes or w["nodes"]).items() if k not in drop}
    edges = [EvidenceEdge(k, "result", R.SUPPORTS) for k in ns if k not in ("result", "rumour") and support] if "result" in ns else []
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


def _leaf_subjects(claim):
    return [claim.subject_id] if not claim.children else [s for ch in claim.children for s in _leaf_subjects(ch)]


def attested(claim, g, ctx=CTX, **records):
    """A TEST authority ledger in which an issuer of the matching role attested every supplied record about every
    subject's result (the issuer-bound path ``assess_credibility(authority=...)`` admits records through)."""
    world = AuthorityWorld()
    digests = {n.evidence_id: n.content_digest for n in g.nodes}
    for sid in sorted(set(_leaf_subjects(claim))):
        for group in ("validation_checks", "applicability_reports", "uncertainty_entries", "red_team"):
            for rec in records.get(group, ()):
                try:
                    world.attest(rec, digests[sid], ctx)
                except Exception:           # noqa: BLE001 - a record that cannot be attested (tampered, non-finite) stays unattested
                    pass
    return world.ledger


def assess(w, claim, g, risk=RiskClass.HIGH, **kw):
    kw.setdefault("trusted_sources", w["pins"])
    kw.setdefault("validation_checks", w["checks"])
    kw.setdefault("applicability_reports", w["reports"])
    kw.setdefault("uncertainty_entries", w["entries"])
    if "authority" not in kw:
        kw["authority"] = attested(claim, g, **{k: kw[k] for k in ("validation_checks", "applicability_reports",
                                                                    "uncertainty_entries", "red_team") if k in kw})
    return assess_credibility(claim, g, req(risk), **kw)


def test_the_projection_is_complete_and_a_fully_evidenced_claim_meets_high(world):
    assert set(VALIDATION_LEVEL_PROJECTION) == set(VL)
    assert VALIDATION_LEVEL_PROJECTION[VL.CROSS_SOLVER_VALIDATED][0] is Factor.INDEPENDENT_ROUTES      # R-39: not validation
    rep = assess(world, leaf(), graph(world))
    assert rep.requirement_met and rep.dominant_blocking_gap is None, rep.notes
    d = rep.to_dict()
    assert d["policy_digest"] and d["required"] and d["context_digest"] == CTX and d["claim_structure_digest"]
    with pytest.raises(CredibilityRefused, match="never asserted"):
        FactorClaim(Factor.VALIDATION, 2, (), VL.EXPERIMENTALLY_VALIDATED.value)
    with pytest.raises(CredibilityRefused, match="does not project"):
        FactorClaim(Factor.VALIDATION, 2, ("route_a",), VL.CROSS_SOLVER_VALIDATED.value)


def test_levels_rest_on_issued_checks_and_registry_pinned_provenance(world):            # confirmation review H-C3
    no_checks = assess(world, leaf(), graph(world), validation_checks=())
    assert no_checks.vector.level(Factor.VALIDATION) == UNKNOWN and no_checks.vector.level(Factor.VERIFICATION) == UNKNOWN
    no_pins = assess(world, leaf(), graph(world), trusted_sources=None)                   # self-signed pins are not trust
    assert no_pins.vector.level(Factor.VALIDATION) == UNKNOWN and no_pins.vector.level(Factor.APPLICABILITY) == UNKNOWN
    with pytest.raises(Exception, match="issuer"):                                        # a hand-built strong check is refused
        ValidationCheck("x", ValidationOutcome.PASS, establishes=VL.EXPERIMENTALLY_VALIDATED, residual=0.0, tolerance=0.1,
                        evidence=("trust me",))
    fake_node = dict(world["nodes"], exp=node("exp", A.EXPERIMENT))                       # experiment node, but no check behind it
    assert assess(world, leaf(), graph(world, nodes=fake_node)).vector.level(Factor.VALIDATION) == UNKNOWN


def test_r_comes_only_from_a_registered_policy_that_is_never_weaker_than_the_baseline(world):   # B1, H-C1
    with pytest.raises(TypeError):
        DecisionRequirement("d", CTX, RiskClass.CRITICAL, required={})
    with pytest.raises(CredibilityRefused, match="no registered risk policy"):
        DecisionRequirement("d", CTX, RiskClass.LOW, policy_id="my-lenient-policy")
    with pytest.raises(CredibilityRefused, match="STRICTER"):
        register_risk_policy("lenient", {r: {Factor.NUMERICAL_UQ: 0, Factor.APPLICABILITY: 1, Factor.VERIFICATION: 1}
                                         if r is RiskClass.LOW else dict(RISK_POLICY_V1[RiskClass.LOW]) for r in RiskClass})
    with pytest.raises(CredibilityRefused, match="normalized id"):
        register_risk_policy(RISK_POLICY_V1_ID + " ", {r: dict(RISK_POLICY_V1[r]) for r in RiskClass})
    stricter = {r: {**RISK_POLICY_V1[r], Factor.ADVERSARIAL: 1} for r in RiskClass}
    register_risk_policy("forge.test.stricter/1", stricter)
    with pytest.raises(TypeError):
        RISK_POLICY_V1[RiskClass.CRITICAL][Factor.VALIDATION] = 0
    with pytest.raises(CredibilityRefused, match="exactly one"):
        ClaimNode("empty")
    for lo, hi in zip(list(RiskClass), list(RiskClass)[1:]):
        assert all(RISK_POLICY_V1[hi].get(f, -1) >= lv for f, lv in RISK_POLICY_V1[lo].items())


def test_the_subject_is_bound_to_the_decision_context(world):                            # H-C5
    moved = dict(world["nodes"], result=node("result", A.SIMULATION, OTHER))
    with pytest.raises(CredibilityRefused, match="decision's context"):
        assess(world, leaf(), graph(world, nodes=moved))


def test_levels_need_support_of_the_subject_admissible_authority_and_context(world):
    claims = [FactorClaim(Factor.VALIDATION, 1, ("foreign",), VL.BENCHMARK_VALIDATED.value),
              FactorClaim(Factor.MEASUREMENT_UQ, 1, ("rumour",), "aleatoric"),
              FactorClaim(Factor.MODEL_FORM_UQ, 1, ("conv",), "model_form")]
    rep = assess(world, leaf(claims), graph(world))
    assert all(rep.vector.level(f) == UNKNOWN for f in (Factor.VALIDATION, Factor.MEASUREMENT_UQ, Factor.MODEL_FORM_UQ))
    unlinked = assess(world, leaf(), graph(world, support=False))
    assert unlinked.vector.level(Factor.VALIDATION) == UNKNOWN
    # M-C1: data that calibrated the model does not validate it
    calibrated = assess(world, leaf(), graph(world, EvidenceEdge("exp", "result", R.CALIBRATES)))
    assert calibrated.vector.level(Factor.VALIDATION) == UNKNOWN


def test_one_record_one_factor_is_decided_over_all_citations_and_removal_never_helps(world):   # H-C4
    claims = [FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability"),
              FactorClaim(Factor.VERIFICATION, 2, ("conv", "mms"), VL.ANALYTICALLY_VERIFIED.value),
              FactorClaim(Factor.NUMERICAL_UQ, 0, ("conv",), "numerical")]
    with_mms = assess(world, leaf(claims), graph(world), RiskClass.LOW)
    without = assess(world, leaf(claims), graph(world, drop=("mms",)), RiskClass.LOW)
    assert with_mms.vector.level(Factor.NUMERICAL_UQ) == without.vector.level(Factor.NUMERICAL_UQ) == UNKNOWN
    assert not with_mms.requirement_met and not without.requirement_met


def test_independence_must_be_shown_positively(world):
    two = [FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b"), VL.CROSS_SOLVER_VALIDATED.value)]
    assert assess(world, leaf(two), graph(world)).vector.level(Factor.INDEPENDENT_ROUTES) == 2
    n = world["nodes"]
    shared_issuer = dict(n, route_b=node("route_b", A.ANALYTICAL, digest=n["route_b"].content_digest, issuer="iss:route_a"))
    w2 = dict(world, pins=TrustedSourceRegistry(tuple(SourcePin(x.provenance.source_id, x.provenance.issuer, x.provenance.document_digest,
                                                                x.provenance.version) for x in shared_issuer.values() if x.provenance)))
    assert assess(w2, leaf(two), graph(w2, nodes=shared_issuer)).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    shared_lineage = graph(world, EvidenceEdge("route_a", "bench", R.DERIVED_FROM), EvidenceEdge("route_b", "bench", R.DERIVED_FROM))
    assert assess(world, leaf(two), shared_lineage).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    # M-C2: recording the SUBJECT's own lineage does not make the routes dependent
    with_model = dict(n, model=node("model", A.ANALYTICAL))
    subject_lineage = graph(world, EvidenceEdge("result", "model", R.DERIVED_FROM), nodes=with_model)
    assert assess(world, leaf(two), subject_lineage).vector.level(Factor.INDEPENDENT_ROUTES) == 2


def test_defeaters_block_and_only_a_newer_version_of_the_same_source_closes_one(world):    # H-C2
    contradicted = assess(world, leaf(), graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS)))
    assert not contradicted.requirement_met and contradicted.dominant_blocking_gap["kind"] == "defeater"
    patch = dict(world["nodes"], patch=node("patch", A.SIMULATION, provenance=False))
    g = graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("patch", "bench", R.SUPERSEDES), nodes=patch)
    assert not assess(world, leaf(), g).requirement_met                                 # a caller-made node cannot close it
    b = world["nodes"]["bench"]
    newer = node("bench_v2", A.REFERENCE_DATA, issuer=b.provenance.issuer, source_id=b.provenance.source_id, version="2")
    pins = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != b.provenance.source_id)
                                 + (SourcePin(b.provenance.source_id, b.provenance.issuer, newer.provenance.document_digest, "2"),))
    g2 = graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("bench_v2", "bench", R.SUPERSEDES),
               nodes=dict(world["nodes"], bench_v2=newer))
    closed = assess(world, leaf(), g2, trusted_sources=pins)
    assert not any(d.kind == "contradiction" for d in closed.open_defeaters) and any("closed by" in x for x in closed.notes)
    rumour = assess(world, leaf(), graph(world, EvidenceEdge("rumour", "exp", R.CONTRADICTS)))
    assert rumour.requirement_met and any("sub-bar contradiction" in x for x in rumour.notes)
    with pytest.raises(CredibilityRefused, match="kind"):
        Defeater("d", "vibes", (), "x")


def test_an_outside_domain_finding_is_a_defeater_and_dominates(world):
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    rep = assess(world, leaf(claims), graph(world))
    assert not rep.requirement_met and rep.dominant_blocking_gap["defeater"]["kind"] == "outside_domain"
    gap = next(g for g in rep.gaps if g.factor is Factor.APPLICABILITY)
    assert gap.gap_class is GapClass.MODEL_OUTSIDE_DOMAIN
    empty = assess(world, leaf([FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value)]), graph(world))
    assert empty.dominant_blocking_gap["factor"] == "applicability"


def test_and_takes_the_weakest_and_or_takes_one_whole_independent_branch(world):
    weak = leaf([FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value)], "weak")
    strong = leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)], "strong")
    g = graph(world)
    assert assess(world, ClaimNode("and", combine=Combine.AND, children=(weak, strong)), g).vector.level(Factor.VALIDATION) == 1
    assert assess(world, ClaimNode("or", combine=Combine.OR, children=(weak, strong)), g).vector.level(Factor.VALIDATION) == 2
    a = leaf([FactorClaim(Factor.VALIDATION, 2, ("exp",), VL.EXPERIMENTALLY_VALIDATED.value)], "a")
    b = leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability")], "b")
    mixed = assess(world, ClaimNode("or", combine=Combine.OR, children=(a, b)), g).vector
    assert not (mixed.level(Factor.VALIDATION) == 2 and mixed.level(Factor.APPLICABILITY) == 1)
    dependent = graph(world, EvidenceEdge("exp", "bench", R.DERIVED_FROM))
    rep = assess(world, ClaimNode("or", combine=Combine.OR, children=(weak, strong)), dependent)
    assert rep.vector.level(Factor.VALIDATION) == 1 and any("not shown independent" in x for x in rep.notes)
    one = assess(world, ClaimNode("x", combine=Combine.AND, children=(weak,)), g)
    both = assess(world, ClaimNode("x", combine=Combine.AND, children=(weak, strong)), g)
    assert one.claim_structure_digest != both.claim_structure_digest


def test_adversarial_standing_needs_a_surviving_envelope_for_this_subject(world):          # H-C6
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("result", (x,))
    routes = (Route("a", "f", 1, lambda p: RouteResult(0.1)), Route("b", "g", 2, lambda p: RouteResult(0.1)))
    survived = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    nodes = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(survived)))
    pins = TrustedSourceRegistry(world["pins"].pins + (SourcePin(nodes["rt"].provenance.source_id, nodes["rt"].provenance.issuer,
                                                                 nodes["rt"].provenance.document_digest, "1"),))
    claim = ClaimNode("c", tuple(full_claims()) + (FactorClaim(Factor.ADVERSARIAL, 1, ("rt",), ENVELOPE_SURVIVED),),
                      subject_id="result", attacked_subject_digest=survived.subject_digest)
    g = graph(world, nodes=nodes)
    assert assess(world, claim, g, RiskClass.CRITICAL, trusted_sources=pins, red_team=(survived,)).vector.level(Factor.ADVERSARIAL) == 1
    assert assess(world, claim, g, RiskClass.CRITICAL, trusted_sources=pins).vector.level(Factor.ADVERSARIAL) == UNKNOWN
    other_space = AttackSpace("someone-else", (x,))
    unrelated = run_red_team(ClaimSubject("someone-else", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), other_space,
                             AttackPlan(other_space.digest, 200, "s"))
    nodes_u = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(unrelated)))
    pins_u = TrustedSourceRegistry(world["pins"].pins + (SourcePin(nodes_u["rt"].provenance.source_id, nodes_u["rt"].provenance.issuer,
                                                                   nodes_u["rt"].provenance.document_digest, "1"),))
    assert assess(world, claim, graph(world, nodes=nodes_u), RiskClass.CRITICAL, trusted_sources=pins_u,
                  red_team=(unrelated,)).vector.level(Factor.ADVERSARIAL) == UNKNOWN
    with pytest.raises(CredibilityRefused, match="TrustEnvelope"):
        assess(world, claim, g, RiskClass.CRITICAL, trusted_sources=pins, red_team=(object(),))
    broken = (Route("a", "f", 1, lambda p: RouteResult(5.0)), Route("b", "g", 2, lambda p: RouteResult(5.0)))
    falsified = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, broken, "a"), space, AttackPlan(space.digest, 200, "s"))
    assert falsified.outcome is EnvelopeOutcome.FALSIFIED and isinstance(falsified, TrustEnvelope)
    rep = assess(world, claim, g, RiskClass.CRITICAL, trusted_sources=pins, red_team=(survived, falsified))
    assert not rep.requirement_met and any(d.kind == "red_team_falsified" for d in rep.open_defeaters)


def test_removing_evidence_never_raises_any_factor_or_meets_a_requirement(world):
    claims = full_claims()
    base = assess(world, leaf(claims), graph(world))
    ids = sorted({e for c in claims for e in c.evidence_ids})
    for k in (1, 2):
        for removed in itertools.combinations(ids, k):
            rep = assess(world, leaf(claims), graph(world, drop=removed))
            assert all(rep.vector.level(f) <= base.vector.level(f) for f in Factor), removed
            assert not rep.requirement_met or base.requirement_met
    contradicted = assess(world, leaf(claims), graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS)))
    assert contradicted.graph_digest != base.graph_digest and not contradicted.requirement_met


# ---------------------------------------------------------------------------- second confirmation review


def _pins_with(w, *extra):
    add = {n.provenance.source_id: SourcePin(n.provenance.source_id, n.provenance.issuer, n.provenance.document_digest,
                                             n.provenance.version) for n in extra}
    return TrustedSourceRegistry(tuple(p for p in w["pins"].pins if p.source_id not in add) + tuple(add.values()))


def test_a_contradiction_of_the_subject_or_its_lineage_is_a_defeater_in_any_child_order(world):      # BLOCKER-1
    nodes = dict(world["nodes"], lab=node("lab", A.EXPERIMENT), model=node("model", A.ANALYTICAL))
    assert assess(world, leaf(), graph(world, nodes=nodes)).requirement_met
    direct = assess(world, leaf(), graph(world, EvidenceEdge("lab", "result", R.CONTRADICTS), nodes=nodes))
    assert not direct.requirement_met and any(d.evidence_ids == ("lab", "result") for d in direct.open_defeaters)
    lineage = assess(world, leaf(), graph(world, EvidenceEdge("result", "model", R.DERIVED_FROM),
                                          EvidenceEdge("lab", "model", R.CONTRADICTS), nodes=nodes))
    assert not lineage.requirement_met and any(d.evidence_ids == ("lab", "model") for d in lineage.open_defeaters)
    # two subjects: the verdict does not depend on which child is processed last
    other = dict(nodes, result2=node("result2", A.SIMULATION))
    edges = [EvidenceEdge(k, "result2", R.SUPPORTS) for k in world["nodes"] if k not in ("result", "rumour")]
    g = graph(world, *edges, EvidenceEdge("lab", "result", R.CONTRADICTS), nodes=other)
    a = ClaimNode("a", (FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value),), subject_id="result")
    b = ClaimNode("b", (FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value),), subject_id="result2")
    for kids in ((a, b), (b, a)):
        for how in (Combine.AND, Combine.OR):
            rep = assess(world, ClaimNode("x", combine=how, children=kids), g, RiskClass.LOW)
            assert any(d.evidence_ids == ("lab", "result") for d in rep.open_defeaters), (how, [k.node_id for k in kids])


def test_a_cited_contradicted_record_defeats_even_when_it_did_not_win_its_factor(world):            # HIGH-1
    claims = list(full_claims()) + [FactorClaim(Factor.VALIDATION, 1, ("bench",), VL.BENCHMARK_VALIDATED.value)]
    claims = [c for c in claims if c.factor is not Factor.MEASUREMENT_UQ and c.factor is not Factor.INDEPENDENT_ROUTES]
    g = graph(world, EvidenceEdge("muq", "exp", R.CONTRADICTS))
    exp_check = world["checks"][0]
    exp_pin = world["nodes"]["exp"].provenance.source_id
    variants = [assess(world, leaf(claims), g, RiskClass.MEDIUM),
                assess(world, leaf(claims), g, RiskClass.MEDIUM, validation_checks=tuple(c for c in world["checks"] if c is not exp_check)),
                assess(world, leaf(claims), g, RiskClass.MEDIUM,
                       trusted_sources=TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != exp_pin)))]
    assert variants[1].vector.level(Factor.VALIDATION) == 1                               # bench took over the factor ...
    for rep in variants:                                                                  # ... but exp is still cited and contradicted
        assert not rep.requirement_met and any(d.evidence_ids == ("muq", "exp") for d in rep.open_defeaters)


def test_supersession_only_lowers_whatever_the_superseder_s_pin_or_standing(world):              # HIGH-2
    c = world["nodes"]["conv"]
    v2 = node("conv_v2", A.SIMULATION, issuer=c.provenance.issuer, source_id=c.provenance.source_id, version="2")
    nodes = dict(world["nodes"], conv_v2=v2, lab=node("lab", A.EXPERIMENT))
    claims = [FactorClaim(Factor.VERIFICATION, 1, ("conv",), VL.NUMERICALLY_CONVERGED.value)]
    pinned = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != c.provenance.source_id)
                                   + (SourcePin(c.provenance.source_id, c.provenance.issuer, v2.provenance.document_digest, "2"),))
    sup = EvidenceEdge("conv_v2", "conv", R.SUPERSEDES)
    unpinned = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != c.provenance.source_id))
    for g, pins in ((graph(world, sup, nodes=nodes), pinned), (graph(world, sup, nodes=nodes), unpinned),
                    (graph(world, sup, nodes=nodes), None),
                    (graph(world, sup, EvidenceEdge("lab", "conv_v2", R.CONTRADICTS), nodes=nodes), pinned)):
        rep = assess(world, leaf(claims), g, RiskClass.LOW, trusted_sources=pins)
        assert rep.vector.level(Factor.VERIFICATION) == UNKNOWN and any("superseded" in r for r in rep.vector.rejected)


def test_applicability_and_uq_are_backed_by_existing_records_not_labels(world):                     # HIGH-3
    nodes = dict(world["nodes"], d1=node("d1", A.SIMULATION, digest=_h("anything")),
                 copy=node("copy", A.SIMULATION, digest=world["nodes"]["result"].content_digest))
    pins = _pins_with(world, nodes["d1"], nodes["copy"])
    bare = [FactorClaim(Factor.APPLICABILITY, 1, ("d1",), "applicability"),
            FactorClaim(Factor.VERIFICATION, 1, ("conv",), VL.NUMERICALLY_CONVERGED.value),
            FactorClaim(Factor.NUMERICAL_UQ, 1, ("copy",), "numerical")]
    rep = assess(world, leaf(bare), graph(world, nodes=nodes), RiskClass.LOW, trusted_sources=pins)
    assert not rep.requirement_met
    assert rep.vector.level(Factor.APPLICABILITY) == UNKNOWN and rep.vector.level(Factor.NUMERICAL_UQ) == UNKNOWN
    # the record must be SUPPLIED (re-read), decided on THIS subject, of THIS channel, quantified with that channel's source
    assert assess(world, leaf(), graph(world), applicability_reports=()).vector.level(Factor.APPLICABILITY) == UNKNOWN
    assert assess(world, leaf(), graph(world), uncertainty_entries=()).vector.level(Factor.MODEL_FORM_UQ) == UNKNOWN
    elsewhere = ApplicabilityReport("domain.check", "within", _h("another result"), "x")
    n2 = dict(world["nodes"], domain=node("domain", A.ANALYTICAL, digest=record_digest(elsewhere)))
    assert assess(world, leaf(), graph(world, nodes=n2), applicability_reports=(elsewhere,),
                  trusted_sources=_pins_with(world, n2["domain"])).vector.level(Factor.APPLICABILITY) == UNKNOWN
    unattributed = quantified(UC.NUMERICAL, US.UNSPECIFIED)
    unknown = ChannelEntry(UC.NUMERICAL, ChannelState.UNKNOWN)
    wrong_channel = quantified(UC.EPISTEMIC_PARAMETER, US.PARAMETER)
    for entry in (unattributed, unknown, wrong_channel):
        n3 = dict(world["nodes"], nuq=node("nuq", A.SIMULATION, digest=record_digest(entry)))
        rep = assess(world, leaf(), graph(world, nodes=n3), uncertainty_entries=world["entries"] + (entry,),
                     trusted_sources=_pins_with(world, n3["nuq"]))
        assert rep.vector.level(Factor.NUMERICAL_UQ) == UNKNOWN, entry
    # NOT_APPLICABLE declares (level 0) only with pinned provenance, from an authority that could quantify the channel,
    # and never for model form (that would turn missing model discrepancy into zero)  -- second-round M-4
    na = ChannelEntry(UC.ALEATORIC, ChannelState.NOT_APPLICABLE, rationale="a single deterministic reading")
    for authority, prov, expected in ((A.SIMULATION, True, UNKNOWN), (A.EXPERIMENT, True, 0), (A.EXPERIMENT, False, UNKNOWN)):
        n4 = dict(world["nodes"], na=node("na", authority, digest=record_digest(na), provenance=prov))
        claim = [FactorClaim(Factor.MEASUREMENT_UQ, 0, ("na",), "aleatoric")]
        pins = _pins_with(world, n4["na"]) if prov else world["pins"]
        rep = assess(world, leaf(claim), graph(world, nodes=n4), uncertainty_entries=(na,), trusted_sources=pins)
        assert rep.vector.level(Factor.MEASUREMENT_UQ) == expected, (authority, prov)
    na_mf = ChannelEntry(UC.MODEL_FORM, ChannelState.NOT_APPLICABLE, rationale="no model-form freedom in this check")
    n5 = dict(world["nodes"], na=node("na", A.EXPERIMENT, digest=record_digest(na_mf)))
    rep = assess(world, leaf([FactorClaim(Factor.MODEL_FORM_UQ, 0, ("na",), "model_form")]), graph(world, nodes=n5),
                 uncertainty_entries=(na_mf,), trusted_sources=_pins_with(world, n5["na"]))
    assert rep.vector.level(Factor.MODEL_FORM_UQ) == UNKNOWN
    # an 'outside' report decided on the subject is a defeater without anyone citing it
    outside = ApplicabilityReport("domain.check2", "outside", RESULT_DIGEST, "temperature above the fitted range")
    rep = assess(world, leaf(), graph(world), applicability_reports=world["reports"] + (outside,))
    assert not rep.requirement_met and rep.dominant_blocking_gap["defeater"]["kind"] == "outside_domain"


def test_citing_an_outside_domain_record_twice_does_not_cancel_it(world):                          # MEDIUM-1
    claims = list(full_claims()) + [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability"),
                                    FactorClaim(Factor.MODEL_FORM_UQ, 0, ("domain_out",), "model_form")]
    rep = assess(world, leaf(claims), graph(world))
    assert not rep.requirement_met and any(d.kind == "outside_domain" for d in rep.open_defeaters)


def test_an_envelope_for_another_statement_of_the_claim_supplies_nothing(world):                    # MEDIUM-2
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("result", (x,))
    routes = (Route("a", "f", 1, lambda p: RouteResult(0.1)), Route("b", "g", 2, lambda p: RouteResult(0.1)))
    real = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    vacuous = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1e300, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    assert vacuous.outcome is EnvelopeOutcome.SURVIVED and vacuous.subject_digest != real.subject_digest
    nodes = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(vacuous)))
    pins = _pins_with(world, nodes["rt"])
    adv = (FactorClaim(Factor.ADVERSARIAL, 1, ("rt",), ENVELOPE_SURVIVED),)
    g = graph(world, nodes=nodes)
    declared_real = ClaimNode("c", tuple(full_claims()) + adv, subject_id="result", attacked_subject_digest=real.subject_digest)
    undeclared = ClaimNode("c", tuple(full_claims()) + adv, subject_id="result")
    for claim in (declared_real, undeclared):
        rep = assess(world, claim, g, RiskClass.CRITICAL, trusted_sources=pins, red_team=(vacuous,))
        assert rep.vector.level(Factor.ADVERSARIAL) == UNKNOWN and not rep.requirement_met
    honest = ClaimNode("c", tuple(full_claims()) + adv, subject_id="result", attacked_subject_digest=vacuous.subject_digest)
    assert honest.structure() != declared_real.structure()                              # what was attacked is in the claim digest
    with pytest.raises(CredibilityRefused, match="attacked_subject_digest"):
        ClaimNode("c", tuple(full_claims()), subject_id="result", attacked_subject_digest="nope")


def test_the_calibration_guard_follows_duplicate_content_and_lineage(world):                       # MEDIUM-3
    exp = world["nodes"]["exp"]
    twin = dict(world["nodes"], exp_cal=node("exp_cal", A.EXPERIMENT, digest=exp.content_digest, issuer="iss:cal"))
    g1 = graph(world, EvidenceEdge("exp_cal", "result", R.CALIBRATES), nodes=twin, support=True)
    assert assess(world, leaf(), g1, trusted_sources=_pins_with(world, twin["exp_cal"])).vector.level(Factor.VALIDATION) == UNKNOWN
    lineage = dict(world["nodes"], cal_data=node("cal_data", A.MEASUREMENT))
    g2 = graph(world, EvidenceEdge("exp", "cal_data", R.DERIVED_FROM), EvidenceEdge("cal_data", "result", R.CALIBRATES), nodes=lineage)
    assert assess(world, leaf(), g2).vector.level(Factor.VALIDATION) == UNKNOWN


def test_refused_records_leave_a_note_and_falsified_envelopes_of_other_claims_are_not_defeaters(world):   # LOWs
    forged = ValidationCheck("conv2", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.001, tolerance=0.01,
                             evidence=("x",))
    object.__setattr__(forged, "establishes", VL.EXPERIMENTALLY_VALIDATED)                # tampered after construction
    rep = assess(world, leaf(), graph(world), validation_checks=world["checks"] + (forged,))
    assert any("refused on re-read" in n for n in rep.notes)
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("someone-else", (x,))
    broken = (Route("a", "f", 1, lambda p: RouteResult(5.0)), Route("b", "g", 2, lambda p: RouteResult(5.0)))
    other = run_red_team(ClaimSubject("someone-else", "y", "1", Sense.AT_MOST, 1.0, broken, "a"), space, AttackPlan(space.digest, 200, "s"))
    assert other.outcome is EnvelopeOutcome.FALSIFIED
    rep = assess(world, leaf(), graph(world), red_team=(other,))
    assert rep.requirement_met and any("no subject of this claim" in n for n in rep.notes)


# ---------------------------------------------------------------------------- third confirmation review


def test_an_outside_domain_finding_is_judged_like_a_defeater(world):                                   # NEW-1
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    nodes = dict(world["nodes"], patch=node("patch", A.SIMULATION, provenance=False))
    lifted = assess(world, leaf(claims), graph(world, EvidenceEdge("patch", "domain_out", R.SUPERSEDES), nodes=nodes))
    assert not lifted.requirement_met and any(d.kind == "outside_domain" for d in lifted.open_defeaters)
    unlinked = EvidenceGraph(tuple(world["nodes"].values()), tuple(EvidenceEdge(k, "result", R.SUPPORTS) for k in world["nodes"]
                                                                   if k not in ("result", "rumour", "domain_out")))
    rep = assess(world, leaf(claims), unlinked)                       # an outside finding need not SUPPORT the result
    assert not rep.requirement_met and any(d.kind == "outside_domain" for d in rep.open_defeaters)
    with pytest.raises(CredibilityRefused, match="not in the graph"):
        assess(world, leaf(claims), graph(world, drop=("domain_out",)))
    d = world["nodes"]["domain_out"]                                  # only a registry-pinned newer version closes it
    newer = node("domain_out_v2", A.ANALYTICAL, issuer=d.provenance.issuer, source_id=d.provenance.source_id, version="2")
    pins = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != d.provenance.source_id)
                                 + (SourcePin(d.provenance.source_id, d.provenance.issuer, newer.provenance.document_digest, "2"),))
    closed = assess(world, leaf(claims), graph(world, EvidenceEdge("domain_out_v2", "domain_out", R.SUPERSEDES),
                                               nodes=dict(world["nodes"], domain_out_v2=newer)), trusted_sources=pins)
    assert not any(x.kind == "outside_domain" for x in closed.open_defeaters) and any("closed by" in r for r in closed.vector.rejected)


def test_contradicted_calibration_data_defeats_and_nothing_is_dropped_silently(world):                 # NEW-2
    nodes = dict(world["nodes"], cal_data=node("cal_data", A.MEASUREMENT), lab=node("lab", A.EXPERIMENT),
                 elsewhere=node("elsewhere", A.MEASUREMENT))
    g = graph(world, EvidenceEdge("cal_data", "result", R.CALIBRATES), EvidenceEdge("lab", "cal_data", R.CONTRADICTS), nodes=nodes)
    rep = assess(world, leaf(), g)
    assert not rep.requirement_met and any(d.evidence_ids == ("lab", "cal_data") for d in rep.open_defeaters)
    g2 = EvidenceGraph(g.nodes, tuple(e for e in g.edges if e.relation is not R.CALIBRATES and e.source_id != "elsewhere")
                       + (EvidenceEdge("lab", "elsewhere", R.CONTRADICTS),))
    rep2 = assess(world, leaf(), g2)
    assert any("not something this claim rests on" in n for n in rep2.notes)


def test_a_same_content_twin_does_not_escape_contradiction_or_supersession(world):                    # NEW-3
    exp, conv = world["nodes"]["exp"], world["nodes"]["conv"]
    twin = node("exp_copy", A.EXPERIMENT, digest=exp.content_digest, issuer="iss:copy")
    nodes = dict(world["nodes"], exp_copy=twin, lab=node("lab", A.EXPERIMENT))
    claims = [c if c.factor is not Factor.VALIDATION else FactorClaim(Factor.VALIDATION, 2, ("exp_copy",), VL.EXPERIMENTALLY_VALIDATED.value)
              for c in full_claims()]
    rep = assess(world, leaf(claims), graph(world, EvidenceEdge("lab", "exp", R.CONTRADICTS), nodes=nodes),
                 trusted_sources=_pins_with(world, twin))
    assert not rep.requirement_met and any(d.evidence_ids == ("lab", "exp") for d in rep.open_defeaters)
    conv_copy = node("conv_copy", A.SIMULATION, digest=conv.content_digest, issuer="iss:conv_copy")
    nodes = dict(world["nodes"], conv_copy=conv_copy, conv_v2=node("conv_v2", A.SIMULATION))
    rep = assess(world, leaf([FactorClaim(Factor.VERIFICATION, 1, ("conv_copy",), VL.NUMERICALLY_CONVERGED.value)]),
                 graph(world, EvidenceEdge("conv_v2", "conv", R.SUPERSEDES), nodes=nodes), RiskClass.LOW)
    assert rep.vector.level(Factor.VERIFICATION) == UNKNOWN


def test_the_report_binds_its_inputs_and_unbound_negative_reports_are_noted(world):                   # M-1
    outside = ApplicabilityReport("domain.check2", "outside", RESULT_DIGEST, "temperature above the fitted range")
    with_it = assess(world, leaf(), graph(world), applicability_reports=world["reports"] + (outside,))
    without = assess(world, leaf(), graph(world))
    assert with_it.graph_digest == without.graph_digest and with_it.inputs_digest != without.inputs_digest
    assert with_it.to_dict()["inputs_digest"] == with_it.inputs_digest
    assert assess(world, leaf(), graph(world), trusted_sources=None).inputs_digest != without.inputs_digest
    unbound = ApplicabilityReport("domain.check3", "outside", "", "no evidence named")
    rep = assess(world, leaf(), graph(world), applicability_reports=world["reports"] + (unbound,))
    assert any("decided on no subject" in n for n in rep.notes)


def test_an_unknown_check_caps_applicability_and_an_outside_report_sets_the_level(world):             # M-2, L-1
    unknown = ApplicabilityReport("domain.check2", "unknown", RESULT_DIGEST, "T not evaluated")
    rep = assess(world, leaf(), graph(world), applicability_reports=world["reports"] + (unknown,))
    assert not rep.requirement_met and rep.vector.level(Factor.APPLICABILITY) == UNKNOWN
    assert rep.dominant_blocking_gap["gap_class"] == GapClass.MODEL_APPLICABILITY_UNKNOWN.value
    outside = ApplicabilityReport("domain.check2", "outside", RESULT_DIGEST, "too hot")
    rep = assess(world, leaf(), graph(world), applicability_reports=world["reports"] + (outside,))
    assert rep.vector.level(Factor.APPLICABILITY) == 0
    assert next(g for g in rep.gaps if g.factor is Factor.APPLICABILITY).gap_class is GapClass.MODEL_OUTSIDE_DOMAIN


def test_any_supersession_disqualifies_support_and_an_obsolete_subject_is_defeated(world):            # M-5, M-6
    rep = assess(world, leaf(), graph(world, EvidenceEdge("rumour", "conv", R.SUPERSEDES)))
    assert rep.vector.level(Factor.VERIFICATION) == UNKNOWN                      # the canonical rule: SUPERSEDED
    nodes = dict(world["nodes"], result_v2=node("result_v2", A.SIMULATION))
    rep = assess(world, leaf(), graph(world, EvidenceEdge("result_v2", "result", R.SUPERSEDES), nodes=nodes))
    assert not rep.requirement_met and any(d.kind == "superseded" for d in rep.open_defeaters)
    # a contradiction from something the claim rests on is not closed by superseding that thing
    m = node("model", A.ANALYTICAL, issuer="iss:model", source_id="sid:model")
    m2 = node("model_v2", A.ANALYTICAL, issuer="iss:model", source_id="sid:model", version="2")
    pins = TrustedSourceRegistry(world["pins"].pins + (SourcePin("sid:model", "iss:model", m2.provenance.document_digest, "2"),))
    g = graph(world, EvidenceEdge("result", "model", R.DERIVED_FROM), EvidenceEdge("model", "exp", R.CONTRADICTS),
              EvidenceEdge("model_v2", "model", R.SUPERSEDES), nodes=dict(world["nodes"], model=m, model_v2=m2))
    rep = assess(world, leaf(), g, trusted_sources=pins)
    assert any(d.evidence_ids == ("model", "exp") for d in rep.open_defeaters)


def test_an_incoherent_envelope_backs_nothing(world):                                                  # L-3
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("result", (x,))
    routes = (Route("a", "f", 1, lambda p: RouteResult(0.1)), Route("b", "g", 2, lambda p: RouteResult(0.1)))
    real = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    import dataclasses
    hollow = dataclasses.replace(real, evaluations=0, points_covered=0)
    nodes = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(hollow)))
    claim = ClaimNode("c", tuple(full_claims()) + (FactorClaim(Factor.ADVERSARIAL, 1, ("rt",), ENVELOPE_SURVIVED),),
                      subject_id="result", attacked_subject_digest=real.subject_digest)
    rep = assess(world, claim, graph(world, nodes=nodes), RiskClass.CRITICAL, trusted_sources=_pins_with(world, nodes["rt"]),
                 red_team=(hollow,))
    assert rep.vector.level(Factor.ADVERSARIAL) == UNKNOWN


# ---------------------------------------------------------------------------- fourth confirmation review


def test_an_obsolete_subject_is_defeated_whatever_else_links_it_to_its_replacement(world):         # finding 1
    nodes = dict(world["nodes"], result_v2=node("result_v2", A.SIMULATION))
    for extra in (EvidenceEdge("result", "result_v2", R.SUPPORTS), EvidenceEdge("result_v2", "result", R.CALIBRATES)):
        rep = assess(world, leaf(), graph(world, EvidenceEdge("result_v2", "result", R.SUPERSEDES), extra, nodes=nodes))
        assert not rep.requirement_met and any(d.kind == "superseded" for d in rep.open_defeaters), extra


def test_or_never_meets_a_requirement_because_a_branch_lost_evidence(world):                         # finding 2
    within_b = ApplicabilityReport("domain.check.b", "within", RESULT_DIGEST, "b")
    conv_b = ValidationCheck("conv_b", ValidationOutcome.PASS, establishes=VL.NUMERICALLY_CONVERGED, residual=0.001, tolerance=0.01,
                             evidence=("r:b",))
    nodes = dict(world["nodes"], domain_b=node("domain_b", A.ANALYTICAL, digest=record_digest(within_b)),
                 conv_b=node("conv_b", A.SIMULATION, digest=check_digest(conv_b)))
    pins = _pins_with(world, nodes["domain_b"], nodes["conv_b"])
    a = leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain",), "applicability"),
              FactorClaim(Factor.VERIFICATION, 2, ("conv", "mms"), VL.ANALYTICALLY_VERIFIED.value)], "a")
    b = leaf([FactorClaim(Factor.APPLICABILITY, 1, ("domain_b",), "applicability"),
              FactorClaim(Factor.VERIFICATION, 1, ("conv_b",), VL.NUMERICALLY_CONVERGED.value),
              FactorClaim(Factor.NUMERICAL_UQ, 0, ("nuq",), "numerical")], "b")
    claim = ClaimNode("or", combine=Combine.OR, children=(a, b))
    kw = dict(trusted_sources=pins, validation_checks=world["checks"] + (conv_b,), applicability_reports=(world["reports"][0], within_b))
    g = graph(world, nodes=nodes)
    full = assess(world, claim, g, RiskClass.LOW, **kw)
    mms_check = world["checks"][2]
    variants = [assess(world, claim, g, RiskClass.LOW, **dict(kw, validation_checks=tuple(c for c in kw["validation_checks"]
                                                                                          if c is not mms_check))),
                assess(world, claim, graph(world, EvidenceEdge("rumour", "mms", R.SUPERSEDES), nodes=nodes), RiskClass.LOW, **kw)]
    assert full.requirement_met, full.notes                         # the branch that meets the bar is the one chosen
    for rep in variants:                                            # ... and stays chosen when the other branch loses evidence
        assert rep.requirement_met and rep.vector.level(Factor.NUMERICAL_UQ) == full.vector.level(Factor.NUMERICAL_UQ)
    # neither branch meets the bar: removing evidence from either never makes the OR met
    b_short = leaf([c for c in b.claims if c.factor is not Factor.NUMERICAL_UQ], "b")
    short = ClaimNode("or", combine=Combine.OR, children=(a, b_short))
    base = assess(world, short, g, RiskClass.LOW, **kw)
    assert not base.requirement_met
    for removed in (("mms",), ("conv",), ("domain",), ("domain_b",), ("conv_b",)):
        assert not assess(world, short, graph(world, nodes={k: v for k, v in nodes.items() if k not in removed}), RiskClass.LOW,
                          **kw).requirement_met, removed


def test_independence_follows_shared_calibration_and_same_content_ancestry(world):                  # finding 3
    two = [FactorClaim(Factor.INDEPENDENT_ROUTES, 2, ("route_a", "route_b"), VL.CROSS_SOLVER_VALIDATED.value)]
    nodes = dict(world["nodes"], cal=node("cal", A.MEASUREMENT), x=node("x", A.MEASUREMENT),
                 x_copy=node("x_copy", A.MEASUREMENT, digest=_h("x")))
    tuned = graph(world, EvidenceEdge("cal", "route_a", R.CALIBRATES), EvidenceEdge("cal", "route_b", R.CALIBRATES), nodes=nodes)
    assert assess(world, leaf(two), tuned).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    copied = graph(world, EvidenceEdge("route_a", "x", R.DERIVED_FROM), EvidenceEdge("route_b", "x_copy", R.DERIVED_FROM), nodes=nodes)
    assert assess(world, leaf(two), copied).vector.level(Factor.INDEPENDENT_ROUTES) == UNKNOWN
    assert assess(world, leaf(two), graph(world, nodes=nodes)).vector.level(Factor.INDEPENDENT_ROUTES) == 2


def test_the_calibration_guard_compares_the_validator_with_every_calibration_input(world):           # finding 4
    nodes = dict(world["nodes"], cal_data=node("cal_data", A.MEASUREMENT), X=node("X", A.MEASUREMENT),
                 result_copy=node("result_copy", A.SIMULATION, digest=RESULT_DIGEST))
    for edges in ((EvidenceEdge("cal_data", "exp", R.DERIVED_FROM), EvidenceEdge("cal_data", "result", R.CALIBRATES)),
                  (EvidenceEdge("X", "exp", R.CALIBRATES), EvidenceEdge("X", "result", R.CALIBRATES)),
                  (EvidenceEdge("exp", "result_copy", R.CALIBRATES),)):
        assert assess(world, leaf(), graph(world, *edges, nodes=nodes)).vector.level(Factor.VALIDATION) == UNKNOWN, edges
    assert assess(world, leaf(), graph(world, nodes=nodes)).vector.level(Factor.VALIDATION) == 2


def test_a_model_never_declares_its_own_model_form_discrepancy(world):                              # finding 5
    zero = ChannelEntry(UC.MODEL_FORM, ChannelState.KNOWN, Uncertainty(kind=UncertaintyKind.STANDARD,
                        standard_uncertainty=Quantity(0.0, "volt"), method="self", source_kind=US.MODEL_FORM), source="model")
    claim = [FactorClaim(Factor.MODEL_FORM_UQ, 0, ("mf0",), "model_form")]
    for prov in (False, True):
        nodes = dict(world["nodes"], mf0=node("mf0", A.SIMULATION, digest=record_digest(zero), provenance=prov))
        pins = _pins_with(world, nodes["mf0"]) if prov else world["pins"]
        rep = assess(world, leaf(claim), graph(world, nodes=nodes), uncertainty_entries=(zero,), trusted_sources=pins)
        assert rep.vector.level(Factor.MODEL_FORM_UQ) == UNKNOWN
    nodes = dict(world["nodes"], mf0=node("mf0", A.EXPERIMENT, digest=record_digest(zero), provenance=False))
    rep = assess(world, leaf(claim), graph(world, nodes=nodes), uncertainty_entries=(zero,))
    assert rep.vector.level(Factor.MODEL_FORM_UQ) == UNKNOWN                     # an outside reference still needs a pin


def test_a_contradiction_is_a_conflict_whichever_side_wrote_it(world):                              # finding 6
    nodes = dict(world["nodes"], lab=node("lab", A.EXPERIMENT))
    rep = assess(world, leaf(), graph(world, EvidenceEdge("result", "lab", R.CONTRADICTS), nodes=nodes))
    assert not rep.requirement_met and any(d.evidence_ids == ("result", "lab") for d in rep.open_defeaters)
    rumour = assess(world, leaf(), graph(world, EvidenceEdge("result", "rumour", R.CONTRADICTS)))
    assert rumour.requirement_met and any("sub-bar contradiction" in n for n in rumour.notes)


def test_fourth_review_lows(world):
    # an UNKNOWN envelope for the same statement caps adversarial standing
    x = AttackDimension("F", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1")
    space = AttackSpace("result", (x,))
    routes = (Route("a", "f", 1, lambda p: RouteResult(0.1)), Route("b", "g", 2, lambda p: RouteResult(0.1)))
    survived = run_red_team(ClaimSubject("result", "y", "1", Sense.AT_MOST, 1.0, routes, "a"), space, AttackPlan(space.digest, 200, "s"))
    import dataclasses
    nodes = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(survived)))
    claim = ClaimNode("c", tuple(full_claims()) + (FactorClaim(Factor.ADVERSARIAL, 1, ("rt",), ENVELOPE_SURVIVED),),
                      subject_id="result", attacked_subject_digest=survived.subject_digest)
    kw = dict(trusted_sources=_pins_with(world, nodes["rt"]))
    g = graph(world, nodes=nodes)
    assert assess(world, claim, g, RiskClass.CRITICAL, red_team=(survived,), **kw).vector.level(Factor.ADVERSARIAL) == 1
    unknown = dataclasses.replace(survived, outcome=EnvelopeOutcome.UNKNOWN, reason="budget ran out")
    assert assess(world, claim, g, RiskClass.CRITICAL, red_team=(survived, unknown), **kw).vector.level(Factor.ADVERSARIAL) == UNKNOWN
    # incoherent envelopes: more coverage than evaluations, or no attacked route
    for bad in (dataclasses.replace(survived, evaluations=survived.points_covered - 1), dataclasses.replace(survived, attacked_routes=())):
        n2 = dict(world["nodes"], rt=node("rt", A.SIMULATION, digest=envelope_digest(bad)))
        rep = assess(world, claim, graph(world, nodes=n2), RiskClass.CRITICAL, red_team=(bad,), trusted_sources=_pins_with(world, n2["rt"]))
        assert rep.vector.level(Factor.ADVERSARIAL) == UNKNOWN
    # a contradiction of an ANCESTOR of calibration data reaches the claim (fixpoint)
    deep = dict(world["nodes"], cal_data=node("cal_data", A.MEASUREMENT), raw=node("raw", A.MEASUREMENT), lab=node("lab", A.EXPERIMENT))
    g3 = graph(world, EvidenceEdge("cal_data", "result", R.CALIBRATES), EvidenceEdge("cal_data", "raw", R.DERIVED_FROM),
               EvidenceEdge("lab", "raw", R.CONTRADICTS), nodes=deep)
    assert any(d.evidence_ids == ("lab", "raw") for d in assess(world, leaf(), g3).open_defeaters)


# ---------------------------------------------------------------------------- fifth confirmation review


def test_a_contradiction_inside_the_closure_needs_only_one_admissible_end(world):                  # NEW-1
    lab_cite = FactorClaim(Factor.MEASUREMENT_UQ, 0, ("lab",), "aleatoric")       # rejected (no entry); pulls lab inside
    for authority, prov in ((A.UNKNOWN, False), (A.ANALYTICAL, True)):
        nodes = dict(world["nodes"], model=node("model", authority, provenance=prov), lab=node("lab", A.EXPERIMENT))
        g = graph(world, EvidenceEdge("result", "model", R.DERIVED_FROM), EvidenceEdge("model", "lab", R.CONTRADICTS), nodes=nodes)
        for claims in (list(full_claims()), list(full_claims()) + [lab_cite]):
            rep = assess(world, leaf(claims), g)
            assert not rep.requirement_met and any(d.evidence_ids == ("model", "lab") for d in rep.open_defeaters), (authority, claims)
        both = graph(world, EvidenceEdge("result", "model", R.DERIVED_FROM), EvidenceEdge("result", "lab", R.DERIVED_FROM),
                     EvidenceEdge("model", "lab", R.CONTRADICTS), nodes=nodes)
        assert not assess(world, leaf(), both).requirement_met, authority


def test_a_contradicted_twin_disqualifies_a_closing_superseder(world):                              # NEW-4
    b = world["nodes"]["bench"]
    newer = node("bench_v2", A.REFERENCE_DATA, issuer=b.provenance.issuer, source_id=b.provenance.source_id, version="2")
    twin = node("bench_v2_copy", A.REFERENCE_DATA, digest=newer.content_digest, issuer="iss:copy")
    pins = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != b.provenance.source_id)
                                 + (SourcePin(b.provenance.source_id, b.provenance.issuer, newer.provenance.document_digest, "2"),))
    nodes = dict(world["nodes"], bench_v2=newer, bench_v2_copy=twin, lab=node("lab", A.EXPERIMENT))
    edges = (EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("bench_v2", "bench", R.SUPERSEDES))
    assert assess(world, leaf(), graph(world, *edges, nodes=nodes), trusted_sources=pins).requirement_met
    rep = assess(world, leaf(), graph(world, *edges, EvidenceEdge("lab", "bench_v2_copy", R.CONTRADICTS), nodes=nodes), trusted_sources=pins)
    assert any(d.evidence_ids == ("bench", "exp") for d in rep.open_defeaters)


# ---------------------------------------------------------------------------- sixth confirmation review


def test_a_closing_version_must_be_other_content_and_not_itself_obsolete(world):                   # M-1, L-1
    b, d = world["nodes"]["bench"], world["nodes"]["domain_out"]

    def pinned_v2(src, eid, authority, **kw):
        n = node(eid, authority, issuer=src.provenance.issuer, source_id=src.provenance.source_id, version="2", **kw)
        pins = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != src.provenance.source_id)
                                     + (SourcePin(src.provenance.source_id, src.provenance.issuer, n.provenance.document_digest, "2"),))
        return n, pins
    # the identical finding re-issued as "v2" closes nothing
    same, pins = pinned_v2(b, "bench_v2", A.REFERENCE_DATA, digest=b.content_digest)
    rep = assess(world, leaf(), graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("bench_v2", "bench", R.SUPERSEDES),
                                      nodes=dict(world["nodes"], bench_v2=same)), trusted_sources=pins)
    assert any(x.evidence_ids == ("bench", "exp") for x in rep.open_defeaters)
    out_same, pins_d = pinned_v2(d, "domain_out_v2", A.ANALYTICAL, digest=d.content_digest)
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    rep = assess(world, leaf(claims), graph(world, EvidenceEdge("domain_out_v2", "domain_out", R.SUPERSEDES),
                                            nodes=dict(world["nodes"], domain_out_v2=out_same)), trusted_sources=pins_d)
    assert any(x.kind == "outside_domain" for x in rep.open_defeaters)
    # a closer that is itself superseded (by anyone) or contradicts an admissible record (either direction) closes nothing
    newer, pins = pinned_v2(b, "bench_v2", A.REFERENCE_DATA)
    nodes = dict(world["nodes"], bench_v2=newer, lab=node("lab", A.EXPERIMENT))
    base = (EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("bench_v2", "bench", R.SUPERSEDES))
    assert assess(world, leaf(), graph(world, *base, nodes=nodes), trusted_sources=pins).requirement_met
    for extra in (EvidenceEdge("rumour", "bench_v2", R.SUPERSEDES), EvidenceEdge("bench_v2", "lab", R.CONTRADICTS)):
        rep = assess(world, leaf(), graph(world, *base, extra, nodes=nodes), trusted_sources=pins)
        assert any(x.evidence_ids == ("bench", "exp") for x in rep.open_defeaters), extra


def test_an_explicit_defeater_may_add_but_never_replace_a_computed_one(world):                    # L-3
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    with pytest.raises(CredibilityRefused, match="collides"):
        assess(world, leaf(claims), graph(world), defeaters=(Defeater("outside_domain:result", "superseded", (), "x"),))
    rep = assess(world, leaf(), graph(world), defeaters=(Defeater("review:1", "contradiction", ("exp",), "a reviewer's finding"),))
    assert not rep.requirement_met


# ---------------------------------------------------------------------------- seventh confirmation review (post-approval LOW)


def test_the_claim_s_own_records_never_close_its_defeaters(world):                                  # L-b
    d, b = world["nodes"]["domain_out"], world["nodes"]["bench"]
    # a CITED record that is a pinned newer version of the outside-domain source does not lift the outside-domain finding
    mms = world["nodes"]["mms"]
    mms_v2 = node("mms", A.ANALYTICAL, digest=mms.content_digest, issuer=d.provenance.issuer, source_id=d.provenance.source_id,
                  version="2")
    pins = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id not in (d.provenance.source_id, "sid:mms"))
                                 + (SourcePin(d.provenance.source_id, d.provenance.issuer, mms_v2.provenance.document_digest, "2"),))
    domain_as_analytical = dict(world["nodes"], mms=mms_v2)
    claims = [FactorClaim(Factor.APPLICABILITY, 0, ("domain_out",), "applicability")] + list(full_claims())
    rep = assess(world, leaf(claims), graph(world, EvidenceEdge("mms", "domain_out", R.SUPERSEDES), nodes=domain_as_analytical),
                 trusted_sources=pins)
    assert any(x.kind == "outside_domain" for x in rep.open_defeaters)
    # a CITED pinned newer version of a contradicting source does not close the contradiction either
    newer = node("bench_v2", A.REFERENCE_DATA, issuer=b.provenance.issuer, source_id=b.provenance.source_id, version="2")
    pins_b = TrustedSourceRegistry(tuple(p for p in world["pins"].pins if p.source_id != b.provenance.source_id)
                                   + (SourcePin(b.provenance.source_id, b.provenance.issuer, newer.provenance.document_digest, "2"),))
    g = graph(world, EvidenceEdge("bench", "exp", R.CONTRADICTS), EvidenceEdge("bench_v2", "bench", R.SUPERSEDES),
              nodes=dict(world["nodes"], bench_v2=newer))
    cites_v2 = list(full_claims()) + [FactorClaim(Factor.VALIDATION, 1, ("bench_v2",), VL.BENCHMARK_VALIDATED.value)]
    rep = assess(world, leaf(cites_v2), g, trusted_sources=pins_b)
    assert any(x.evidence_ids == ("bench", "exp") for x in rep.open_defeaters)
