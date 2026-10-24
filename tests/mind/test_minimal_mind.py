"""BR-MIND-01 Stage 1: functional and adversarial tests of the Minimal Mind (engcore.mind.minimal).

Synthetic worlds here are plain functions with seeded multiplicative noise: no escrow, no Blindfold generator, so each
test controls exactly the scientific situation it names.  Benchmark-level tests (presentation, isolation, hidden
answers) are in tests/genesis_lite_mind.
"""

from __future__ import annotations

import ast
import math
import pathlib
import random

import pytest

from engcore.claims.falsification import verify_status
from engcore.mind.minimal import (
    FULL, NO_ADAPTIVE_SELECTION, NO_BELIEF_UPDATE, NO_FALSIFIER, ConclusionKind, ExperimentalProblem, HypothesisCompetition,
    InputSpec, ObservationRefused, StructureRefused, replay, run_mind, verify_chain,
)
from engcore.mind.minimal import experiments as ex
from engcore.mind.minimal import falsifier as fz
from engcore.mind.minimal.structures import Structure, hypothesis_for, log_prior
from engcore.mind.minimal.trace import digest
from engcore.sria.decision import ActionFamily, HypothesisStatus, ProposerKind
from engcore.sria.decision.external import ExternalSuggestion, SuggestionRefused

ROOT = pathlib.Path(__file__).resolve().parents[2]


class World:
    """y = law(x, u) * exp(N(0, noise)); u = covariate(x, rng) observed passively; the budget is enforced."""

    def __init__(self, law, *, noise=0.01, budget=30, covariate=None, seed=0):
        self.law, self.noise, self.budget, self.covariate = law, noise, budget, covariate
        self.rng = random.Random(seed)
        self.calls = 0

    def __call__(self, settings, query_ref):
        if self.calls >= self.budget:
            raise ObservationRefused("budget", budget=True)
        self.calls += 1
        x = dict(settings)
        u = self.covariate(x, self.rng) if self.covariate else math.exp(self.rng.gauss(0, 0.4))
        return {**x, "u": u, "y": self.law(x, u) * math.exp(self.rng.gauss(0, self.noise))}


def problem(*, names=("a", "b"), budget=30, region=None, out="y", cov="u", ranges=None):
    ranges = ranges or [(0.5, 5.0), (1.0, 8.0), (0.2, 3.0)][: len(names)]
    return ExperimentalProblem(problem_id="t", inputs=tuple(InputSpec(n, lo, hi) for n, (lo, hi) in zip(names, ranges)),
                               covariates=(cov,), observable=out, observable_unit="1", budget=budget, query_cost=1.0,
                               region=region or {})


# ---------------------------------------------------------------------------------------------- 1, 3: rivals survive
def test_rivals_survive_when_the_evidence_cannot_distinguish_them_and_evidence_for_one_deletes_no_other():
    # the passive covariate is a copy of input a: {a} and {u} make the same predictions at every admissible setting
    w = World(lambda x, u: 2.0 * x["a"] ** 1.37, covariate=lambda x, rng: x["a"] * math.exp(rng.gauss(0, 1e-4)), noise=0.01)
    run = run_mind(problem(), w, config=FULL)
    comp = run.competition
    a_id = Structure(("a",)).hypothesis_id(comp.problem)
    u_id = Structure(("u",)).hypothesis_id(comp.problem)
    weights = comp.weights()
    assert weights[a_id] > 0.05 and weights[u_id] > 0.05, weights
    assert comp.rivals[a_id].hypothesis.status is not HypothesisStatus.REFUTED
    assert comp.rivals[u_id].hypothesis.status is not HypothesisStatus.REFUTED
    # the conclusion prefers the intervened input over its passive copy -- without deleting the copy's hypothesis
    assert run.conclusion.kind is ConclusionKind.LAW
    assert set(run.conclusion.laws[0].linear) == {"a"}
    view_ids = {h["hypothesis_id"] for h in run.trace["final_state"]["hypotheses"]}
    assert {a_id, u_id} <= view_ids and len(view_ids) == len(comp.rivals)
    # every rival ever entertained is still in the state, with a weight or an explicit UNFIT/REFUTED reason
    assert all(r.weight is not None or r.fitted is None or not r.fitted.fit_ok for r in comp.rivals.values())


