"""Core re-audit 2026-09-16, batch 35: a record's re-derivation is only as good as its inputs.

Problem R-22 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-14 part C of
four, under benchmarks/core_v4_false_confidence/BATCH35_THRESHOLD_PROTOCOL.json. Three of R-22's four
claims; the observation count is part D, with the schema bump.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import copy

import pytest

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteClaim, local_gaussian_posterior
from engcore.hybrid_uq.local_gaussian import (
    _MULTISTART_POLICY_KEYS,
    LocalGaussianPosterior,
    MULTISTART_MASS_FLOOR,
)
from engcore.hybrid_uq.vocabulary import HybridUQError


def _payload(problem, **policy):
    posterior = local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                         multistart=MultistartPolicy(**policy))
    return posterior, posterior.to_dict()


def _claimed(payload, claim, *, uniqueness=None, refusals=(), downgrades=()):
    """A forger's payload: every re-derived field edited to agree with the claim being bought."""
    edited = copy.deepcopy(payload)
    if uniqueness is not None:
        edited["diagnostics"]["uniqueness"] = uniqueness
    edited["diagnostics"]["refusals"] = list(refusals)
    edited["diagnostics"]["downgrades"] = list(downgrades)
    edited["diagnostics"]["claim"] = claim
    edited["claim"] = claim
    return edited


# ---------------------------------------------------------------------------
# a_record_that_lists_starts_carries_the_policy_they_were_drawn_under
# ---------------------------------------------------------------------------
def test_r22c_a_narrow_search_is_genuinely_downgraded():
    """The premise, measured."""
    posterior, _ = _payload(S.affine("R22c"), interior_fraction=0.02)
    assert posterior.claim is RouteClaim.DOWNGRADED
    assert "MULTISTART_INCOMPLETE" in {reason.value for reason in posterior.reasons}
    assert posterior.diagnostics.uniqueness == "MULTISTART_BELOW_MINIMUM_SEARCH"


@pytest.mark.xfail(strict=True, reason="R-22(c): with no policy keys the record counts as pre-policy")
def test_r22c_stripping_the_policy_no_longer_buys_a_supported_reading():
    """The audited forgery: four coordinated edits turned DOWNGRADED into SUPPORTED with no reasons at all."""
    _posterior, payload = _payload(S.affine("R22c"), interior_fraction=0.02)
    forged = _claimed(payload, "SUPPORTED", uniqueness="MULTISTART_NO_SECOND_MODE")
    for key in _MULTISTART_POLICY_KEYS:
        forged["diagnostics"]["thresholds"].pop(key, None)
    with pytest.raises(HybridUQError, match="policy"):
        LocalGaussianPosterior.from_dict(forged)


def test_r22c_a_partial_policy_is_still_refused_and_a_full_one_still_reads():
    """Controls: the existing partial-policy refusal, and the genuine record round-tripping."""
    _posterior, payload = _payload(S.affine("R22c"), interior_fraction=0.02)
    assert LocalGaussianPosterior.from_dict(copy.deepcopy(payload)).claim is RouteClaim.DOWNGRADED
    partial = copy.deepcopy(payload)
    partial["diagnostics"]["thresholds"].pop(sorted(_MULTISTART_POLICY_KEYS)[0])
    with pytest.raises(HybridUQError, match="policy"):
        LocalGaussianPosterior.from_dict(partial)


def test_r22c_a_record_with_no_starts_and_no_policy_still_reads():
    """The control that keeps the rule from being 'every record carries a policy'.

    A route refused before any multistart runs records neither, and that record must still read back.
    """
    problem = S.affine("R22c_early")
    # No MultistartPolicy at all: the route records no starts and no policy, which is the shape the rule
    # must not refuse.
    posterior = local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                         multistart=None)
    payload = posterior.to_dict()
    assert not payload["diagnostics"]["multistart"]
    assert not set(payload["diagnostics"]["thresholds"]) & set(_MULTISTART_POLICY_KEYS)
    assert LocalGaussianPosterior.from_dict(payload).claim is posterior.claim


# ---------------------------------------------------------------------------
# a_tail_ratio_is_nan_only_when_no_tail_probe_was_evaluated
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-22(d): a NaN tail ratio yields no verdict and no problem")
@pytest.mark.parametrize("encoding", ["nan", float("nan")], ids=["string", "float"])
def test_r22d_a_tail_ratio_that_no_probe_produced_is_refused(encoding):
    """The route writes NaN only when no probe was evaluated, and then the skip count is not zero."""
    posterior, payload = _payload(S.affine("R22d"))
    assert posterior.claim is RouteClaim.SUPPORTED
    assert payload["diagnostics"]["tail_probes_skipped"] == 0
    assert not payload["diagnostics"]["near_bound"] and not payload["diagnostics"]["at_bound"]
    forged = copy.deepcopy(payload)
    forged["diagnostics"]["minimum_tail_rise_ratio"] = encoding
    with pytest.raises(HybridUQError, match="tail"):
        LocalGaussianPosterior.from_dict(forged)


def test_r22d_a_genuine_record_with_no_tail_probe_still_reads():
    """The control, and the reason the rule is a disjunction: a bound reached is why a probe is skipped."""
    posterior, payload = _payload(F.tail_beyond_a_bound(2.0))
    diagnostics = payload["diagnostics"]
    assert diagnostics["tail_probes_skipped"] or diagnostics["near_bound"] or diagnostics["at_bound"], (
        "the fixture must be one the route legitimately skipped a probe on, or it says nothing"
    )
    assert LocalGaussianPosterior.from_dict(copy.deepcopy(payload)).claim is posterior.claim


def test_r22d_an_infinite_tail_ratio_is_still_refused():
    """The control for the rule next door, which this batch does not change."""
    _posterior, payload = _payload(S.affine("R22d"))
    forged = copy.deepcopy(payload)
    forged["diagnostics"]["minimum_tail_rise_ratio"] = "inf"
    with pytest.raises(HybridUQError, match="tail"):
        LocalGaussianPosterior.from_dict(forged)


# ---------------------------------------------------------------------------
# the_relabelled_refit_is_recorded_as_already_closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("target", ["WORSE_LOCAL_OPTIMUM", "SAME_OPTIMUM", "LOWER_OBJECTIVE_SAME_BASIN"])
def test_r22b_relabelling_a_genuine_second_mode_is_already_refused(target):
    """ALREADY CLOSED by an earlier batch's mass-ratio rule, pinned here so the closure cannot be lost.

    The audit's fix direction asks for the class to be re-derived from the OBJECTIVE. Read against the code,
    that is not the rule production uses: WORSE_LOCAL_OPTIMUM is chosen when a separated mode's Laplace mass
    is negligible, not when its fit is worse -- a narrow equally-deep mode is legitimately WORSE_LOCAL_OPTIMUM.
    What the record needed was the MASS re-derived against the class, and that is what refuses these.
    """
    _posterior, payload = _payload(F.second_mode_behind_a_refit_budget(), starts=12)
    entries = payload["diagnostics"]["multistart"]
    genuine = [e for e in entries if e.get("classification") == "SECOND_MODE"]
    assert genuine, "the fixture must find a second mode, or there is nothing to relabel"
    assert all(e["laplace_mass_ratio"] > MULTISTART_MASS_FLOOR for e in genuine)
    forged = copy.deepcopy(payload)
    for entry in forged["diagnostics"]["multistart"]:
        if entry.get("classification") == "SECOND_MODE":
            entry["classification"] = target
    with pytest.raises(HybridUQError):
        LocalGaussianPosterior.from_dict(forged)
