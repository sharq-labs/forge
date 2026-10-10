"""Roadmap V2 R6/R6B: Scientific Red Team (attack space, replay, independent check, trust envelope) + seeded flaw suite
(incl. the checkpoint-4 hostile review)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from engcore.claims.redteam import (
    TRUST_ENVELOPE_SCHEMA, AttackDimension, AttackKind, AttackPlan, AttackSpace, ClaimSubject, CounterexampleClass, EnvelopeOutcome,
    RedTeamRefused, Route, RouteResult, Sense, run_red_team,
)
from engcore.claims.redteam_suite import run_suite, seeded_cases

X = AttackDimension("x", AttackKind.INPUT_PARAMETER, "spec S-1", low=0.0, high=1.0, unit="1")


def subject(*routes, threshold=1.0, claim=None):
    return ClaimSubject("c", "y", "1", Sense.AT_MOST, threshold, tuple(routes), claim or routes[0].route_id)


def route(rid, family, fidelity, fn, conv=lambda p: True):
    return Route(rid, family, fidelity, lambda p: RouteResult(fn(p), conv(p)))


def plan(space, budget=400, **kw):
    return AttackPlan(space.digest, budget, "t", **kw)


VIOL = lambda p: 2.0 if p["x"] >= 0.99 else 0.5  # noqa: E731
HOLD = lambda p: 0.5  # noqa: E731


def test_there_is_no_safe_every_range_has_a_source_and_the_envelope_binds_its_inputs():
    assert {o.value for o in EnvelopeOutcome} == {"falsified", "survived", "unknown"}
    assert "physical" not in {c.value for c in CounterexampleClass}           # review H6: agreement of models, not physics
    with pytest.raises(RedTeamRefused, match="SOURCE"):
        AttackDimension("x", AttackKind.INPUT_PARAMETER, "", low=0.0, high=1.0, unit="1")
    with pytest.raises(RedTeamRefused, match="unit"):
        AttackDimension("x", AttackKind.INPUT_PARAMETER, "s", low=0.0, high=1.0)
    space = AttackSpace("c", (X,))
    s = subject(route("a", "f", 1, HOLD), route("b", "g", 2, HOLD))
    env = run_red_team(s, space, plan(space))
    d = env.to_dict()
    assert env.outcome is EnvelopeOutcome.SURVIVED and "not a statement that the claim is safe" in env.statement()
    assert d["schema"] == TRUST_ENVELOPE_SCHEMA and d["plan_digest"] and d["subject_digest"]          # review M4
    assert d["attacked_routes"] == ["a", "b"] and "routes ['a', 'b']" in env.statement()             # review H5
    assert "seeded interior" in env.method and "seed 't'" in env.method                              # review M3
    tighter = run_red_team(dataclasses.replace(s, threshold=0.6), space, plan(space))
    assert tighter.subject_digest != env.subject_digest
    assert run_red_team(s, space, plan(space)).to_dict() == d                                         # deterministic
    with pytest.raises(RedTeamRefused, match="another attack space"):
        run_red_team(s, space, AttackPlan("0" * 64, 10, "t"))


def test_a_non_finite_value_never_means_the_claim_holds():
    space = AttackSpace("c", (X,))
    env = run_red_team(subject(route("a", "f", 1, lambda p: float("nan"))), space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and "converge" in env.reason


def test_budget_exhaustion_is_unknown_even_with_only_implausible_candidates():
    wide = AttackDimension("x", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1", edge_high=1.2)
    space = AttackSpace("c", (wide,))
    s = subject(route("a", "f", 1, lambda p: 5.0 if p["x"] > 1.2 else 0.5))
    full = run_red_team(s, space, plan(space, probe_implausible=True))
    assert full.outcome is EnvelopeOutcome.SURVIVED and {c.classification for c in full.candidates} == {CounterexampleClass.OUTSIDE_PLAUSIBILITY}
    short = run_red_team(s, space, plan(space, budget=3, probe_implausible=True))
    assert short.outcome is EnvelopeOutcome.UNKNOWN and "budget ran out" in short.reason


def test_confirmation_needs_another_family_and_no_converged_dissent():
    space = AttackSpace("c", (X,))
    # review H1: same-family refinement agreeing is a convergence check, not confirmation
    env = run_red_team(subject(route("claim", "z", 1, HOLD), route("coarse", "fe", 1, VIOL), route("fine", "fe", 3, VIOL)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.UNCONFIRMED
    # cross-family agreement (the claim's own route never votes) -> confirmed
    env = run_red_team(subject(route("claim", "eb_ss", 1, HOLD), route("hi", "fe", 3, VIOL), route("lo", "eb", 1, VIOL)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.FALSIFIED and env.counterexample.cross_family_confirmed
    assert "not a physical measurement" in env.statement()
    # review H2: lower-fidelity independent dissent counts, whatever fidelity the candidate declares
    env = run_red_team(subject(route("claim", "q", 1, HOLD), route("a", "a", 9, VIOL), route("b", "b", 1, VIOL), route("c", "c", 2, HOLD)),
                       space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and any(c.classification is CounterexampleClass.MODEL_FORM_DEPENDENT for c in env.candidates)
    # a refined route of the same family removing it, with no other family reproducing it: explained artifact
    env = run_red_team(subject(route("coarse", "fe", 1, VIOL), route("fine", "fe", 3, HOLD)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.SURVIVED and env.candidates[0].explained
    # review H4: ... but not when another family confirms it
    env = run_red_team(subject(route("coarse", "fe", 1, VIOL), route("fine", "fe", 2, HOLD), route("indep", "other", 5, VIOL)), space,
                       plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.MODEL_FORM_DEPENDENT


def test_unconverged_or_unevaluated_independent_routes_never_strengthen_the_verdict():
    space = AttackSpace("c", (X,))
    env = run_red_team(subject(route("claim", "q", 1, HOLD), route("a", "a", 1, VIOL), route("b", "b", 1, VIOL),
                               route("c", "c", 5, HOLD, conv=lambda p: False)), space, plan(space))           # review H3
    assert env.outcome is EnvelopeOutcome.UNKNOWN
    env = run_red_team(subject(route("only", "fe", 1, VIOL)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.UNCONFIRMED


def test_without_a_route_dimension_every_declared_route_is_attacked():
    case = next(c for c in seeded_cases() if c.name == "wrong_bc")
    no_route_dim = AttackSpace(case.space.claim_ref, tuple(d for d in case.space.dimensions if not d.choices))
    env = run_red_team(case.subject, no_route_dim, AttackPlan(no_route_dim.digest, 400, "t"))         # review H5
    assert env.outcome is EnvelopeOutcome.FALSIFIED


def test_the_edge_band_interior_is_attacked_and_points_are_distinct():
    band = AttackDimension("x", AttackKind.INPUT_PARAMETER, "spec", low=0.0, high=1.0, unit="1", edge_high=2.0)
    space = AttackSpace("c", (band,))
    inner = lambda p: 2.0 if 1.2 < p["x"] < 1.8 else 0.5  # noqa: E731
    env = run_red_team(subject(route("a", "f", 1, inner), route("b", "g", 2, inner)), space, plan(space, edge_interior_points=8))
    assert env.outcome is EnvelopeOutcome.FALSIFIED and env.counterexample.plausibility.value == "edge"    # review M1
    only_routes = AttackSpace("c", (AttackDimension("r", AttackKind.MODEL_FORM, "note", choices=("a", "b")),))
    env = run_red_team(subject(route("a", "f", 1, HOLD), route("b", "g", 1, HOLD)), only_routes, plan(only_routes))
    assert env.points_covered == 2                                                                     # review M2: deduplicated


def test_the_seeded_flaw_suite():
    report = run_suite()
    rows = {r["case"]: r for r in report["cases"]}
    assert len(seeded_cases()) == 14 and all(r["as_expected"] for r in report["cases"]), [r for r in report["cases"] if not r["as_expected"]]
    assert report["detection_rate"] == 1.0 and report["false_alarm_rate"] == 0.0 and report["controls_as_expected"] == 1.0
    assert report["cross_family_confirmation_rate"] == 1.0 and report["artifact_classified"]
    assert rows["unsupported_extrapolation"]["counterexample_plausibility"] == "edge"
    assert report["blind_spots_missed"] == ["flaw_outside_attack_space"]
    assert "over {" in rows["flaw_outside_attack_space"]["statement"]
    case = next(c for c in seeded_cases() if c.name == "interior_only_violation")                      # review M6
    env = case.run()
    assert 3500.0 < env.counterexample.point["F"] < 5000.0 and env.counterexample.point["F"] not in (1000.0, 4500.0, 8000.0)
    flaky = next(c for c in seeded_cases() if c.name == "flaky_trap")
    assert flaky.run().outcome is flaky.run().outcome is EnvelopeOutcome.UNKNOWN                        # deterministic
    assert math.isfinite(report["evaluations_to_confirmed_counterexample"]["mean"])


def test_confirmation_review_rules():
    space = AttackSpace("c", (X,))
    # M-R3: with a route dimension the claim's own route must be attacked
    only_b = AttackSpace("c", (X, AttackDimension("r", AttackKind.MODEL_FORM, "note", choices=("b",))))
    with pytest.raises(RedTeamRefused, match="claim's own route"):
        run_red_team(subject(route("a", "f", 1, VIOL), route("b", "g", 1, HOLD)), only_b, plan(only_b))
    # M-R1: an explanation by an UNATTACKED refined route does not dismiss the violation
    coarse_only = AttackSpace("c", (X, AttackDimension("r", AttackKind.DISCRETIZATION, "mesh", choices=("coarse",))))
    env = run_red_team(subject(route("coarse", "fe", 1, VIOL), route("fake", "fe", 99, HOLD)), coarse_only, plan(coarse_only))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.UNCONFIRMED
    # ... and an attacked explanation is disclosed in the SURVIVED statement
    env = run_red_team(subject(route("coarse", "fe", 1, VIOL), route("fine", "fe", 3, HOLD)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.SURVIVED and "dismissed as numerical artifacts" in env.statement()
    # M-R2: the replay tolerance is part of the plan and its digest, and bounded
    assert AttackPlan(space.digest, 10, "t").digest != AttackPlan(space.digest, 10, "t", replay_tol=1e-3).digest
    with pytest.raises(RedTeamRefused, match="replay tolerance"):
        AttackPlan(space.digest, 10, "t", replay_tol=1e9)
    # LOW: a NaN threshold can never be violated; duplicate choices; family labels normalized
    with pytest.raises(RedTeamRefused, match="finite"):
        ClaimSubject("c", "y", "1", Sense.AT_MOST, float("nan"), (route("a", "f", 1, HOLD),), "a")
    with pytest.raises(RedTeamRefused, match="distinct"):
        AttackDimension("r", AttackKind.MODEL_FORM, "note", choices=("a", "a"))
    assert route("a", " FE ", 1, HOLD).family == "fe"