# ---------------------------------------------------------------------------- 2: discrimination beats a replicate
def _diagonal_competition():
    """Evidence only on the diagonal a == b: {a} and {b} agree on every observed point and disagree off it."""
    prob = problem(ranges=[(1.0, 8.0), (1.0, 8.0)])
    comp = HypothesisCompetition(prob, seed=0, authority_key=b"k" * 32, campaign_id="diag", falsify=True)
    rng = random.Random(1)
    for i, t in enumerate([1.0, 1.3, 1.7, 2.2, 2.9, 3.6, 4.4, 5.3, 6.4, 7.7]):
        y = 3.0 * t ** 1.5 * math.exp(rng.gauss(0, 0.01))
        comp.admit(f"q{i}", {"a": t, "b": t}, {"a": t, "b": t, "u": math.exp(rng.gauss(0, 0.4)), "y": y})
    return prob, comp


def test_a_discriminating_experiment_is_preferred_over_a_redundant_replicate():
    prob, comp = _diagonal_competition()
    a_id, b_id = Structure(("a",)).hypothesis_id(prob), Structure(("b",)).hypothesis_id(prob)
    w = comp.weights()
    assert w[a_id] > 0.2 and w[b_id] > 0.2                       # the diagonal cannot tell them apart
    replicate = ex.candidate({"a": 4.4, "b": 4.4}, ActionFamily.REDUCE_UNCERTAINTY, "replicate", "noise", "redundant")
    off = ex.candidate({"a": 8.0, "b": 1.0}, ActionFamily.EXPLORE, "manual", "design", "off the diagonal")
    sel = ex.select(prob, comp, [replicate, off], w, "test")
    assert sel.selected.candidate_id == off.candidate_id
    by = {s.candidate.candidate_id: s for s in sel.scored}
    disc = lambda s: s.component("expected_discrimination").value  # noqa: E731
    assert disc(by[off.candidate_id]) > 100 * max(disc(by[replicate.candidate_id]), 1e-12)
    # the falsifier role proposes an off-diagonal test for the strong hypotheses
    props = fz.propose(prob, comp, w, [replicate, off])
    assert props and all(p.candidate.settings == off.settings for p in props)
    assert all(p.candidate.family is ActionFamily.DISCRIMINATE for p in props)


def test_a_replicate_is_never_a_falsifier_test_because_its_outcome_could_be_read_off_the_data():
    prob, comp = _diagonal_competition()
    w = comp.weights()
    hid = max(w, key=w.get)
    preds = comp.predictions({"a": 4.4, "b": 4.4}, "rep", [hid])
    sealed = comp.seal("rep", {"a": 4.4, "b": 4.4}, preds, {hid: w[hid]})
    assert sealed and not sealed[0]["sealed"] and "already released" in sealed[0]["reason"]


# ----------------------------------------------------------------- 4: refutation through the existing authority
def test_a_strong_hypothesis_is_refuted_by_its_sealed_falsifier_when_a_discriminating_result_arrives():
    """H = {a} is strong while b has never varied; a falsifier sealed on H at a new b refutes it through the registry."""
    prob = problem()
    comp = HypothesisCompetition(prob, seed=0, authority_key=b"k" * 32, campaign_id="refute", falsify=True)
    rng = random.Random(2)
    law = lambda a, b: 1.5 * a ** 2.0 * b ** -1.3  # noqa: E731
    pts = [0.5, 0.7, 1.0, 1.4, 2.0, 2.8, 4.0, 5.0, 2.0, 4.0]          # b fixed at 2.0, two replicates
    for i, a in enumerate(pts):
        comp.admit(f"q{i}", {"a": a, "b": 2.0}, {"a": a, "b": 2.0, "u": math.exp(rng.gauss(0, .4)),
                                                  "y": law(a, 2.0) * math.exp(rng.gauss(0, .005))})
    h_id = Structure(("a",)).hypothesis_id(prob)
    w = comp.weights()
    assert w[h_id] > 0.3 and comp.noise.upper95 is not None
    test = {"a": 2.0, "b": 8.0}
    preds = comp.predictions(test, "t", [h_id])
    sealed = comp.seal("t", test, preds, {h_id: w[h_id]})
    assert sealed[0]["sealed"], sealed
    comp.admit("t", test, {**test, "u": 1.0, "y": law(2.0, 8.0)})
    h = comp.rivals[h_id].hypothesis
    assert h.status is HypothesisStatus.REFUTED and any(b.verdict == "refuted" for b in h.status_basis)
    assert verify_status(h, comp.registry, anchor=comp.anchor) == []
    assert comp.rivals[h_id].weight == 0.0 and h_id in comp.view(budget_spent=11)["contradictions"]


