"""Batch 10 of the 2026-09-16 core re-audit: an honest multistart (I-02, closing R-07, R-08, R-18).

The search every hybrid-UQ claim of a single mode rests on counted things that had not happened. Three ways:

* **R-08** -- ``max_evaluations`` and ``maximum_retractions`` were recorded and were not part of the minimum
  search, and a refit that ran out of budget was dropped while the search still counted as complete as long
  as half the starts converged. A refit budget of 12 turned REFUSED SECOND_MODE_FOUND into SUPPORTED
  MULTISTART_NO_SECOND_MODE with no shortfall recorded at all.
* **R-18** -- a start the forward model refused was halved toward the estimate, up to twelve times, and then
  counted as a full-span start. Five of six starts pulled into the estimate's own basin read "no second mode".
* **R-07** -- a separated converged refit was classified by its objective alone, so a broad basin ten
  chi-square units up holding 0.79 of the posterior was WORSE_LOCAL_OPTIMUM, which the verdict ignored.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH10_THRESHOLD_PROTOCOL.json`. The eleven
reproductions here were committed as `xfail(strict=True)` at 8f094f04 and run with `--runxfail` to watch
each fail on its own assertion; the markers came off when I-02 was implemented. The rest carry no marker
and never did. Two of them passed at 8f094f04 and must keep passing: the lower-separated-optimum case (a
better optimum must not become a mass-weighed WORSE_LOCAL_OPTIMUM) and the unseparated-start case (a
SAME_OPTIMUM refit is not a mode and gets no ratio). Two were added with the implementation, to exercise the
branch the audited cases do not reach: a separated mode whose mass cannot be bounded is counted, and the
read-back takes a recorded reason in place of the number for SECOND_MODE and for nothing else.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    local_gaussian_posterior,
)
from engcore.hybrid_uq.local_gaussian import _minimum_starts

CANONICAL = MultistartPolicy()


def _mass_floor():
    """The floor as the module exposes it, or None -- read with ``getattr`` so a test that needs it fails on
    its own assertion rather than on an ImportError while the batch is still preregistered."""
    from engcore.hybrid_uq import local_gaussian

    return getattr(local_gaussian, "MULTISTART_MASS_FLOOR", None)


def _local(problem, multistart=None):
    if multistart is None:
        multistart = MultistartPolicy()
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=multistart)


def _entries(post):
    return tuple(dict(entry) for entry in post.diagnostics.multistart)


# =====================================================================
# R-08: the budget and the allowance are part of the search
# =====================================================================
def test_r08_a_refit_budget_below_the_canonical_one_is_a_shortfall():
    """The audited record: max_evaluations 12 gives SUPPORTED with 'recorded policy shortfalls: []'."""
    from engcore.hybrid_uq.local_gaussian import _policy_record, _search_shortfalls

    problem = F.second_mode_behind_a_refit_budget()
    small = MultistartPolicy(max_evaluations=12)
    shortfalls = _search_shortfalls(_policy_record(small, 1), 1)
    assert any("evaluation" in text for text in shortfalls), shortfalls
    assert _search_shortfalls(_policy_record(CANONICAL, 1), 1) == [], "the canonical policy is the minimum"


def test_r08_a_replacement_allowance_below_the_canonical_one_is_a_shortfall():
    from engcore.hybrid_uq.local_gaussian import _policy_record, _search_shortfalls

    narrow = MultistartPolicy(maximum_retractions=0)
    shortfalls = _search_shortfalls(_policy_record(narrow, 1), 1)
    assert shortfalls, "a search that may not replace a refused start looks in fewer places"


def test_r08_a_search_is_incomplete_unless_the_minimum_number_converged():
    """The audited rule was `converged * 2 < len(entries)`: up to half the starts could fail silently."""
    from engcore.hybrid_uq.local_gaussian import _multistart_verdict, _policy_record

    thresholds = _policy_record(CANONICAL, 1)
    minimum = _minimum_starts(1)
    converged = [{"status": "CALIBRATION_CONVERGED", "classification": "SAME_OPTIMUM",
                  "chi_square": 0.0, "mahalanobis_sq": 0.0} for _ in range(minimum - 1)]
    failed = [{"status": "CALIBRATION_FAILED"}]
    uniqueness, _refusals, downgrades = _multistart_verdict(converged + failed, 1, thresholds)
    assert RouteReason.MULTISTART_INCOMPLETE in downgrades, (uniqueness, downgrades)
    full = converged + [dict(converged[0])]
    uniqueness, _refusals, downgrades = _multistart_verdict(full, 1, thresholds)
    assert RouteReason.MULTISTART_INCOMPLETE not in downgrades, uniqueness


def test_r08_a_failed_refit_is_retried_at_the_canonical_budget():
    """The audited record: max_evaluations 12 gives SUPPORTED MULTISTART_NO_SECOND_MODE and sd 1.0, against
    REFUSED SECOND_MODE_FOUND at the canonical budget and a reference sd of 9.72."""
    problem = F.second_mode_behind_a_refit_budget()
    post = _local(problem, MultistartPolicy(max_evaluations=12))
    assert post.claim is not RouteClaim.SUPPORTED, [r.value for r in post.reasons]
    assert RouteReason.SECOND_MODE_FOUND in post.reasons, (
        f"the canonical budget finds the mode at theta = 20, so a retry at it must too; the record says "
        f"{post.diagnostics.uniqueness} over {[e.get('status') for e in _entries(post)]}")


# =====================================================================
# R-18: a refused start is replaced, not retracted
# =====================================================================
def test_r18_a_refused_start_is_replaced_by_the_next_halton_point():
    """The audited record: 'proposed [-12.0] used [-0.75] retractions 4' -- a start that searched 1/16 of
    its intended span and counted as a full one."""
    problem = F.retracted_starts_never_leave_the_basin()
    post = _local(problem)
    entries = _entries(post)
    for entry in entries:
        assert "retractions" not in entry, f"nothing retracts any more: {entry}"
        used = entry.get("start")
        proposed = entry.get("proposed_start", used)
        if used is not None and proposed is not None and tuple(used) != tuple(proposed):
            # A replacement, not a halving: the used point is another Halton point of the box and not
            # a fraction of the way from the proposed one to the estimate.
            z0 = float(post.inference_point[0])
            halved = abs(float(used[0]) - z0) / max(abs(float(proposed[0]) - z0), 1e-300)
            assert not any(abs(halved - 2.0 ** -k) < 1e-9 for k in range(1, 13)), (
                f"used {used} is {halved:.6g} of the way from the estimate to proposed {proposed}")
        assert isinstance(entry.get("replacements", 0), int)
    used = [tuple(entry["start"]) for entry in entries]
    assert len(set(used)) == len(used), f"one shared counter means no two starts take the same point: {used}"


def test_r18_starts_that_never_leave_the_basin_do_not_claim_a_single_mode():
    """The audited record: MULTISTART_NO_SECOND_MODE, SUPPORTED, sd 0.1, over a posterior whose two equal
    modes sit at 0 and 20 -- so the reported 95% interval holds 0.4748 of it."""
    problem = F.retracted_starts_never_leave_the_basin()
    post = _local(problem)
    assert post.claim is not RouteClaim.SUPPORTED, (
        f"uniqueness {post.diagnostics.uniqueness} over {[e.get('classification') for e in _entries(post)]}")
    # and it is the second island the search reaches, not merely a shortfall it reports: a replacement is a
    # full-span point of the same sequence, so a start refused near the estimate can still land on the far island
    assert RouteReason.SECOND_MODE_FOUND in post.reasons, (
        f"uniqueness {post.diagnostics.uniqueness} over {[e.get('start') for e in _entries(post)]}")


# =====================================================================
# R-07: a separated optimum is classified by its mass
# =====================================================================
def test_r07_a_separated_optimum_records_the_mass_its_classification_follows_from():
    problem = F.worse_local_optimum_holds_the_mass()
    post = _local(problem)
    separated = [e for e in _entries(post)
                 if e.get("status") == "CALIBRATION_CONVERGED"
                 and e.get("classification") in ("SECOND_MODE", "WORSE_LOCAL_OPTIMUM")]
    assert separated, [e.get("classification") for e in _entries(post)]
    floor = _mass_floor()
    assert floor is not None, "the classification rule needs a published floor"
    for entry in separated:
        ratio = entry.get("laplace_mass_ratio")
        assert isinstance(ratio, float) and math.isfinite(ratio) and ratio >= 0.0, entry
        expected = "SECOND_MODE" if ratio > floor else "WORSE_LOCAL_OPTIMUM"
        assert entry["classification"] == expected, (entry["classification"], ratio)


def test_r07_a_broad_basin_that_holds_the_mass_is_a_second_mode():
    """The audited record: all six starts WORSE_LOCAL_OPTIMUM at chi2 = 10 and m2 = 2.5e5, SUPPORTED, while
    0.792 of the posterior sits in that basin."""
    problem = F.worse_local_optimum_holds_the_mass()
    post = _local(problem)
    assert RouteReason.SECOND_MODE_FOUND in post.reasons, (
        f"uniqueness {post.diagnostics.uniqueness}; mass ratios "
        f"{[e.get('laplace_mass_ratio') for e in _entries(post)]}")


def test_a_separated_mode_is_weighed_by_its_volume_and_not_only_its_height():
    """The case that separates mass from height, which the R-07 reproduction does not.

    R-07's broad basin is a second mode under either rule: its peak-height ratio exp(-10 / 2) = 6.7e-3 is
    already above the floor, and the volume only raises it. This is the other direction -- the same basin 10
    chi-square units up, made a tenth as wide as the estimate's, so the height still clears the floor and the
    mass ratio 6.7e-4 does not. Not a reproduction: it is here so the volume term of the ratio is measured.
    """
    def model(t, _x):
        th = float(t[0])
        s = np.exp(-((th / 0.5) ** 2))
        return np.asarray([th / 0.01 * s, np.sqrt(10.0) * (1.0 - s), (th - 5.0) * 1000.0 * (1.0 - s)])

    problem = S.Problem("narrow_worse_optimum", model, np.arange(3.0), (0.0,), 1.0, (-1.0,), (30.0,), (0.05,),
                        observed=(0.0, 0.0, 0.0))
    post = _local(problem)
    floor = _mass_floor()
    separated = [e for e in _entries(post) if e.get("classification") in ("SECOND_MODE", "WORSE_LOCAL_OPTIMUM")]
    assert separated, [e.get("classification") for e in _entries(post)]
    for entry in separated:
        height = math.exp(-0.5 * (entry["chi_square"] - float(post.diagnostics.chi_square_minimum)))
        assert height > floor, f"the height alone clears the floor, or the case does not separate the rules: {height:.3g}"
        assert entry["laplace_mass_ratio"] < floor, entry
        assert entry["classification"] == "WORSE_LOCAL_OPTIMUM", entry
    assert RouteReason.SECOND_MODE_FOUND not in post.reasons, [r.value for r in post.reasons]


def test_r07_a_lower_separated_optimum_is_still_refused_whatever_its_mass():
    """BETTER_OPTIMUM is not a second-mode finding: it says the estimate is not the optimum, and no mass
    argument rescues the covariance built at it.

    Not a reproduction -- this already holds, and the mass rule must not weaken it into a negligible
    WORSE_LOCAL_OPTIMUM. The asymmetric double well is the one from
    `test_hybrid_uq_local_route.py::test_a_better_optimum_than_the_estimate_is_refused`.
    """
    problem = S.Problem("better_optimum", lambda t, x: t[0] ** 2 * x + 0.05 * t[0], np.linspace(1.0, 2.0, 8),
                        (1.5,), 0.01, (-3.0,), (3.0,), (-1.9,))
    post = _local(problem)
    words = {e.get("classification") for e in _entries(post)}
    assert "BETTER_OPTIMUM" in words, words
    assert RouteReason.BETTER_OPTIMUM_FOUND in post.reasons


def test_r07_a_negligible_separated_optimum_is_still_only_worse():
    """The floor has to leave something below it, or it is not a floor.

    F4's mirror mode is an EQUAL mode, so it is SECOND_MODE. What must not happen is every separated
    optimum becoming a second mode by construction, so this asserts the classification tracks the recorded
    ratio rather than being constant.
    """
    floor = _mass_floor()
    assert floor is not None and 0.0 < floor < 0.0526, (
        f"the floor is a negligibility floor: above 0.0526 a mode could hold more than the 0.05 of the "
        f"posterior that I-15's 0.90 conformance floor allows to sit outside a 95% interval; got {floor}"
    )
    problem = S.bimodal_two_parameter()
    post = _local(problem)
    ratios = [e.get("laplace_mass_ratio") for e in _entries(post)
              if e.get("classification") in ("SECOND_MODE", "WORSE_LOCAL_OPTIMUM")]
    assert ratios, "the bimodal problem's refits reach the mirror mode"
    assert all(r is not None and r > floor for r in ratios), ratios


# =====================================================================
# the read-back
# =====================================================================
def test_the_read_back_holds_a_separated_classification_to_its_recorded_mass():
    """A SECOND_MODE start whose recorded ratio is negligible is a record whose word does not follow from
    its own number.

    The other direction -- rewriting the classification, the refusals and the uniqueness word together --
    is already refused by `_require_reasons_follow_measurements`, so it is not a reproduction of anything.
    The ratio here is a literal far below any admissible floor rather than the floor itself, so the test
    fails on this assertion while the floor does not yet exist.
    """
    import json

    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
    from engcore.hybrid_uq.vocabulary import HybridUQError

    post = _local(S.bimodal_two_parameter())
    payload = json.loads(json.dumps(post.to_dict()))
    entries = payload["diagnostics"]["multistart"]
    separated = [e for e in entries if e.get("classification") == "SECOND_MODE"]
    assert separated, [e.get("classification") for e in entries]
    for entry in separated:
        entry["laplace_mass_ratio"] = 1e-12
    with pytest.raises(HybridUQError, match="(?i)mass"):
        LocalGaussianPosterior.from_dict(payload)


def test_the_read_back_requires_a_mass_ratio_for_a_separated_start():
    import json

    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
    from engcore.hybrid_uq.vocabulary import HybridUQError

    post = _local(S.bimodal_two_parameter())
    payload = json.loads(json.dumps(post.to_dict()))
    for entry in payload["diagnostics"]["multistart"]:
        entry.pop("laplace_mass_ratio", None)
    with pytest.raises(HybridUQError, match="(?i)mass"):
        LocalGaussianPosterior.from_dict(payload)


def test_a_mass_that_cannot_be_bounded_is_not_a_negligible_mode():
    """When the curvature at either optimum gives no determinant, there is no ratio and no negligibility.

    Not a reproduction: it covers the branch the audited cases do not reach, so that the rule which counts an
    unbounded mode is a checked rule and not an unexercised one.
    """
    from engcore.hybrid_uq.local_gaussian import _log_det_information, _separated_mass_ratio

    problem = S.bimodal_two_parameter()
    calibration = problem.calibrate()
    ratio, spent, unavailable = _separated_mass_ratio(calibration, problem.observations, problem.forward,
                                                      float(calibration.objective_value), None)
    assert ratio is None and spent == 0 and "not positive definite" in unavailable
    assert _log_det_information(np.zeros((3, 2))) is None, "a rank-deficient information has no determinant"


def test_the_read_back_accepts_a_separated_start_whose_mass_could_not_be_bounded():
    """A recorded reason stands in for the number, and only for SECOND_MODE: nothing else may skip the ratio."""
    import json

    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
    from engcore.hybrid_uq.vocabulary import HybridUQError

    post = _local(S.bimodal_two_parameter())
    payload = json.loads(json.dumps(post.to_dict()))
    entries = payload["diagnostics"]["multistart"]
    separated = [e for e in entries if e.get("classification") == "SECOND_MODE"]
    assert len(separated) >= 2, [e.get("classification") for e in entries]
    for entry in separated:
        entry.pop("laplace_mass_ratio")
        entry["laplace_mass_unavailable"] = "the curvature at the refit is not available (RouteRefusedError)"
    LocalGaussianPosterior.from_dict(json.loads(json.dumps(payload)))

    blank = json.loads(json.dumps(payload))
    for entry in blank["diagnostics"]["multistart"]:
        if entry.get("classification") == "SECOND_MODE":
            entry["laplace_mass_unavailable"] = ""
    with pytest.raises(HybridUQError, match="(?i)mass"):
        LocalGaussianPosterior.from_dict(blank)

    # the same record with ONE of the three separated starts called merely worse: the uniqueness word and the
    # refusal are unchanged, so the only thing wrong with it is that a WORSE_LOCAL_OPTIMUM gives no ratio.
    worse = json.loads(json.dumps(payload))
    for entry in worse["diagnostics"]["multistart"]:
        if entry.get("classification") == "SECOND_MODE":
            entry["classification"] = "WORSE_LOCAL_OPTIMUM"
            break
    with pytest.raises(HybridUQError, match="(?i)mass"):
        LocalGaussianPosterior.from_dict(worse)


def test_an_unseparated_start_needs_no_mass_ratio():
    """The route that must keep working: a SAME_OPTIMUM refit is not a mode and has no mass to weigh.

    Not a reproduction -- it passes today and holds the new rule to the unseparated case afterwards.
    """
    post = _local(S.affine())
    assert post.claim is RouteClaim.SUPPORTED, [r.value for r in post.reasons]
    for entry in _entries(post):
        if entry.get("classification") == "SAME_OPTIMUM":
            assert "laplace_mass_ratio" not in entry
