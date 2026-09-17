"""Core re-audit 2026-09-16, batch 37: a record is trusted for nothing no field in it constrains.

Problems R-25 and R-27's finding 24 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json),
improvement I-14 part E of five, under benchmarks/core_v4_false_confidence/BATCH37_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit 3dd5fd08, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import copy
import inspect

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.hybrid_uq import local_gaussian as LG
from engcore.hybrid_uq import router as RO
from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
from engcore.hybrid_uq.router import HybridUQResult, routed_predictive_uncertainty
from engcore.hybrid_uq.vocabulary import HybridUQError
from engcore.uq import PredictiveObservableSpec

SHRINK = 1.0e-4


def _problem():
    return S.affine("R25")


def _posterior(problem):
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy())


def _shrunk(payload, *, rename=None, move_bounds=False):
    """The audited forgeries: a covariance divided by 1e4, hidden one of two ways."""
    edited = copy.deepcopy(payload)
    edited["covariance"] = [[v * SHRINK for v in row] for row in payload["covariance"]]
    if rename is not None:
        edited["parameterization"] = rename
    if move_bounds:
        point = np.asarray(payload["inference_point"], dtype=float)
        scale = float(np.sqrt(SHRINK))
        for key in ("lower_bounds", "upper_bounds"):
            edge = np.asarray(payload[key], dtype=float)
            edited[key] = list(point + (edge - point) * scale)
    return edited


def _symbol(module, name):
    assert hasattr(module, name), (
        f"{module.__name__} has no {name!r}; it is preregistered in BATCH37_THRESHOLD_PROTOCOL.json"
    )
    return getattr(module, name)


# ---------------------------------------------------------------------------
# a_local_route_result_carries_a_declared_posterior
# ---------------------------------------------------------------------------
def test_r25_the_covariance_only_shrink_is_already_refused():
    """The premise: the bound-distance re-derivation works, when it runs."""
    payload = _posterior(_problem()).to_dict()
    with pytest.raises(HybridUQError, match="bound"):
        LocalGaussianPosterior.from_dict(_shrunk(payload))


def test_r25_renaming_the_parameterization_no_longer_switches_the_defence_off():
    """The forgery: any label but 'declared' returns early after one check."""
    problem = _problem()
    posterior = _posterior(problem)
    forged = _shrunk(posterior.to_dict(), rename="linear_map:forged")
    mapped = LocalGaussianPosterior.from_dict(forged)  # on its own, a mapped posterior is legitimate
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                              forward=problem.forward, multistart=MultistartPolicy())
    payload = result.to_dict()
    payload["local_posterior"] = forged
    payload["covariance"] = forged["covariance"]
    with pytest.raises(HybridUQError, match="declared"):
        HybridUQResult.from_dict(payload)
    assert mapped.parameterization == "linear_map:forged"


def test_r25_a_mapped_posterior_is_still_usable_on_its_own():
    """The control: `reparameterized` is a caller's tool and this rule is about a ROUTED record."""
    posterior = _posterior(_problem())
    mapped = posterior.reparameterized(np.eye(len(posterior.parameter_names)),
                                       names=posterior.parameter_names,
                                       units=posterior.parameter_units, label="identity")
    assert mapped.parameterization.startswith("linear_map:")
    assert LocalGaussianPosterior.from_dict(mapped.to_dict()).parameterization == mapped.parameterization


def test_r25_a_genuine_routed_record_still_reads():
    """The control that matters: the router's own record round-trips."""
    problem = _problem()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                              forward=problem.forward, multistart=MultistartPolicy())
    assert HybridUQResult.from_dict(result.to_dict()).claim is result.claim


# ---------------------------------------------------------------------------
# a_records_bounds_are_the_calibrations_bounds
# ---------------------------------------------------------------------------
def test_r25_moving_the_bounds_with_the_covariance_is_caught_against_the_calibration():
    """The second forgery: both move together, so every distance in sd units survives."""
    require = _symbol(LG, "require_posterior_matches_calibration")
    problem = _problem()
    calibration = problem.calibrate()
    posterior = _posterior(problem)
    require(posterior, calibration)  # the genuine pair
    forged = LocalGaussianPosterior.from_dict(_shrunk(posterior.to_dict(), move_bounds=True))
    with pytest.raises(HybridUQError, match="bound|calibration|parameterization"):
        require(forged, calibration)


