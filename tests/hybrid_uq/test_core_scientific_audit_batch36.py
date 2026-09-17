"""Core re-audit 2026-09-16, batch 36: the observation count is bound to the observations.

Problem R-22 claim (a) (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-14
part D of four, under benchmarks/core_v4_false_confidence/BATCH36_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import copy
import dataclasses
import re

import pytest

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteClaim, local_gaussian_posterior
from engcore.hybrid_uq import local_gaussian as LG
from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
from engcore.hybrid_uq.vocabulary import HybridUQError
from engcore.inference import split as SPLIT

DIGEST_FORM = re.compile(r"^\d+:[0-9a-f]{64}$")


def _posterior(problem, **policy):
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy(**policy))


def _symbol(module, name):
    assert hasattr(module, name), (
        f"{module.__name__} has no {name!r}; it is preregistered in BATCH36_THRESHOLD_PROTOCOL.json"
    )
    return getattr(module, name)


# ---------------------------------------------------------------------------
# an_observation_set_has_a_content_digest
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_an_observation_set_digests_its_count_and_its_content():
    digest_of = _symbol(SPLIT, "observation_set_content_digest")
    problem = S.affine("R22a")
    digest = digest_of(problem.observations)
    assert DIGEST_FORM.match(digest), digest
    assert digest.split(":")[0] == str(len(problem.observations.observations))


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_the_same_evidence_in_another_order_is_the_same_digest():
    """A set of observations is a set, and the per-observation digest already ignores what a row is called."""
    from engcore.inference.grid import ObservationSet

    digest_of = _symbol(SPLIT, "observation_set_content_digest")
    problem = S.affine("R22a")
    rows = tuple(problem.observations.observations)
    forward = ObservationSet(observations=rows, dataset_id=problem.observations.dataset_id)
    backward = ObservationSet(observations=tuple(reversed(rows)), dataset_id=problem.observations.dataset_id)
    assert digest_of(forward) == digest_of(backward)


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_a_different_reading_is_a_different_digest():
    """The control: the digest must be over the content and not only the count."""
    from engcore.inference.grid import GaussianObservation, ObservationSet
    from engcore.scientific.units.quantity import Quantity

    digest_of = _symbol(SPLIT, "observation_set_content_digest")
    problem = S.affine("R22a")
    rows = list(problem.observations.observations)
    nudged = dataclasses.replace(rows[0], value=Quantity(rows[0].value.magnitude + 1.0, rows[0].value.units))
    other = ObservationSet(observations=(nudged, *rows[1:]), dataset_id=problem.observations.dataset_id)
    assert digest_of(other) != digest_of(problem.observations)
    assert digest_of(other).split(":")[0] == digest_of(problem.observations).split(":")[0]


# ---------------------------------------------------------------------------
# the_record_carries_it_and_the_count_agrees
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_a_record_carries_the_digest_of_the_observations_it_was_fitted_to():
    digest_of = _symbol(SPLIT, "observation_set_content_digest")
    problem = S.affine("R22a")
    posterior = _posterior(problem)
    payload = posterior.to_dict()
    assert payload["diagnostics"]["schema"] == "hybrid_uq.route_diagnostics/3"
    carried = payload["diagnostics"]["observation_content_digest"]
    assert carried == digest_of(problem.observations)
    assert carried.split(":")[0] == str(payload["diagnostics"]["observations"])


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_editing_the_observation_count_is_refused():
    """The audited edit: `observations` feeds the goodness of fit and nothing else reads it."""
    posterior = _posterior(F.gross_misfit_with_ten_precise_points())
    assert posterior.claim is RouteClaim.REFUSED
    payload = posterior.to_dict()
    assert payload["diagnostics"]["observations"] == 10
    forged = copy.deepcopy(payload)
    forged["diagnostics"]["observations"] = 40
    forged["diagnostics"]["refusals"] = []
    forged["diagnostics"]["claim"] = "SUPPORTED"
    forged["claim"] = "SUPPORTED"
    with pytest.raises(HybridUQError, match="observation"):
        LocalGaussianPosterior.from_dict(forged)


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_a_record_with_no_digest_under_the_new_schema_is_refused():
    posterior = _posterior(S.affine("R22a"))
    forged = copy.deepcopy(posterior.to_dict())
    forged["diagnostics"]["observation_content_digest"] = ""
    with pytest.raises(HybridUQError, match="observation"):
        LocalGaussianPosterior.from_dict(forged)


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_a_genuine_record_still_round_trips():
    """The control."""
    posterior = _posterior(S.affine("R22a"))
    read = LocalGaussianPosterior.from_dict(copy.deepcopy(posterior.to_dict()))
    assert read.claim is posterior.claim
    assert read.diagnostics.observation_content_digest == posterior.diagnostics.observation_content_digest


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_an_older_payload_is_still_readable():
    """A /2 payload carries no digest, and refusing it would break records this core wrote three batches ago."""
    posterior = _posterior(S.affine("R22a"))
    older = copy.deepcopy(posterior.to_dict())
    older["diagnostics"]["schema"] = "hybrid_uq.route_diagnostics/2"
    older["diagnostics"].pop("observation_content_digest")
    assert LocalGaussianPosterior.from_dict(older).claim is posterior.claim


# ---------------------------------------------------------------------------
# the_route_checks_its_own_record_against_the_observations_it_used
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_the_route_binds_its_own_record_to_the_observations_it_used():
    require = _symbol(LG, "require_posterior_matches_observations")
    problem = S.affine("R22a")
    posterior = _posterior(problem)
    require(posterior, problem.observations)  # the genuine pair
    other = S.affine("R22a_other", seed=999)
    with pytest.raises(HybridUQError, match="observation"):
        require(posterior, other.observations)


@pytest.mark.xfail(strict=True, reason="R-22(a): the count is a free field and there is no digest")
def test_r22a_a_record_whose_count_was_edited_to_agree_still_fails_against_the_observations():
    """Why the count is in the clear AND the digest is there: editing both to agree leaves a record that
    matches no observation set at all, and this is the check that says so."""
    require = _symbol(LG, "require_posterior_matches_observations")
    problem = S.affine("R22a")
    posterior = _posterior(problem)
    forged = dataclasses.replace(
        posterior.diagnostics, observations=40,
        observation_content_digest="40:" + "0" * 64)
    with pytest.raises(HybridUQError, match="observation"):
        require(dataclasses.replace(posterior, diagnostics=forged), problem.observations)
