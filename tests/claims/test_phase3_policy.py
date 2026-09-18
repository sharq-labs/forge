"""Phase 3 -- risk-aware evidence policy. Risk sets the bar; it is never evidence."""

from __future__ import annotations

import itertools
import json
from dataclasses import replace

import pytest

from claims_support import claim, et_claim, t3_claim
from engcore.claims import (
    BUILTIN_PROFILES,
    AssessmentForgeryError,
    ClaimContractError,
    DecisionConsequence,
    DecisionContext,
    EvidencePolicy,
    EvidencePolicyProfile,
    ModelInfluence,
    RiskClass,
    ScientificClaim,
    UncertaintyDemand,
    apply_policy,
    assess_claim,
    builtin_context,
    compile_claim,
    derive_requirement,
    plan_experiment,
    verify_assessment,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.mcp.capabilities import production_registry
from engcore.sria.uncertainty import UncertaintyChannel as C

RANK = {"low": 0, "medium": 1, "high": 2}
STRENGTH = {"insufficient_evidence": 0, "supported": 1, "contradicted": 1}
CELLS = list(itertools.product(ModelInfluence, DecisionConsequence))


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _ctx(profile_id="engineering_decision", influence="medium", consequence="medium"):
    return builtin_context(profile_id, influence=influence, consequence=consequence, owner="org:test-owner")


# ---------------------------------------------------------------------------
# Invariant 13 and profile construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile_id", sorted(BUILTIN_PROFILES))
def test_more_risk_never_requires_less_evidence_within_a_profile(profile_id) -> None:
    profile = BUILTIN_PROFILES[profile_id]
    for (i1, c1), (i2, c2) in itertools.product(CELLS, CELLS):
        if RANK[i2.value] >= RANK[i1.value] and RANK[c2.value] >= RANK[c1.value]:
            lo, hi = profile.risk_class(i1, c1), profile.risk_class(i2, c2)
            assert RANK[hi.value] >= RANK[lo.value]
            assert profile.policies[hi].covers(profile.policies[lo])


@pytest.mark.parametrize("profile_id", sorted(BUILTIN_PROFILES))
def test_the_effective_claim_only_ever_gains_requirements(profile_id) -> None:
    base = t3_claim(uncertainty=UncertaintyDemand(frozenset({C.ALEATORIC}), 2.0, False))
    previous = None
    for influence, consequence in CELLS:
        effective = apply_policy(replace(base, decision_context=_ctx(profile_id, influence.value, consequence.value)))
        assert set(effective.evidence.required_levels) >= set(base.evidence.required_levels)
        assert effective.uncertainty.required_channels >= base.uncertainty.required_channels
        assert effective.uncertainty.coverage_factor >= base.uncertainty.coverage_factor
        assert apply_policy(effective) == effective  # idempotent
    assert apply_policy(base) is base  # no context: untouched


def _profile(**overrides):
    fields = dict(
        profile_id="org:acme_thermal", version="3", description="Acme's thermal sign-off policy",
        risk_matrix={f"{i.value}/{c.value}": ("high" if i is ModelInfluence.HIGH else "low") for i, c in CELLS},
        policies={RiskClass.LOW: EvidencePolicy(), RiskClass.MEDIUM: EvidencePolicy(require_independent_route=True),
                  RiskClass.HIGH: EvidencePolicy(require_independent_route=True, required_channels=frozenset({C.NUMERICAL}))},
    )
    fields.update(overrides)
    return EvidencePolicyProfile(**fields)


def test_an_organization_profile_is_accepted_and_round_trips() -> None:
    profile = _profile()
    assert EvidencePolicyProfile.from_dict(json.loads(json.dumps(profile.to_dict()))).digest == profile.digest


def test_a_non_monotone_matrix_is_refused() -> None:
    matrix = dict(_profile().risk_matrix)
    matrix["high/high"] = RiskClass.LOW
    with pytest.raises(ClaimContractError, match="not monotone"):
        _profile(risk_matrix=matrix)


def test_a_higher_risk_policy_that_demands_less_is_refused() -> None:
    policies = dict(_profile().policies)
    policies[RiskClass.HIGH] = EvidencePolicy()
    with pytest.raises(ClaimContractError, match="never less"):
        _profile(policies=policies)
    policies[RiskClass.HIGH] = EvidencePolicy(require_independent_route=True, coverage_factor=1.0)
    policies[RiskClass.MEDIUM] = EvidencePolicy(require_independent_route=True, coverage_factor=2.0)
    with pytest.raises(ClaimContractError, match="never less"):
        _profile(policies=policies)


def test_a_matrix_missing_a_cell_is_refused() -> None:
    matrix = dict(_profile().risk_matrix)
    del matrix["low/low"]
    with pytest.raises(ClaimContractError, match="every influence/consequence cell"):
        _profile(risk_matrix=matrix)


def test_a_built_in_profile_id_cannot_be_impersonated() -> None:
    weak = replace(BUILTIN_PROFILES["high_consequence_engineering"], policies={r: EvidencePolicy() for r in RiskClass})
    with pytest.raises(ClaimContractError, match="built-in"):
        DecisionContext("q", "u", "high", "high", "org", "r", weak)


def test_consequence_is_stated_never_inferred() -> None:
    ctx = _ctx().to_dict()
    for key in ("model_influence", "decision_consequence", "consequence_owner"):
        broken = dict(ctx)
        del broken[key]
        with pytest.raises(ClaimContractError):
            DecisionContext.from_dict(broken)
    # Prose that sounds dangerous moves nothing: the statement is not part of identity or of the policy.
    calm = t3_claim(decision_context=_ctx(consequence="low"))
    alarming = replace(calm, statement="CATASTROPHIC failure if wrong; lives depend on this")
    assert calm.identity_digest == alarming.identity_digest
    assert derive_requirement(calm.decision_context).risk_class is derive_requirement(alarming.decision_context).risk_class


def test_a_carried_profile_must_match_its_recorded_digest() -> None:
    raw = _ctx().to_dict()
    raw["profile_digest"] = "0" * 64
    with pytest.raises(ClaimContractError, match="profile_digest"):
        DecisionContext.from_dict(raw)


# ---------------------------------------------------------------------------
# Identity: changing the policy changes the decision context
# ---------------------------------------------------------------------------


def test_changing_the_policy_changes_claim_identity_and_the_charter(registry) -> None:
    variants = [
        t3_claim(),
        t3_claim(decision_context=_ctx(consequence="low")),
        t3_claim(decision_context=_ctx(consequence="high")),
        t3_claim(decision_context=_ctx("research_exploration", consequence="low")),
        t3_claim(decision_context=DecisionContext("q", "u", "low", "low", "org", "r", _profile())),
        t3_claim(decision_context=DecisionContext("q", "u", "low", "low", "org", "r", _profile(version="4"))),
    ]
    digests = {c.identity_digest for c in variants}
    assert len(digests) == len(variants)
    charters = {plan_experiment(compile_claim(c, registry), registry).charter.digest for c in variants}
    assert len(charters) == len(variants)


def test_a_claim_with_a_context_round_trips() -> None:
    made = t3_claim(decision_context=_ctx())
    assert ScientificClaim.from_dict(json.loads(json.dumps(made.to_dict()))) == made
    assert "decision_context" not in t3_claim().to_dict()


# ---------------------------------------------------------------------------
# Risk is not evidence: a policy can withhold admissibility, never grant it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile_id", sorted(BUILTIN_PROFILES))
@pytest.mark.parametrize("make", [t3_claim, et_claim], ids=["t3", "electrothermal"])
def test_no_decision_context_ever_strengthens_a_verdict(registry, profile_id, make) -> None:
    without = assess_claim(make(), registry).to_dict()["verdict"]
    for influence, consequence in CELLS:
        with_ctx = assess_claim(make(decision_context=_ctx(profile_id, influence.value, consequence.value)), registry).to_dict()
        assert STRENGTH[with_ctx["verdict"]] <= STRENGTH[without], (influence, consequence)
        if with_ctx["verdict"] != "insufficient_evidence":
            assert with_ctx["verdict"] == without


def test_higher_risk_under_one_profile_never_yields_a_stronger_verdict(registry) -> None:
    for make in (t3_claim, et_claim):
        seen = {}
        for influence, consequence in CELLS:
            seen[(influence, consequence)] = STRENGTH[assess_claim(make(decision_context=_ctx("engineering_decision", influence.value, consequence.value)), registry).to_dict()["verdict"]]
        for a, b in itertools.product(CELLS, CELLS):
            if RANK[b[0].value] >= RANK[a[0].value] and RANK[b[1].value] >= RANK[a[1].value]:
                assert seen[b] <= seen[a]


def test_a_policy_cannot_grant_what_the_run_lacks(registry) -> None:
    # MODEL_FORM is never quantified here; no profile makes the claim supported.
    demand = UncertaintyDemand(frozenset({C.MODEL_FORM}), None, False)
    for profile_id in BUILTIN_PROFILES:
        record = assess_claim(t3_claim(uncertainty=demand, decision_context=_ctx(profile_id, "low", "low")), registry).to_dict()
        assert record["verdict"] == "insufficient_evidence"


def test_policy_findings_name_their_authoritative_record(registry) -> None:
    record = assess_claim(et_claim(decision_context=_ctx("engineering_decision", "high", "high")), registry).to_dict()
    (finding,) = [f for f in record["policy"]["findings"] if f["requirement"] == "validation_evidence"]
    assert finding["source"] == "/credibility/evidence_basis"
    assert record["basis"]["policy_satisfied"] is False
    assert any(r["source"] == "/policy/findings" for r in record["reasons"])
    assert any(r["target"] == "validation_evidence" and r["source"].startswith("policy:engineering_decision@") for r in record["repair_actions"])


def test_the_independent_route_requirement_reads_the_run(registry) -> None:
    record = assess_claim(t3_claim(decision_context=_ctx("research_exploration", "high", "high")), registry).to_dict()
    assert record["policy"]["requirement"]["policy"]["require_independent_route"] is True
    assert record["policy"]["findings"] == []  # the benchmark route was active and attained BENCHMARK_VALIDATED


def test_a_medium_risk_engineering_decision_is_supported_only_with_numerical_uq(registry) -> None:
    t3 = assess_claim(t3_claim(decision_context=_ctx()), registry).to_dict()
    assert t3["verdict"] == "supported" and t3["uncertainty"]["channels"] == {"numerical": True}
    et = assess_claim(et_claim(decision_context=_ctx()), registry).to_dict()
    assert et["verdict"] == "insufficient_evidence" and et["uncertainty"]["channels"] == {"numerical": False}


def test_a_record_whose_policy_or_context_was_edited_is_refused(registry) -> None:
    record = assess_claim(t3_claim(decision_context=_ctx()), registry).to_dict()
    verify_assessment(json.loads(json.dumps(record)), registry)
    flipped = json.loads(json.dumps(record))
    flipped["policy"]["satisfied"] = False
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(flipped, registry)
    lowered = json.loads(json.dumps(record))
    lowered["claim"]["decision_context"]["decision_consequence"] = "low"
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(lowered, registry)
    dropped = json.loads(json.dumps(record))
    del dropped["policy"]
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(dropped, registry)
