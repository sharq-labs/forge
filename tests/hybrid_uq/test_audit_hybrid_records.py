"""Audit stream "hybrid": a serialized routed record states one truth, and its fields cannot move (HUQ-09, HUQ-12, HUQ-13).

HUQ-09  from_dict compared class, digest, claim and names, never the numbers: an identifiability report could
        contradict the carried covariance, and diagnostics could contradict the claim they sit under;
HUQ-12  non-finite means, an open grid_summary, predictive intervals unrelated to their sd and an estimate
        unrelated to its inference point were all read back;
HUQ-13  nested mappings were plain dicts after validation, so a validated record could be edited in place.

Digests in these records are integrity-only: anyone can recompute them. What makes a record authoritative is that
every claim in it is re-derived from the numbers it carries under the canonical thresholds, and these tests forge
records whose digests are recomputed to prove that is what is checked.
"""

from __future__ import annotations

import copy
import inspect
import json
import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    HybridUQError,
    HybridUQResult,
    LocalGaussianPosterior,
    MultistartPolicy,
    RouteDiagnostics,
    RoutedIdentifiability,
    RoutedPredictiveUncertainty,
    route_uncertainty,
)
from engcore.hybrid_uq import router as R
from engcore.hybrid_uq._records import encode_matrix, encode_vector


def _json(payload):
    return json.loads(json.dumps(payload))


@pytest.fixture(scope="module")
def local():
    P = S.affine()
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert result.claim.value == "SUPPORTED"
    return result


@pytest.fixture(scope="module")
def grid():
    P = S.affine()
    # A supplied grid narrower than the declared bounds now needs a uniqueness basis (R-06, re-audit
    # 2026-09-16), and the only basis a grid route can get is a search, which needs the calibration.
    # The record this returns is what the router produces for a properly posed request; what the tests
    # below do to it is unchanged.
    result = route_uncertainty(grid=P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]),
                               calibration=P.calibrate(), observations=P.observations, forward=P.forward)
    assert result.decision.value == "GRID_AS_SUPPLIED"
    return result


# ---------------------------------------------------------------------------
# HUQ-09: identifiability re-derived from the carried covariance
# ---------------------------------------------------------------------------
def _ident_numbers(p):
    report = p["identifiability"]["report"]
    report["max_abs_correlation"] = 0.0
    report["condition_number"] = 1.0
    report["relative_widths"] = [1e-9, 1e-9]


def _ident_status(p):
    p["identifiability"]["report"]["status"] = "PARAMETERS_NOT_IDENTIFIABLE"


def _ident_why(p):
    p["identifiability"]["report"]["why"] = "forged"


def _ident_thresholds(p):
    p["identifiability"]["report"]["width_threshold"] = 1.0e9


def _ident_numbers_explained(p):
    """A1 with its explanation rewritten to match the forged numbers, so only the covariance can refute it."""
    from engcore.hybrid_uq.identifiability import _rule

    _ident_numbers(p)
    report = p["identifiability"]["report"]
    status, why = _rule(report["condition_number"], report["max_abs_correlation"], report["relative_widths"],
                        report["parameter_names"], correlation_threshold=0.95, condition_threshold=1.0e6, width_threshold=1.0)
    report["status"], report["why"] = status.value, why + " [LOCAL_GAUSSIAN_APPROXIMATION in parameterization 'declared']"


@pytest.mark.parametrize("edit", [_ident_numbers, _ident_numbers_explained, _ident_status, _ident_why, _ident_thresholds],
                         ids=["A1_numbers", "A1_numbers_explained", "A1b_status", "why", "thresholds"])
def test_huq09_an_identifiability_report_the_covariance_does_not_produce_is_refused(local, edit):
    payload = _json(local.to_dict())
    edit(payload)
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


@pytest.mark.parametrize("edit", [_ident_status, _ident_why], ids=["status", "why"])
def test_huq09_a_standalone_verdict_must_follow_from_its_own_numbers(local, grid, edit):
    for result in (local, grid):
        payload = _json(result.to_dict())
        edit(payload)
        with pytest.raises(HybridUQError):
            RoutedIdentifiability.from_dict(payload["identifiability"])


# ---------------------------------------------------------------------------
# HUQ-09: route reasons re-derived from the measured diagnostics
# ---------------------------------------------------------------------------
def _diag(edit):
    def apply(p):
        edit(p["local_posterior"]["diagnostics"])
    return apply


DIAGNOSTIC_EDITS = {
    "nonlinearity": _diag(lambda d: d.update(nonlinearity_index=7.5)),
    "newton_step": _diag(lambda d: d.update(newton_step_in_sd=[12.0, -9.0])),
    "probes_skipped": _diag(lambda d: d.update(nonlinearity_probes_skipped=4)),
    "multistart_removed": _diag(lambda d: d.update(multistart=[], uniqueness="NOT_ASSESSED")),
    "multistart_truncated": _diag(lambda d: d.update(multistart=d["multistart"][:1])),
    "uniqueness_word": _diag(lambda d: d.update(uniqueness="SECOND_MODE_FOUND")),
    "rank": _diag(lambda d: d.update(jacobian_rank=1)),
    "condition": _diag(lambda d: d.update(jacobian_condition="inf")),
    "raw_condition": _diag(lambda d: d.update(raw_jacobian_condition=1.0e300)),
    "threshold_edited": _diag(lambda d: d["thresholds"].update(nonlinearity_refuse=1e9)),
    "negative_rise": _diag(lambda d: d.update(minimum_chi_square_rise=-3.0)),
    "near_bound": _diag(lambda d: d.update(near_bound=["theta1"])),
    "bound_distance": _diag(lambda d: d.update(minimum_bound_distance_sd=1.0)),
}


