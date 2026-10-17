"""Adaptive resolution (adaptive mesh control slice 1, active-epic exception EXC-1; ERT V1 Big Rock 19).

Exact first-order model: value(n) = 1 + 1/n, baseline n = 4, ratio 2.
* n = 4, 8, 16: canonical GCI with p = 1, half-width 1.25 * 0.0625 = 0.078125 (> 0.05 target);
* adding n = 32: half-width 1.25 * 0.03125 = 0.0390625 (<= 0.05) -> TARGET_MET, extrapolate exactly 1.0.
All values are exact in binary.  NOT YET EXECUTED (build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import pytest

from engcore.claims.adaptive_resolution import (
    AdaptiveResolutionError, AdaptiveResolutionPolicy, AdaptiveResolutionStatus, ResolutionLevelRun, adapt_resolution,
)
from engcore.claims.uncertainty import transport
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.results.uncertainty import UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel


def _policy(**kw):
    base = dict(refined_inputs={"numerics.cells": 4}, ratio=2, max_levels=6, formal_order=1.0, order_tolerance=0.1,
                target_half_width=Quantity(0.05, "K"), basis="first-order scheme; target from the test")
    return AdaptiveResolutionPolicy(**{**base, **kw})


def _solver(value_of, usable_until=None):
    calls = []

    def solve(counts, level):
        calls.append(dict(counts))
        n = counts["numerics.cells"]
        usable = usable_until is None or level <= usable_until
        return ResolutionLevelRun(counts, value_of(n, level) if usable else None, f"run~{level}", usable,
                                  None if usable else "solver did not converge")

    return solve, calls


def first_order(n, _level):
    return 1.0 + 1.0 / n


def test_refines_until_the_canonical_estimate_meets_the_target():
    solve, calls = _solver(first_order)
    record = adapt_resolution(solve, _policy(), quantity="t", units="K")
    assert record.status is AdaptiveResolutionStatus.TARGET_MET
    assert [c["numerics.cells"] for c in calls] == [4, 8, 16, 32]
    assert record.reported_value == pytest.approx(1.03125)
    assert record.estimate.half_width == pytest.approx(0.0390625)
    assert record.estimate.richardson_extrapolate == pytest.approx(1.0)


def test_the_met_target_is_the_canonical_numerical_interval_of_the_finest_run():
    solve, _ = _solver(first_order)
    uncertainty = adapt_resolution(solve, _policy(), quantity="t", units="K").uncertainty()
    assert UncertaintySource(uncertainty.source_kind) is UncertaintySource.NUMERICAL
    assert uncertainty.lower.magnitude_in("K") == pytest.approx(1.03125 - 0.0390625)
    assert transport({"t": uncertainty}).state_of(UncertaintyChannel.NUMERICAL) == "quantified"


def test_a_spent_budget_keeps_the_quantified_interval_and_says_it_misses_the_target():
    solve, calls = _solver(first_order)
    record = adapt_resolution(solve, _policy(max_levels=3), quantity="t", units="K")
    assert record.status is AdaptiveResolutionStatus.BUDGET_EXHAUSTED
    assert len(calls) == 3 and record.estimate.half_width == pytest.approx(0.078125)
    assert record.uncertainty().is_quantified  # honest interval, but the target was not met


def test_an_oscillating_sequence_never_yields_a_quantified_answer():
    solve, _ = _solver(lambda n, level: 1.0 + (-1) ** level / n)
    record = adapt_resolution(solve, _policy(), quantity="t", units="K")
    assert record.status is AdaptiveResolutionStatus.UNKNOWN
    assert not record.uncertainty().is_quantified


def test_an_unusable_level_stops_the_search_rather_than_being_skipped():
    solve, calls = _solver(first_order, usable_until=1)
    record = adapt_resolution(solve, _policy(), quantity="t", units="K")
    assert record.status is AdaptiveResolutionStatus.UNKNOWN and len(calls) == 3
    assert record.reported_value is None and not record.uncertainty().is_quantified
    assert "not usable" in record.reason


def test_a_run_at_other_counts_than_requested_is_refused():
    def solve(counts, level):
        return ResolutionLevelRun({"numerics.cells": 5}, 1.0, "r", True)

    with pytest.raises(AdaptiveResolutionError, match="exactly"):
        adapt_resolution(solve, _policy(), quantity="t", units="K")


@pytest.mark.parametrize("kw", [dict(ratio=1), dict(max_levels=2), dict(max_levels=13), dict(formal_order=0.0),
                                dict(order_tolerance=float("nan")), dict(basis=" "), dict(refined_inputs={}),
                                dict(refined_inputs={"n": 0}), dict(target_half_width=Quantity(0.0, "K"))])
def test_policy_declarations_are_checked(kw):
    with pytest.raises(AdaptiveResolutionError):
        _policy(**kw)


def test_a_target_stated_as_an_absolute_offset_temperature_is_refused():
    with pytest.raises(ScientificCoreError, match="spread"):
        _policy(target_half_width=Quantity(0.05, "degC"))
    _policy(target_half_width=Quantity(0.05, "delta_degC"))  # a difference unit is a spread


def test_the_record_never_reads_as_validation():
    solve, _ = _solver(first_order)
    notice = adapt_resolution(solve, _policy(), quantity="t", units="K").to_dict()["notice"]
    assert "not validation" in notice and "never a stage promotion" in notice