def _curved(x, u):
    return 1.5 * x["a"] ** 1.5 * math.exp(0.1 * math.log(x["a"]) ** 2) * x["b"] ** -0.8


def test_the_loop_refutes_the_early_leader_and_keeps_the_structure_the_evidence_supports():
    """Early on the power law in (a, b) leads; the falsifier role's tests at discriminating settings refute it."""
    w = World(_curved, noise=0.005, budget=40)
    run = run_mind(problem(), w, config=FULL)
    comp = run.competition
    refuted = [h for h, r in comp.rivals.items() if r.hypothesis.status is HypothesisStatus.REFUTED]
    monomial = Structure(("a", "b")).hypothesis_id(comp.problem)
    assert monomial in refuted, "rivals contradicted at discriminating settings are refuted by the registry"
    for hid in refuted:
        h = comp.rivals[hid].hypothesis
        assert h.status_basis and all(b.verdict == "refuted" for b in h.status_basis if b.verdict == "refuted")
        assert verify_status(h, comp.registry, anchor=comp.anchor) == []
        assert comp.rivals[hid].weight == 0.0                         # no standing, but still a member
    curved = Structure(("a", "b"), ("a", "b")).hypothesis_id(comp.problem)
    assert curved not in refuted
    assert run.conclusion.kind is ConclusionKind.LAW and run.conclusion.laws[0].hypothesis_id == curved
    law = run.conclusion.laws[0]
    assert abs(law.quadratic["a"] - 0.1) < 0.02 and abs(law.quadratic["b"]) < 0.02


def test_a_status_label_that_the_expected_registry_did_not_issue_never_verifies():
    from engcore.sria.decision import VerdictReference

    comp = run_mind(problem(), World(_curved, noise=0.005, budget=40), config=FULL).competition
    refuted = [r.hypothesis for r in comp.rivals.values() if r.hypothesis.status is HypothesisStatus.REFUTED]
    assert refuted
    other = HypothesisCompetition(comp.problem, seed=0, authority_key=b"x" * 32, campaign_id="other", falsify=True)
    assert verify_status(refuted[0], other.registry, anchor=other.anchor)          # a verdict from elsewhere
    survivor = comp.rivals[Structure(("a", "b"), ("a", "b")).hypothesis_id(comp.problem)].hypothesis
    fake = VerdictReference("made-up@v1", "f" * 64, "refuted", survivor.content_digest)
    forged = survivor.revise(status=HypothesisStatus.REFUTED, status_basis=(fake,))
    assert verify_status(forged, comp.registry, anchor=comp.anchor)                 # a label the chain does not hold


# ------------------------------------------------------------------------------- 5, 7: names steer nothing
def _run_named(names, out, cov):
    law = lambda x, u: 0.7 * x[names[0]] ** 1.37 * x[names[1]] ** -0.61  # noqa: E731

    class Renamed(World):
        def __call__(self, settings, query_ref):
            o = super().__call__(settings, query_ref)
            return {**{k: v for k, v in o.items() if k not in ("u", "y")}, cov: o["u"], out: o["y"]}

    prob = ExperimentalProblem(problem_id=f"p-{names[0]}", inputs=(InputSpec(names[0], 0.5, 5.0), InputSpec(names[1], 1.0, 8.0)),
                               covariates=(cov,), observable=out, observable_unit="1", budget=30, query_cost=1.0, region={})
    return run_mind(prob, Renamed(law, noise=0.01, seed=3), config=FULL)


def test_renaming_and_trap_vocabulary_leave_the_reasoning_unchanged():
    anon = _run_named(("q1", "q2"), "y", "u1")
    trap = _run_named(("body_mass", "ambient_temperature"), "metabolic_rate", "season_index")
    reordered = _run_named(("v812", "v133"), "v400", "v999")
    for other in (trap, reordered):
        assert other.conclusion.kind is anon.conclusion.kind is ConclusionKind.LAW
        assert [s["selection"]["selected"]["settings"] and len(s["selection"]["selected"]["settings"]) for s in other.trace["steps"]] \
            == [len(s["selection"]["selected"]["settings"]) for s in anon.trace["steps"]]
        role = lambda run: [n.name for n in run.competition.problem.inputs]  # noqa: E731 - presentation order
        assert [[s["execution"]["settings"][n] for n in role(other)] for s in other.trace["steps"]] == \
            [[s["execution"]["settings"][n] for n in role(anon)] for s in anon.trace["steps"]]
        a, b = anon.conclusion.laws[0], other.conclusion.laws[0]
        assert sorted(a.linear.values()) == pytest.approx(sorted(b.linear.values()), abs=1e-9)
    # the textbook exponent for body mass is 0.75; the Mind reports the evidence's exponent, not the vocabulary's
    assert abs(trap.conclusion.laws[0].linear["body_mass"] - 1.37) < 0.05