@pytest.mark.parametrize("name", sorted(DIAGNOSTIC_EDITS))
def test_huq09_diagnostics_that_contradict_their_claim_are_refused(local, name):
    payload = _json(local.to_dict())
    DIAGNOSTIC_EDITS[name](payload)
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)
    with pytest.raises(HybridUQError):
        RouteDiagnostics.from_dict(payload["local_posterior"]["diagnostics"]) if name not in (
            "near_bound", "bound_distance") else LocalGaussianPosterior.from_dict(payload["local_posterior"])


def test_huq09_a_consistently_rescaled_covariance_is_refused(local):
    payload = _json(local.to_dict())
    small = [[v * 1e-4 for v in row] for row in payload["covariance"]]
    payload["covariance"] = small
    payload["local_posterior"]["covariance"] = small
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


def test_huq09_a_legacy_route_with_every_probe_skipped_and_nonlinearity_zero_is_refused():
    """The state HUQ-10 fixed, written by the old code: DOWNGRADED, nonlinearity 0.0 over no evaluated probe."""
    from test_audit_hybrid_local_route import _tight_nonlinear

    P = _tight_nonlinear()
    from engcore.hybrid_uq import local_gaussian_posterior

    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    payload = _json(post.diagnostics.to_dict())
    assert payload["minimum_chi_square_rise"] == "inf"
    payload.update(nonlinearity_index=0.0, claim="DOWNGRADED",
                   refusals=[r for r in payload["refusals"] if r != "NONLINEAR_BEYOND_LOCAL_GAUSSIAN"])
    assert not payload["refusals"]
    with pytest.raises(HybridUQError):
        RouteDiagnostics.from_dict(payload)


# ---------------------------------------------------------------------------
# HUQ-09 / HUQ-12: grid records
# ---------------------------------------------------------------------------
def _recommit(payload, result):
    summary = payload["grid_summary"]
    arguments = {"route": summary["route"], "parameter_names": payload["parameter_names"], "grid_identity": summary["grid_digest"],
                 "mean": [float(v) for v in payload["mean"]],
                 "covariance": [[float(v) for v in row] for row in payload["covariance"]],
                 "dataset_id": summary["dataset_id"], "points": summary["points"]}
    accepted = inspect.signature(R._grid_moments_digest).parameters
    summary["moments_digest"] = R._grid_moments_digest(**{k: v for k, v in arguments.items() if k in accepted})


def test_huq09_grid_moments_forged_with_a_recomputed_commitment_are_refused(grid):
    payload = _json(grid.to_dict())
    mean = [v + 5.0 for v in grid.mean]
    cov = [[v * 1e-6 for v in row] for row in grid.covariance]
    payload["mean"], payload["covariance"] = encode_vector(mean), encode_matrix(cov)
    _recommit(payload, grid)
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


def test_huq09_a_grid_covariance_shrunk_under_a_recomputed_commitment_is_refused(grid):
    payload = _json(grid.to_dict())
    payload["covariance"] = encode_matrix([[v * 1e-6 for v in row] for row in grid.covariance])
    _recommit(payload, grid)
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


def test_huq12_a_non_finite_grid_mean_is_refused_even_with_a_recomputed_commitment(grid):
    payload = _json(grid.to_dict())
    payload["mean"] = ["nan", "inf"]
    summary = payload["grid_summary"]
    accepted = inspect.signature(R._grid_moments_digest).parameters
    arguments = {"route": summary["route"], "parameter_names": payload["parameter_names"], "grid_identity": summary["grid_digest"],
                 "mean": [math.nan, math.inf], "covariance": grid.covariance, "dataset_id": summary["dataset_id"],
                 "points": summary["points"]}
    try:
        summary["moments_digest"] = R._grid_moments_digest(**{k: v for k, v in arguments.items() if k in accepted})
    except (ValueError, HybridUQError):
        pass  # a commitment that cannot even be computed over a non-finite mean
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


@pytest.mark.parametrize("edit", [
    lambda s: s.update(dataset_id="another.dataset"),
    lambda s: s.update(points=10 ** 9),
    lambda s: s.update(certified_by="EXACT_POSTERIOR"),
], ids=["dataset_id", "points", "extra_key"])
def test_huq12_the_grid_summary_is_a_closed_committed_record(grid, edit):
    payload = _json(grid.to_dict())
    edit(payload["grid_summary"])
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


