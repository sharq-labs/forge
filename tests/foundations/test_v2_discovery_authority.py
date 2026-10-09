"""Roadmap V2 R1: one canonical hypothesis record and one planner authority."""

from __future__ import annotations

import hashlib

import pytest

from engcore.claims.next_experiment import ExperimentAction, planning_family
from engcore.scientific.discovery import GeneratedHypothesis, GeneratedHypothesisKind
from engcore.sria.decision import (
    ActionFamily, Hypothesis, HypothesisKind, HypothesisParameter, HypothesisPrediction, HypothesisStatus, NoveltyStatus,
    ProposalProvenance, ProposerKind, derive_hypothesis,
)
from engcore.sria.decision.discovery_adapter import generated_to_sria_hypothesis
from engcore.sria.decision.external import ExternalSuggestion, SuggestionRefused, proposal_from_suggestion

D = hashlib.sha256(b"ctx").hexdigest()


def eq_hypothesis(**kw):
    base = dict(hypothesis_id="h-eq", model_ref="law:y=a*x^b", kind=HypothesisKind.EQUATION, statement="y = a * x**b",
                predictions=(HypothesisPrediction("y", "m", "cond:grid-1"),),
                parameters=(HypothesisParameter("a", "m", 2.0, "fitted", "fit:run-1"), HypothesisParameter("b", "dimensionless")),
                proposal=ProposalProvenance(ProposerKind.ALGORITHM, "sparse-regression-v1"))
    base.update(kw)
    return Hypothesis(**base)


def test_the_legacy_record_keeps_its_bytes():
    legacy = Hypothesis(hypothesis_id="h1", model_ref="m1")
    assert legacy.to_dict() == {"schema": "sria_hypothesis/1", "hypothesis_id": "h1", "model_ref": "m1", "description": "",
                                "weight": None, "parameter_belief_ref": "", "scope_ref": "", "evidence_links": []}
    h = eq_hypothesis()
    assert Hypothesis.from_dict(h.to_dict()) == h and h.to_dict()["kind"] == "equation" and "status" not in h.to_dict()


def test_there_is_no_true_and_a_status_is_never_asserted():
    assert not {"true", "validated", "proven", "supported"} & {s.value for s in HypothesisStatus}
    assert "novel" not in {s.value for s in NoveltyStatus}
    with pytest.raises(ValueError, match="never asserted"):
        eq_hypothesis(status=HypothesisStatus.SURVIVING)
    with pytest.raises(ValueError, match="never asserted"):
        eq_hypothesis(status=HypothesisStatus.REFUTED, falsifier_refs=("f1",))  # no verdict record
    ok = eq_hypothesis(status=HypothesisStatus.SURVIVING, falsifier_refs=("f1",), status_basis=("verdict:1",))
    assert ok.status is HypothesisStatus.SURVIVING
    with pytest.raises(ValueError, match="declares its kind"):
        Hypothesis(hypothesis_id="h", model_ref="m", status=HypothesisStatus.ADMITTED_FOR_TEST)
    with pytest.raises(ValueError, match="names its source"):
        HypothesisParameter("a", "m", 1.0, "literature")


def test_an_equation_fit_never_becomes_a_mechanism():
    h = eq_hypothesis()
    with pytest.raises(ValueError, match="keeps its kind"):
        h.revise(kind=HypothesisKind.MECHANISM)
    with pytest.raises(ValueError, match="not a mechanism"):
        derive_hypothesis(h, hypothesis_id="h-mech", kind=HypothesisKind.MECHANISM, model_ref="mech:diffusion")
    mech = derive_hypothesis(h, hypothesis_id="h-mech", kind="mechanism", model_ref="mech:diffusion",
                             mechanism_basis_refs=("intervention:temperature-step",))
    assert mech.parents == ("h-eq",) and mech.status is HypothesisStatus.PROPOSED and mech.falsifier_refs == ()
    with pytest.raises(ValueError, match="no inherited"):
        derive_hypothesis(h, hypothesis_id="h2", kind="equation", model_ref="m", status="surviving")


def test_changing_the_content_resets_the_status():
    s = eq_hypothesis(status=HypothesisStatus.SURVIVING, falsifier_refs=("f1",), status_basis=("verdict:1",))
    r = s.revise(statement="y = a * x**b + c")
    assert r.status is HypothesisStatus.PROPOSED and r.status_basis == () and r.revision == 1
    assert s.revise(description="typo").status is HypothesisStatus.SURVIVING  # narrative only


def test_the_legacy_generated_hypothesis_adapts_with_its_kind_and_no_status():
    g = GeneratedHypothesis("g1", GeneratedHypothesisKind.REGIME_CHANGE, "regime at x=3", D, (D,))
    h = generated_to_sria_hypothesis(g)
    assert h.kind is HypothesisKind.REGIME_BOUNDARY and h.status is HypothesisStatus.PROPOSED
    assert h.proposal.proposer_kind is ProposerKind.LEGACY_ADAPTER


def test_external_engines_and_language_models_only_suggest():
    s = ExternalSuggestion(ProposerKind.ALGORITHM, "botorch.qEI", "0.17.2", ActionFamily.OPTIMIZE, "space:x", {"x": 1.5},
                           "max expected improvement", acquisition_value=0.31)
    p = proposal_from_suggestion(s)
    assert p.family is ActionFamily.OPTIMIZE and any(a.startswith("suggestion_digest=") for a in p.assumptions)
    assert s.digest == ExternalSuggestion(**{**s.__dict__}).digest  # content-addressed: replay reuses, never re-asks
    with pytest.raises(SuggestionRefused, match="never decides"):
        ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ActionFamily.VALIDATE, "claim:c", {"x": 1},
                           "it is clearly right", extra={"validated": True})
    with pytest.raises(SuggestionRefused, match="never decides"):
        ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ActionFamily.EXPLORE, "space:x", {"status": "surviving"}, "trust me")


def test_the_gap_advisor_speaks_the_planners_strategy_vocabulary():
    families = {f.value for f in ActionFamily}
    for action in ExperimentAction:
        fam = planning_family(action)
        assert fam is None or fam in families
    assert planning_family(ExperimentAction.RESTATE_CLAIM) is None  # a restatement is never turned into an experiment