# --------------------------------------------------------------------------------------- 8, 9: refusals
def test_a_world_with_no_dependence_is_never_given_a_law():
    for seed in range(6):
        w = World(lambda x, u: 1.0, noise=0.75, budget=30, seed=seed)
        con = run_mind(problem(), w, seed=seed).conclusion
        assert con.kind in (ConclusionKind.NO_DEPENDENCE, ConclusionKind.INSUFFICIENT_EVIDENCE), con


def test_insufficient_evidence_does_not_become_certainty():
    for seed in range(4):
        w = World(lambda x, u: 2.0 * x["a"] ** 0.9 * x["b"] ** -0.4, noise=0.8, budget=12, seed=seed)
        con = run_mind(problem(), w, seed=seed).conclusion
        assert con.kind not in (ConclusionKind.LAW, ConclusionKind.INDISTINGUISHABLE), con


def test_extrapolation_beyond_the_box_is_not_claimed_as_a_law():
    w = World(lambda x, u: 2.0 * x["a"] ** 1.3 * x["b"] ** -0.7, noise=0.005, budget=40)
    prob = problem(region={"a": (6.0, 20.0)})
    con = run_mind(prob, w).conclusion
    assert con.kind in (ConclusionKind.INSUFFICIENT_EVIDENCE, ConclusionKind.INDISTINGUISHABLE)


def test_an_association_with_an_unsettable_covariate_is_not_promoted_to_a_mechanism():
    def cov(x, rng):
        h = math.exp(rng.gauss(0, 0.4))
        cov.last = h
        return h * math.exp(rng.gauss(0, 0.01))
    w = World(lambda x, u: 2.0 * x["a"] ** 1.3 * cov.last ** 1.2, covariate=cov, noise=0.01, budget=30)
    con = run_mind(problem(), w).conclusion
    assert con.kind is ConclusionKind.UNIDENTIFIABLE_PASSIVE_ASSOCIATION
    assert "no admissible experiment sets it" in con.reason


def test_a_non_positive_observable_makes_the_log_model_inapplicable():
    w = World(lambda x, u: -1.0, noise=0.01, budget=12)
    con = run_mind(problem(), w).conclusion
    assert con.kind is ConclusionKind.REFUSED


# ------------------------------------------------------------------------ 10: pre-result seals and replay
def test_every_prediction_is_sealed_before_its_result_and_the_trace_replays_exactly():
    w = World(lambda x, u: 1.5 * x["a"] ** 2.0 * x["b"] ** -1.3, noise=0.01, budget=24)
    prob = problem()
    run = run_mind(prob, w, config=FULL)
    steps = run.trace["steps"]
    assert verify_chain(steps) == []
    sealed_any = False
    for s in steps:
        assert s["prediction_seal_digest"] == digest(s["pre_result"])
        for f in s["pre_result"]["falsifiers"]:
            if f.get("sealed"):
                sealed_any = True
                assert s["evidence"]["exposure_sequence"] > 0
    assert sealed_any
    assert replay(run.trace, prob)["status"] == "VERIFIED"


def test_a_tampered_trace_does_not_replay():
    w = World(lambda x, u: 1.5 * x["a"] ** 2.0 * x["b"] ** -1.3, noise=0.01, budget=20)
    prob = problem()
    trace = run_mind(prob, w).trace
    bad = dict(trace)
    bad["observations"] = [dict(o) for o in trace["observations"]]
    bad["observations"][12]["y"] *= 1.5
    assert replay(bad, prob)["status"] == "DIVERGED"
    broken = dict(trace)
    broken["steps"] = [dict(s) for s in trace["steps"]]
    broken["steps"][3]["policy"] = "edited"
    assert replay(broken, prob)["status"] == "CHAIN_BROKEN"


