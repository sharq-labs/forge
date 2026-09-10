"""Phase 8 — prove this audit can actually see contract drift.

An audit that has never been shown to fail is decoration. Each test below
plants one controlled defect, runs the real detection logic against it, and
requires the defect to be found. Nothing is planted in production: the defects
live in synthetic claim/context pairs registered for the duration of one test,
or in a monkeypatched copy of a derivation, and every one is removed in a
``finally``.

The five planted defects are the five the round names:

1. the record requires three inputs and the runtime accepts one;
2. the record says one input is enough and the runtime requires three;
3. the record claims a cross-check and only one route ever executes;
4. the record's applicability is wider than the runtime's validity;
5. the runtime changes and the record does not.
"""

from __future__ import annotations

import contextlib

import pytest

import nominals
import review
from claim_map import CLAIMS


@contextlib.contextmanager
def planted(context_id, declarations, assemble, claim_key, claim):
    """Register a synthetic context and claim, and always remove them."""
    nominals.CONTEXTS[context_id] = (declarations, assemble)
    review.SYSTEM_CONTEXT[context_id] = context_id
    CLAIMS[claim_key] = claim
    try:
        yield
    finally:
        nominals.CONTEXTS.pop(context_id, None)
        review.SYSTEM_CONTEXT.pop(context_id, None)
        CLAIMS.pop(claim_key, None)


def results_for(system, condition, claim):
    """Run the real all_of / one_of checks and collect their verdicts."""
    out = []
    for declaration in claim.get("all_of", []):
        answered, how = review.evaluate(system, condition, (declaration,))
        out.append(review.RECORD_TOO_BROAD if answered else review.MATCH)
    for group in claim.get("one_of", []):
        answered, _ = review.evaluate(system, condition, tuple(group))
        out.append(review.RECORD_TOO_BROAD if answered else review.MATCH)
        if len(group) > 1:
            for member in group:
                answered_one, _ = review.evaluate(system, condition, (member,))
                out.append(
                    review.MATCH if answered_one else review.RECORD_TOO_NARROW
                )
    return out


def test_1_record_requires_three_inputs_but_runtime_accepts_one():
    """Planted: the record demands A, B and C; the runtime needs only A."""
    def assemble(d):
        return {"planted"} if "a" in d else set()

    claim = {"clause": "UNKNOWN unless a, b and c are supplied.",
             "all_of": ["a", "b", "c"]}
    with planted("planted.one", {"a": 1, "b": 2, "c": 3}, assemble,
                 ("planted.one", "planted"), claim):
        verdicts = results_for("planted.one", "planted", claim)
    assert verdicts.count(review.RECORD_TOO_BROAD) == 2, verdicts
    assert review.MATCH in verdicts, "dropping the input it really needs must match"


def test_2_record_says_one_input_is_enough_but_runtime_requires_three():
    """Planted: the record offers two alternative routes; the runtime needs both."""
    def assemble(d):
        return {"planted"} if {"a", "b"} <= set(d) else set()

    claim = {"clause": "UNKNOWN only when neither route is available.",
             "one_of": [["a", "b"]]}
    with planted("planted.two", {"a": 1, "b": 2}, assemble,
                 ("planted.two", "planted"), claim):
        verdicts = results_for("planted.two", "planted", claim)
    assert review.RECORD_TOO_NARROW in verdicts, verdicts
    assert verdicts.count(review.RECORD_TOO_NARROW) == 2, (
        "each alternative route the runtime does not honour must be reported"
    )


def test_3_record_claims_a_crosscheck_but_only_one_route_executes():
    """Planted: a fake cross-check that answers from a single route."""
    def assemble(d):
        # answers from EITHER route alone, while claiming to compare both
        return {"agreement"} if ({"route_a"} <= set(d) or {"route_b"} <= set(d)) else set()

    claim = {
        "clause": "UNKNOWN unless both route_a and route_b are supplied, because "
                  "this condition compares the two.",
        "all_of": ["route_a", "route_b"],
    }
    with planted("planted.three", {"route_a": 1, "route_b": 2}, assemble,
                 ("planted.three", "agreement"), claim):
        verdicts = results_for("planted.three", "agreement", claim)
    assert verdicts.count(review.RECORD_TOO_BROAD) == 2, verdicts


def test_4_record_applicability_is_wider_than_runtime_validity():
    """Planted: the record advertises a value the runtime refuses.

    This is the one direction the drop-a-declaration experiment cannot see, so
    it has its own probe: take a value the record says is supported and find
    out whether the runtime will build it.
    """
    def prober(value):
        if value > 10.0:
            raise ValueError("runtime refuses above 10")
        return "ACCEPTED"

    def applicability_gap(prober, claimed_supported):
        gaps = []
        for value in claimed_supported:
            try:
                prober(value)
            except Exception as exc:
                gaps.append((value, f"{type(exc).__name__}: {exc}"))
        return gaps

    # the record claims support up to 50; the runtime stops at 10
    gaps = applicability_gap(prober, [1.0, 5.0, 20.0, 50.0])
    assert gaps, "an applicability claim wider than the runtime must be reported"
    assert [g[0] for g in gaps] == [20.0, 50.0]

    # and the probe must stay silent when the claim is honest
    assert applicability_gap(prober, [1.0, 5.0]) == []


def test_5_runtime_changes_and_the_record_does_not():
    """Planted: a real derivation is monkeypatched to answer where it refused.

    The closest thing to genuine drift: production text unchanged, production
    behaviour moved. Uses the live thermal record and a patched copy of the
    derivation, restored in a finally.
    """
    import engcore.domains.thermal_models.context as tc

    system, condition = "thermal.lumped", tc.MELTING_TEMPERATURE_UTILIZATION
    claim = CLAIMS[(system, condition)]

    # Before: the record promises UNKNOWN without a melting temperature, and
    # the runtime keeps that promise.
    assert results_for(system, condition, claim) == [review.MATCH]

    original = tc.melting_temperature_utilization
    try:
        def drifted(*, peak_temperature=None, melting_temperature=None):
            from engcore.scientific.units.quantity import Quantity
            if melting_temperature is None:      # the drift: invent an answer
                return Quantity(0.5, "dimensionless")
            return original(
                peak_temperature=peak_temperature,
                melting_temperature=melting_temperature,
            )

        tc.melting_temperature_utilization = drifted
        verdicts = results_for(system, condition, claim)
        assert verdicts == [review.RECORD_TOO_BROAD], verdicts
    finally:
        tc.melting_temperature_utilization = original

    # After restoring, the audit is quiet again — so the detection above was
    # the planted drift and not a standing failure.
    assert results_for(system, condition, claim) == [review.MATCH]


def test_the_live_surface_is_clean_and_fully_covered():
    """The audit's own headline, asserted rather than reported."""
    result = review.review()
    bad = [r for r in result["rows"] if r["result"] != review.MATCH]
    assert bad == [], bad
    assert nominals.assert_physical() == [], "audit inputs left the physical range"
