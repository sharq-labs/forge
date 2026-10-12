"""Roadmap V2 R1: one canonical hypothesis record and one planner authority."""

from __future__ import annotations

import hashlib

import pytest

from engcore.claims.next_experiment import ExperimentAction, planning_family
from engcore.scientific.discovery import GeneratedHypothesis, GeneratedHypothesisKind
from engcore.sria.decision import (
    ActionFamily, Hypothesis, HypothesisKind, HypothesisParameter, HypothesisPrediction, HypothesisStatus, NoveltyStatus,
    ProposalProvenance, ProposerKind, VerdictReference, derive_hypothesis,
)
from engcore.sria.decision.discovery_adapter import generated_to_sria_hypothesis
from engcore.sria.decision.external import ExternalSuggestion, SuggestionRefused, proposal_from_suggestion

D = hashlib.sha256(b"ctx").hexdigest()
V = hashlib.sha256(b"verdict").hexdigest()


def basis(h, verdict="not_refuted", falsifier="f1"):
    return (VerdictReference(falsifier, V, verdict, h.content_digest),)


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
    assert not {"true", "validated", "proven", "supported"} & {st.value for st in HypothesisStatus}
    assert "novel" not in {st.value for st in NoveltyStatus}
    with pytest.raises(ValueError, match="never asserted"):
        eq_hypothesis(status=HypothesisStatus.SURVIVING)
    h = eq_hypothesis(falsifier_refs=("f1",))
    with pytest.raises(ValueError, match="never asserted"):
        eq_hypothesis(status=HypothesisStatus.REFUTED, falsifier_refs=("f1",))  # no verdict record
    ok = eq_hypothesis(falsifier_refs=("f1",), status=HypothesisStatus.SURVIVING, status_basis=basis(h))
    assert ok.status is HypothesisStatus.SURVIVING and Hypothesis.from_dict(ok.to_dict()) == ok
    with pytest.raises(ValueError, match="every cited verdict to be not_refuted"):
        eq_hypothesis(falsifier_refs=("f1",), status=HypothesisStatus.SURVIVING, status_basis=basis(h, "inconclusive"))
    with pytest.raises(ValueError, match="not one of this hypothesis's falsifiers"):
        eq_hypothesis(falsifier_refs=("f1",), status=HypothesisStatus.SURVIVING, status_basis=basis(h, "not_refuted", "f9"))
    # a REFUTED basis may cite any falsifier of the id's lineage: dropping a falsifier never sheds its refutation
    assert eq_hypothesis(falsifier_refs=(), status=HypothesisStatus.REFUTED, status_basis=basis(h, "refuted", "f9")).status \
        is HypothesisStatus.REFUTED
    with pytest.raises(ValueError, match="other content"):  # a verdict about another revision's content
        eq_hypothesis(falsifier_refs=("f1",), statement="y = a*x", status=HypothesisStatus.SURVIVING, status_basis=basis(h))
    with pytest.raises(ValueError, match="declares its kind"):
        Hypothesis(hypothesis_id="h", model_ref="m", status=HypothesisStatus.ADMITTED_FOR_TEST)
    with pytest.raises(ValueError, match="names its source"):
        HypothesisParameter("a", "m", 1.0, "literature")
    with pytest.raises(ValueError, match="applicability record"):
        eq_hypothesis(status=HypothesisStatus.OUT_OF_SCOPE)
    with pytest.raises(ValueError, match="prior-art snapshot"):                     # review M2
        eq_hypothesis(novelty_status=NoveltyStatus.POSSIBLY_NOVEL)
    assert hash(ok)                                                                  # review L1: still hashable


def test_an_equation_fit_never_becomes_a_mechanism():
    h = eq_hypothesis()
    with pytest.raises(ValueError, match="keeps its kind"):
        h.revise(kind=HypothesisKind.MECHANISM)
    with pytest.raises(ValueError, match="keeps its parents"):
        derive_hypothesis(h, hypothesis_id="h2", kind="model_structure", model_ref="m").revise(parents=())
    with pytest.raises(ValueError, match="not a mechanism"):
        derive_hypothesis(h, hypothesis_id="h-mech", kind=HypothesisKind.MECHANISM, model_ref="mech:diffusion")
    # two hops: EQUATION -> MODEL_STRUCTURE -> MECHANISM still needs a basis beyond the fit (review M1)
    mid = derive_hypothesis(h, hypothesis_id="h-struct", kind="model_structure", model_ref="struct:1")
    with pytest.raises(ValueError, match="not a mechanism"):
        derive_hypothesis(mid, hypothesis_id="h-mech2", kind="mechanism", model_ref="mech:2")
    with pytest.raises(ValueError, match="not a mechanism"):  # direct construction does not bypass it
        Hypothesis(hypothesis_id="h-direct", model_ref="m", kind="mechanism", parents=("h-eq",))
    with pytest.raises(ValueError, match="cannot be the fit itself"):
        derive_hypothesis(h, hypothesis_id="h-m3", kind="mechanism", model_ref="m", mechanism_basis_refs=("fit:run-1",),
                          parameters=h.parameters)
    mech = derive_hypothesis(h, hypothesis_id="h-mech", kind="mechanism", model_ref="mech:diffusion",
                             mechanism_basis_refs=("intervention:temperature-step",))
    assert mech.parents == ("h-eq",) and mech.status is HypothesisStatus.PROPOSED and mech.falsifier_refs == ()
    with pytest.raises(ValueError, match="no inherited"):
        derive_hypothesis(h, hypothesis_id="h2", kind="equation", model_ref="m", status="surviving")


def test_changing_the_content_resets_the_status():
    h = eq_hypothesis(falsifier_refs=("f1",))
    s = h.revise(status=HypothesisStatus.SURVIVING, status_basis=basis(h))
    r = s.revise(statement="y = a * x**b + c")
    assert r.status is HypothesisStatus.PROPOSED and r.status_basis == () and r.revision == 2
    assert s.revise(description="typo").status is HypothesisStatus.SURVIVING  # narrative only
    assert s.revise(model_ref="other:model").status is HypothesisStatus.PROPOSED  # review H6: model_ref is content
    with pytest.raises(ValueError, match="cannot arrive together"):
        s.revise(statement="new", status=HypothesisStatus.SURVIVING, status_basis=s.status_basis)


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
    with pytest.raises(SuggestionRefused, match="never decides"):  # nested and synonym keys (review L5)
        ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", ActionFamily.EXPLORE, "space:x", {"x": 1},
                           "r", extra={"meta": {"validation_level": "experimental"}})
    with pytest.raises(SuggestionRefused, match="finite"):
        ExternalSuggestion(ProposerKind.ALGORITHM, "bo", "1", ActionFamily.OPTIMIZE, "space:x", {"x": 1}, "r",
                           acquisition_value=float("inf"))


def test_the_gap_advisor_speaks_the_planners_strategy_vocabulary():
    families = {f.value for f in ActionFamily}
    for action in ExperimentAction:
        fam = planning_family(action)
        assert fam is None or fam in families
    assert planning_family(ExperimentAction.RESTATE_CLAIM) is None  # a restatement is never turned into an experiment
    # applicability is not validation, and solver agreement is verification (review M6)
    assert planning_family(ExperimentAction.ESTABLISH_APPLICABILITY) != "validate"
    assert planning_family(ExperimentAction.RUN_INDEPENDENT_ROUTE) != "validate"
