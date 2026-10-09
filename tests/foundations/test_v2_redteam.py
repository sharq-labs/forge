"""Roadmap V2 R6/R6B: Scientific Red Team (attack space, replay, independent check, trust envelope) + seeded flaw suite."""

from __future__ import annotations

import math

import pytest

from engcore.claims.redteam import (
    AttackDimension, AttackKind, AttackPlan, AttackSpace, ClaimSubject, CounterexampleClass, EnvelopeOutcome, RedTeamRefused,
    Route, RouteResult, Sense, run_red_team,
)
from engcore.claims.redteam_suite import run_suite, seeded_cases

X = AttackDimension("x", AttackKind.INPUT_PARAMETER, "spec S-1", low=0.0, high=1.0, unit="1")


def subject(*routes, threshold=1.0, claim=None):
    return ClaimSubject("c", "y", "1", Sense.AT_MOST, threshold, tuple(routes), claim or routes[0].route_id)


def route(rid, family, fidelity, fn, conv=lambda p: True):
    return Route(rid, family, fidelity, lambda p: RouteResult(fn(p), conv(p)))


def plan(space, budget=200, **kw):
    return AttackPlan(space.digest, budget, "t", **kw)


def test_there_is_no_safe_and_every_range_has_a_source():
    assert {o.value for o in EnvelopeOutcome} == {"falsified", "survived", "unknown"}
    with pytest.raises(RedTeamRefused, match="SOURCE"):
        AttackDimension("x", AttackKind.INPUT_PARAMETER, "", low=0.0, high=1.0, unit="1")
    with pytest.raises(RedTeamRefused, match="unit"):
        AttackDimension("x", AttackKind.INPUT_PARAMETER, "s", low=0.0, high=1.0)
    space = AttackSpace("c", (X,))
    env = run_red_team(subject(route("a", "f", 1, lambda p: 0.5)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.SURVIVED and "not a statement that the claim is safe" in env.statement()
    with pytest.raises(RedTeamRefused, match="another attack space"):
        run_red_team(subject(route("a", "f", 1, lambda p: 0.5)), space, AttackPlan("0" * 64, 10, "t"))


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


def test_classification_replay_refinement_and_highest_fidelity_tier():
    space = AttackSpace("c", (X,))
    viol = lambda p: 2.0 if p["x"] >= 0.99 else 0.5  # noqa: E731
    # a top-fidelity candidate confirmed by a lower-fidelity independent family is PHYSICAL
    env = run_red_team(subject(route("hi", "fe", 3, viol), route("lo", "eb", 1, viol)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.FALSIFIED and env.counterexample.cross_family_confirmed
    # a refined route of the same family removing it is an explained artifact -> SURVIVED
    env = run_red_team(subject(route("coarse", "fe", 1, viol), route("fine", "fe", 3, lambda p: 0.5)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.SURVIVED and env.candidates[0].explained
    # no independent route -> UNCONFIRMED -> UNKNOWN
    env = run_red_team(subject(route("only", "fe", 1, viol)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.UNCONFIRMED
    # highest-fidelity voters disagree -> MODEL_FORM_DEPENDENT -> UNKNOWN
    env = run_red_team(subject(route("a", "x", 2, viol), route("b", "y", 3, viol), route("c", "z", 3, lambda p: 0.5)), space, plan(space))
    assert env.outcome is EnvelopeOutcome.UNKNOWN and env.candidates[0].classification is CounterexampleClass.MODEL_FORM_DEPENDENT


def test_the_seeded_flaw_suite():
    report = run_suite()
    rows = {r["case"]: r for r in report["cases"]}
    assert len(seeded_cases()) == 13 and all(r["as_expected"] for r in report["cases"]), [r for r in report["cases"] if not r["as_expected"]]
    assert report["detection_rate"] == 1.0 and report["false_alarm_rate"] == 0.0 and report["controls_as_expected"] == 1.0
    assert report["cross_family_confirmation_rate"] == 1.0 and report["artifact_classified"]
    assert rows["unsupported_extrapolation"]["counterexample_plausibility"] == "edge"
    assert report["blind_spots_missed"] == ["flaw_outside_attack_space"]          # the documented limit, not a detection
    assert "declared plausible/edge region" in rows["flaw_outside_attack_space"]["statement"]
    assert report["evaluations_to_first_counterexample"]["min"] >= 1 and math.isfinite(report["evaluations_to_first_counterexample"]["mean"])