def test_r25_the_route_binds_its_own_record_to_the_calibration_it_used():
    """The production half: without this the rule is one a reader may choose to apply."""
    require = _symbol(LG, "require_posterior_matches_calibration")
    problem = _problem()
    posterior = _posterior(problem)
    require(posterior, problem.calibrate())
    source = inspect.getsource(LG.local_gaussian_posterior)
    assert "require_posterior_matches_calibration" in source, (
        "the local route must verify its own record against the calibration it used, or the binding is a "
        "rule a reader may choose to apply"
    )


# ---------------------------------------------------------------------------
# a_grid_result_predicts_on_evidence_or_says_it_did_not
# ---------------------------------------------------------------------------
def _grid_result(problem):
    axes = [np.linspace(0.6, 1.4, 81), np.linspace(1.4, 2.6, 81)]
    return route_uncertainty(grid=problem.grid(axes), calibration=problem.calibrate(),
                             observations=problem.observations, forward=problem.forward,
                             multistart=MultistartPolicy())


def _specs(problem):
    return (PredictiveObservableSpec(observation_key=problem.observations.keys[0], unit="dimensionless"),)


def _predict_one(problem):
    """A forward evaluator returning ONE value, for the one observable the spec names.

    `problem.forward` answers with every observation, and `_table_reasons` evaluates the spec's single key.
    """
    from engcore.scientific.units.quantity import Quantity

    def predict(theta):
        values = problem.model(np.asarray(theta, dtype=float), problem.x)
        return [Quantity(float(values[0]), "dimensionless")]

    return predict


def test_r27_predicting_from_a_grid_result_without_its_evidence_is_downgraded():
    problem = _problem()
    result = _grid_result(problem)
    assert result.claim is RouteClaim.SUPPORTED
    table = problem.table_builder()(result.grid.points)
    from engcore.scientific.twins import TwinReference

    records = routed_predictive_uncertainty(
        result, _specs(problem), predictive_table=table, predict=_predict_one(problem),
        twin=TwinReference("twin.synthetic", "1"), model=S.MODEL, source_ref="audit",
        calibration_observations=problem.observations)
    assert records, "the call must still produce records"
    assert all(record.route_claim is not RouteClaim.SUPPORTED for record in records), (
        "a grid result predicted from without its evidence claims SUPPORTED, although the function's own "
        "comment says the evidence checks cannot be re-applied"
    )
    assert any(RouteReason.GRID_NOT_BOUND_TO_EVIDENCE in tuple(record.reasons) for record in records)


def test_r27_predicting_with_the_evidence_is_supported_again():
    """The control: a caller who passes the evidence gets what they got before."""
    problem = _problem()
    result = _grid_result(problem)
    table = problem.table_builder()(result.grid.points)
    from engcore.scientific.twins import TwinReference

    records = routed_predictive_uncertainty(
        result, _specs(problem), predictive_table=table, predict=_predict_one(problem),
        twin=TwinReference("twin.synthetic", "1"), model=S.MODEL, source_ref="audit",
        calibration_observations=problem.observations,
        observations=problem.observations, forward=problem.forward,
        calibration=problem.calibrate())
    # The affine fixture's observations declare no conditions, so PREDICTION_DOMAIN_NOT_DECLARED stands --
    # a pre-existing rule this batch does not touch. What must be gone is the reason this batch adds.
    assert records
    for record in records:
        assert RouteReason.GRID_NOT_BOUND_TO_EVIDENCE not in tuple(record.reasons), (
            f"the evidence was handed over and the record still says it was not bound to it: "
            f"{sorted(x.value for x in record.reasons)}")


def test_r27_the_predictive_entry_point_takes_the_evidence():
    signature = inspect.signature(routed_predictive_uncertainty)
    for name in ("observations", "forward"):
        assert name in signature.parameters, (
            f"routed_predictive_uncertainty takes no {name!r}; the rule "
            f"'a_grid_result_predicts_on_evidence_or_says_it_did_not' needs it"
        )
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert signature.parameters[name].default is None