# ---------------------------------------------------------------------------
# HUQ-12: predictive and local records
# ---------------------------------------------------------------------------
PREDICTIVE = {"schema": "hybrid_uq.routed_predictive_uncertainty/1", "observation_key": "k", "unit": "dimensionless",
              "approximation_class": "LINEARIZED_PREDICTIVE_UQ", "exact": False, "mean": 1.0,
              "parameter_standard_uncertainty": 0.5, "measurement_standard_uncertainty": None,
              "total_standard_uncertainty": 0.5, "parameter_interval": [0.020018007729973, 1.979981992270027],
              "total_interval": [0.020018007729973, 1.979981992270027], "confidence_level": 0.95,
              "sources": ["PARAMETER_UNCERTAINTY", "MEASUREMENT_UNCERTAINTY", "MODEL_DISCREPANCY_NOT_MODELLED"],
              "model_discrepancy": "MODEL_DISCREPANCY_NOT_MODELLED", "posterior_digest": "x", "route_claim": "SUPPORTED",
              "reasons": [], "predictive_nonlinearity": 0.0}


def test_huq12_the_predictive_control_record_is_read():
    assert RoutedPredictiveUncertainty.from_dict(copy.deepcopy(PREDICTIVE)).mean == 1.0


@pytest.mark.parametrize("edit", [
    lambda p: p.update(mean="nan"),
    lambda p: p.update(total_interval=[-5.0, 900.0]),
    lambda p: p.update(parameter_interval=[0.9, 1.1]),
    lambda p: p.update(parameter_standard_uncertainty=0.0, total_standard_uncertainty=0.0, parameter_interval=[1.0, 1.0],
                       total_interval=[-5.0, 900.0]),
    lambda p: p.update(predictive_nonlinearity=0.9),
    lambda p: p.update(predictive_nonlinearity=None),
    lambda p: p.update(approximation_class="POSTERIOR_GRID", predictive_nonlinearity=None, total_interval=[-500.0, 900.0]),
], ids=["nan_mean", "total_interval", "parameter_interval", "P1", "nonlinearity_over_threshold", "nonlinearity_unmeasured",
        "grid_interval_beyond_any_distribution"])
def test_huq12_a_predictive_record_whose_numbers_contradict_each_other_is_refused(edit):
    payload = copy.deepcopy(PREDICTIVE)
    edit(payload)
    with pytest.raises(HybridUQError):
        RoutedPredictiveUncertainty.from_dict(payload)


def test_huq12_an_estimate_that_is_not_its_inference_point_is_refused(local):
    payload = _json(local.to_dict())
    payload["local_posterior"]["estimate"] = [123.0, -456.0]
    with pytest.raises(HybridUQError):
        LocalGaussianPosterior.from_dict(payload["local_posterior"])
    with pytest.raises(HybridUQError):
        HybridUQResult.from_dict(payload)


def test_huq12_a_routed_result_built_around_a_contradictory_posterior_is_refused_in_memory(local):
    import dataclasses

    moved = dataclasses.replace(local.local_posterior, estimate=(123.0, -456.0))
    with pytest.raises(HybridUQError, match="inference point"):
        dataclasses.replace(local, local_posterior=moved)


# ---------------------------------------------------------------------------
# HUQ-13: nothing validated can be edited in place
# ---------------------------------------------------------------------------
def test_huq13_nested_mappings_of_a_validated_record_are_immutable(local, grid):
    record = HybridUQResult.from_dict(_json(local.to_dict()))
    digest = record.digest
    with pytest.raises(TypeError):
        record.local_posterior.diagnostics.thresholds["nonlinearity_refuse"] = 1e9
    with pytest.raises(TypeError):
        record.considered[0]["outcome"] = "USED"
    with pytest.raises(TypeError):
        record.local_posterior.diagnostics.multistart[0]["classification"] = "SECOND_MODE"
    with pytest.raises(TypeError):
        grid.grid_summary["dataset_id"] = "mutated"
    assert record.digest == digest
    # the payload a caller receives is still theirs to edit, and editing it does not move the record
    payload = record.to_dict()
    payload["considered"][0]["outcome"] = "EDITED"
    payload["local_posterior"]["diagnostics"]["thresholds"]["probe_sd"] = 9.0
    assert record.digest == digest


def test_huq09_valid_records_of_every_route_still_round_trip(local, grid):
    F = S.strong_nonlinearity()
    rebuilt = route_uncertainty(calibration=F.calibrate(), observations=F.observations, forward=F.forward,
                                multistart=MultistartPolicy(), rebuild=GridRebuildPolicy(F.table_builder()))
    refused = route_uncertainty(calibration=F.calibrate(), observations=F.observations, forward=F.forward,
                                multistart=MultistartPolicy())
    downgraded = route_uncertainty(calibration=S.affine().calibrate(), observations=S.affine().observations,
                                   forward=S.affine().forward, multistart=None)
    for result in (local, grid, rebuilt, refused, downgraded):
        again = HybridUQResult.from_dict(_json(result.to_dict()))
        assert again.to_dict() == result.to_dict() and again.digest == result.digest
    ident = local.identifiability
    assert RoutedIdentifiability.from_dict(_json(ident.to_dict())).digest == ident.digest