# --------------------------------------------------------------------------------------- 11: ablations
def test_each_ablation_removes_exactly_one_capability():
    flags = [(c.adaptive_selection, c.belief_update, c.falsifier) for c in (FULL, NO_ADAPTIVE_SELECTION, NO_BELIEF_UPDATE, NO_FALSIFIER)]
    assert flags == [(True, True, True), (False, True, True), (True, False, True), (True, True, False)]
    w = World(lambda x, u: 1.5 * x["a"] ** 2.0 * x["b"] ** -1.3, noise=0.01, budget=20)
    fixed = run_mind(problem(), w, config=NO_ADAPTIVE_SELECTION).trace
    assert {s["policy"] for s in fixed["steps"]} <= {"initial_design", "fixed_space_filling"}
    w = World(lambda x, u: 1.5 * x["a"] ** 2.0 * x["b"] ** -1.3, noise=0.01, budget=20)
    nof = run_mind(problem(), w, config=NO_FALSIFIER)
    assert not nof.competition.registry.entries or all(e.kind == "registered" for e in nof.competition.registry.entries)


# ------------------------------------------------------------------------- 12: proposals carry no authority
@pytest.mark.parametrize("payload", [
    {"linear": ["a"], "status": "surviving"}, {"linear": ["a"], "confidence": 0.9}, {"linear": ["a"], "weight": 1.0},
    {"linear": ["a"], "posterior": 0.99}, {"linear": ["a"], "uncertainty": 0.0}, {"linear": ["a"], "threshold": 0.5},
    {"linear": ["a"], "outcome": "law_pass"}, {"linear": ["zz"]}, {"linear": ["u"], "quadratic": ["u"]},
])
def test_an_ai_proposal_cannot_carry_authority_or_belief(payload):
    comp = HypothesisCompetition(problem(), seed=0, authority_key=b"k" * 32, campaign_id="ai", falsify=True)
    with pytest.raises(StructureRefused):
        comp.ingest_proposal(payload, proposer_kind=ProposerKind.LANGUAGE_MODEL, proposer_id="llm-x")


def test_an_admitted_ai_proposal_starts_proposed_at_the_declared_prior():
    prob = problem(names=("a", "b", "c"))
    comp = HypothesisCompetition(prob, seed=0, authority_key=b"k" * 32, campaign_id="ai2", falsify=True)
    hid = comp.ingest_proposal({"linear": ["a", "c"], "rationale": "I am very sure"}, proposer_kind="language_model",
                               proposer_id="llm-x")
    r = comp.rivals[hid]
    assert r.hypothesis.status is HypothesisStatus.PROPOSED and not r.hypothesis.status_basis
    assert r.log_prior == log_prior(Structure(("a", "c")), prob)
    assert r.hypothesis.proposal.proposer_kind is not ProposerKind.LANGUAGE_MODEL      # the enumerated record is kept
    assert comp.proposals[-1]["provenance"]["proposer_kind"] == "language_model"
    novel = comp.ingest_proposal({"linear": ["a", "b"], "quadratic": ["a"]}, proposer_kind="language_model", proposer_id="llm-x")
    n = comp.rivals[novel]
    assert n.hypothesis.status is HypothesisStatus.PROPOSED and n.hypothesis.proposal.proposer_kind is ProposerKind.LANGUAGE_MODEL
    assert n.log_prior == log_prior(Structure(("a", "b"), ("a",)), prob)


def test_an_external_suggestion_is_a_candidate_whose_own_number_is_ignored():
    with pytest.raises(SuggestionRefused):
        ExternalSuggestion("language_model", "llm", "1", ActionFamily.DISCRIMINATE, "h", {"a": 1.0, "status": "refuted"}, "x")
    prob, comp = _diagonal_competition()
    w = comp.weights()
    lo = ExternalSuggestion("language_model", "llm", "1", ActionFamily.DISCRIMINATE, "h", {"a": 4.4, "b": 4.4}, "try", 1e9)
    hi = ExternalSuggestion("language_model", "llm", "1", ActionFamily.DISCRIMINATE, "h", {"a": 8.0, "b": 1.0}, "try", 0.0)
    sel = ex.select(prob, comp, [ex.from_suggestion(lo), ex.from_suggestion(hi)], w, "test")
    assert sel.selected.settings == {"a": 8.0, "b": 1.0}


# ------------------------------------------------------------------------------- the boundary, statically
FORBIDDEN = ("engcore.blindfold", "benchmarks", "engcore.mcp", "anthropic", "openai")


def test_the_mind_imports_no_benchmark_world_no_transport_and_no_language_model():
    for path in sorted((ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py")):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for n in names:
                assert not any(n.startswith(f) for f in FORBIDDEN), f"{path.name} imports {n}"
                assert "blindfold" not in n and "mcp" not in n, f"{path.name} imports {n}"
