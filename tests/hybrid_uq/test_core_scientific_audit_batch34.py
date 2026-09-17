"""Core re-audit 2026-09-16, batch 34: an identifiability verdict is not bought by argument.

Problem R-28 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-14 part B of
four, under benchmarks/core_v4_false_confidence/BATCH34_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, local_gaussian_posterior
from engcore.hybrid_uq.identifiability import (
    CANONICAL_IDENTIFIABILITY_THRESHOLDS,
    RoutedIdentifiability,
    assess_routed_identifiability,
)
from engcore.inference.calibration import CalibrationError, IdentifiabilityStatus

from engcore.hybrid_uq.vocabulary import HybridUQError

#: The audited case: local route SUPPORTED, widths [8.553, 1.842], correlation 0.9999985.
LOOSENED = {"correlation_threshold": 0.99999, "condition_threshold": 1.0e300, "width_threshold": 1.0e9}
VERY_LOOSENED = {**LOOSENED, "correlation_threshold": 0.9999999999999}


def _local():
    problem = S.weak_identification()
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy())


# ---------------------------------------------------------------------------
# the_local_branch_is_held_to_the_declared_thresholds_too
# ---------------------------------------------------------------------------
def test_r28_the_canonical_verdict_is_not_identifiable():
    """The premise, measured rather than assumed."""
    report = assess_routed_identifiability(_local()).report
    assert report.status is IdentifiabilityStatus.NOT_IDENTIFIABLE
    assert max(report.relative_widths) == pytest.approx(8.553, rel=1e-3)
    assert report.max_abs_correlation == pytest.approx(0.9999985, rel=1e-5)


@pytest.mark.xfail(strict=True, reason="R-28: the INF-10 guard runs only for grids")
@pytest.mark.parametrize("thresholds", [LOOSENED, VERY_LOOSENED], ids=["weakly", "identifiable"])
def test_r28_a_looser_rule_is_refused_on_the_local_route(thresholds):
    with pytest.raises(CalibrationError, match="looser than the declared"):
        assess_routed_identifiability(_local(), **thresholds)


def test_r28_the_grid_branch_already_refused_the_same_argument():
    """Why this is an inconsistency inside one function and not a new rule."""
    problem = S.weak_identification()
    grid = problem.grid([np.linspace(-50.0, 50.0, 60), np.linspace(-5.0, 5.0, 60)])
    with pytest.raises(CalibrationError, match="looser than the declared"):
        assess_routed_identifiability(grid, width_threshold=1.0e9)


def test_r28_a_stricter_rule_is_still_allowed_on_the_local_route():
    """The control: the thresholds are arguments so a study can be STRICTER, which INF-10 says explicitly."""
    report = assess_routed_identifiability(_local(), width_threshold=0.5).report
    assert report.width_threshold == 0.5
    assert report.status is IdentifiabilityStatus.NOT_IDENTIFIABLE


def test_r28_the_default_call_is_untouched():
    """The control that matters most: the router calls this with its defaults."""
    report = assess_routed_identifiability(_local()).report
    for key, value in CANONICAL_IDENTIFIABILITY_THRESHOLDS.items():
        assert getattr(report, key) == value


# ---------------------------------------------------------------------------
# a_tightened_rule_is_named_in_the_explanation
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-28: the local path appends no tightened note")
def test_r28_a_tightened_local_verdict_says_the_rule_was_moved():
    report = assess_routed_identifiability(_local(), width_threshold=0.5).report
    assert "caller-tightened thresholds" in report.why, (
        f"a stricter verdict is still reached under a rule that is not the declared one, and the grid path "
        f"says so in these words. why={report.why!r}"
    )
    assert "width_threshold" in report.why and "0.5" in report.why


def test_r28_an_untightened_verdict_does_not_claim_one():
    """The control: the note appears only when the rule actually moved."""
    assert "caller-tightened" not in assess_routed_identifiability(_local()).report.why


# ---------------------------------------------------------------------------
# a_record_cannot_carry_a_rule_looser_than_the_routers
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-28: a self-consistent record with a moved rule reads back")
def test_r28_a_record_carrying_a_looser_rule_is_refused_at_construction():
    """This is where a bought verdict SURVIVES: the record is self-consistent, which is the problem."""
    import dataclasses

    canonical = assess_routed_identifiability(_local())
    forged_report = dataclasses.replace(canonical.report, width_threshold=1.0e9)
    with pytest.raises(HybridUQError, match="looser"):
        RoutedIdentifiability(approximation_class=canonical.approximation_class,
                              parameterization_digest=canonical.parameterization_digest,
                              route_claim=canonical.route_claim, report=forged_report)


def test_r28_a_record_round_trips_and_a_forged_payload_does_not():
    canonical = assess_routed_identifiability(_local())
    assert RoutedIdentifiability.from_dict(canonical.to_dict()).status is canonical.status
    payload = canonical.to_dict()
    payload["report"]["width_threshold"] = 1.0e9
    with pytest.raises(HybridUQError):
        RoutedIdentifiability.from_dict(payload)
