"""Core V2 records: explicit schemas, round trips, unknown-schema refusal, material identity, fresh-process digests."""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
import subprocess
import sys

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    ApproximationClass,
    HybridUQError,
    HybridUQResult,
    LocalGaussianPosterior,
    LocalSensitivity,
    MultistartPolicy,
    ParameterInterval,
    RouteClaim,
    RoutedIdentifiability,
    RoutedPredictiveUncertainty,
    RouteDiagnostics,
    assess_routed_identifiability,
    linearized_predictive_uq,
    local_gaussian_posterior,
    reconstruct_local_sensitivity,
    route_uncertainty,
)
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

HERE = pathlib.Path(__file__).resolve().parent


def _canonical(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


@pytest.fixture(scope="module")
def records():
    P = S.affine()
    cal = P.calibrate()
    sensitivity = reconstruct_local_sensitivity(cal, P.observations, P.forward)
    posterior = local_gaussian_posterior(cal, P.observations, P.forward, multistart=MultistartPolicy(), sensitivity=sensitivity)
    spec = PredictiveObservableSpec("y@0.5", "dimensionless", Quantity(0.05, "dimensionless"))
    predictive = linearized_predictive_uq(posterior, lambda t: [Quantity(t[0] + 0.5 * t[1], "dimensionless")], [spec])[0]
    refused_problem = S.strong_nonlinearity()
    refused = local_gaussian_posterior(refused_problem.calibrate(), refused_problem.observations, refused_problem.forward,
                                       multistart=MultistartPolicy())
    routed = route_uncertainty(calibration=cal, observations=P.observations, forward=P.forward, multistart=MultistartPolicy())
    refused_route = route_uncertainty(calibration=refused_problem.calibrate(), observations=refused_problem.observations,
                                      forward=refused_problem.forward, multistart=MultistartPolicy())
    return {
        LocalSensitivity: sensitivity, MultistartPolicy: MultistartPolicy(starts=4), RouteDiagnostics: posterior.diagnostics,
        ParameterInterval: posterior.intervals()[0], LocalGaussianPosterior: posterior, RoutedIdentifiability: assess_routed_identifiability(posterior),
        RoutedPredictiveUncertainty: predictive, HybridUQResult: routed, "refused_posterior": refused, "refused_route": refused_route,
    }


RECORD_TYPES = [LocalSensitivity, MultistartPolicy, RouteDiagnostics, ParameterInterval, LocalGaussianPosterior,
                RoutedIdentifiability, RoutedPredictiveUncertainty, HybridUQResult]


@pytest.mark.parametrize("kind", RECORD_TYPES, ids=lambda k: k.__name__)
def test_every_v2_record_round_trips_byte_identically(records, kind):
    record = records[kind]
    first = _canonical(record.to_dict())
    again = kind.from_dict(json.loads(first.decode("utf-8")))
    assert _canonical(again.to_dict()) == first
    if hasattr(record, "digest"):
        assert again.digest == record.digest


@pytest.mark.parametrize("key", ["refused_posterior", "refused_route"])
def test_refused_records_round_trip_and_still_carry_no_numbers(records, key):
    record = records[key]
    kind = type(record)
    again = kind.from_dict(json.loads(_canonical(record.to_dict()).decode("utf-8")))
    assert again.covariance is None
    assert _canonical(again.to_dict()) == _canonical(record.to_dict())


@pytest.mark.parametrize("kind", RECORD_TYPES, ids=lambda k: k.__name__)
def test_every_v2_reader_refuses_an_unknown_schema(records, kind):
    payload = records[kind].to_dict()
    name, _, version = payload["schema"].rpartition("/")
    for bad in (f"{name}/{int(version) + 1}", f"{name}/0", "hybrid_uq.something_else/1", None):
        tampered = dict(payload, schema=bad)
        with pytest.raises(HybridUQError, match="unsupported schema"):
            kind.from_dict(tampered)


@pytest.mark.parametrize("kind", [LocalGaussianPosterior, RoutedPredictiveUncertainty, HybridUQResult], ids=lambda k: k.__name__)
def test_a_record_claiming_exactness_is_refused_on_read(records, kind):
    payload = records[kind].to_dict()
    flag = "exact" if kind is RoutedPredictiveUncertainty else "exact_posterior"
    assert payload[flag] is False
    with pytest.raises(HybridUQError, match="exact"):
        kind.from_dict(dict(payload, **{flag: True}))


def test_no_approximation_class_is_an_exact_posterior(records):
    assert all(member.exact_posterior is False for member in ApproximationClass)
    assert records[LocalGaussianPosterior].exact_posterior is False
    assert records[HybridUQResult].exact_posterior is False


def test_non_finite_diagnostics_survive_a_round_trip(records):
    refused = records["refused_posterior"]
    data = RouteDiagnostics.from_dict(json.loads(_canonical(records[LocalGaussianPosterior].diagnostics.to_dict()).decode()))
    assert data.minimum_chi_square_rise == records[LocalGaussianPosterior].diagnostics.minimum_chi_square_rise
    empty = RouteDiagnostics.from_dict(json.loads(_canonical(refused.diagnostics.to_dict()).decode()))
    assert empty.claim is RouteClaim.REFUSED


# ---------------------------------------------------------------------------
# identity: material fields move the digest, non-material ones do not
# ---------------------------------------------------------------------------
def test_material_fields_of_the_local_posterior_move_its_digest(records):
    posterior = records[LocalGaussianPosterior]
    base = posterior.digest
    cov = np.asarray(posterior.covariance)
    changes = {
        "covariance": tuple(map(tuple, cov * 1.01)),
        "estimate": tuple(v + 1e-9 for v in posterior.estimate),
        "inference_point": tuple(v + 1e-9 for v in posterior.inference_point),
        "parameterization": "linear_map:other",
        "parameterization_digest": "0" * 64,
        "parameter_units": ("volt", "volt"),
        "dataset_id": "another-dataset",
        "sensitivity_digest": "f" * 64,
    }
    for field, value in changes.items():
        assert dataclasses.replace(posterior, **{field: value}).digest != base, field


def test_evaluation_counts_are_not_material(records):
    diagnostics = records[RouteDiagnostics]
    assert dataclasses.replace(diagnostics, evaluation_count=diagnostics.evaluation_count + 999).digest == diagnostics.digest
    sensitivity = records[LocalSensitivity]
    assert dataclasses.replace(sensitivity, evaluation_count=sensitivity.evaluation_count + 7).digest == sensitivity.digest


def test_material_diagnostics_move_the_diagnostics_digest(records):
    diagnostics = records[RouteDiagnostics]
    assert dataclasses.replace(diagnostics, nonlinearity_index=diagnostics.nonlinearity_index + 0.01).digest != diagnostics.digest
    # The multistart policy recorded among the thresholds is material. This edited nonlinearity_refuse to 0.9 before
    # audit HUQ-09; the declared thresholds are constants now, and a record carrying another value is refused.
    thresholds = dict(diagnostics.thresholds, multistart_max_evaluations=4000.0)
    assert dataclasses.replace(diagnostics, thresholds=thresholds).digest != diagnostics.digest
    with pytest.raises(HybridUQError, match="not the declared"):
        dataclasses.replace(diagnostics, thresholds=dict(diagnostics.thresholds, nonlinearity_refuse=0.9))


def test_two_parameterizations_of_one_posterior_never_share_an_identity(records):
    posterior = records[LocalGaussianPosterior]
    differences = posterior.reparameterized([[1.0, 0.0], [-1.0, 1.0]], ("intercept", "difference"), ("dimensionless",) * 2, "difference")
    scaled = posterior.reparameterized([[2.0, 0.0], [0.0, 1.0]], ("intercept", "slope"), ("dimensionless",) * 2, "scaled")
    same_matrix_other_label = posterior.reparameterized([[1.0, 0.0], [-1.0, 1.0]], ("intercept", "difference"), ("dimensionless",) * 2, "renamed")
    identities = {posterior.parameterization_digest, differences.parameterization_digest, scaled.parameterization_digest,
                  same_matrix_other_label.parameterization_digest}
    assert len(identities) == 4
    assert len({posterior.digest, differences.digest, scaled.digest, same_matrix_other_label.digest}) == 4
    assert assess_routed_identifiability(differences).parameterization_digest == differences.parameterization_digest


def test_predictive_material_fields_move_its_digest(records):
    predictive = records[RoutedPredictiveUncertainty]
    # A linearized interval IS mean +/- q sd (audit HUQ-12), so a moved mean or level moves its intervals with it; this
    # edited one field at a time before, which now makes a record that contradicts itself and is refused.
    from scipy.stats import norm

    def moved(mean=predictive.mean, level=predictive.confidence_level):
        q = float(norm.ppf(0.5 + level / 2.0))
        p, t = predictive.parameter_standard_uncertainty, predictive.total_standard_uncertainty
        return dict(mean=mean, confidence_level=level, parameter_interval=(mean - q * p, mean + q * p),
                    total_interval=(mean - q * t, mean + q * t))

    for label, change in {"mean": moved(mean=predictive.mean + 1e-9), "posterior_digest": {"posterior_digest": "0" * 64},
                          "confidence_level": moved(level=0.9)}.items():
        assert dataclasses.replace(predictive, **change).digest != predictive.digest, label
    with pytest.raises(HybridUQError, match="mean \\+/-"):
        dataclasses.replace(predictive, parameter_interval=(predictive.parameter_interval[0] - 1e-9, predictive.parameter_interval[1]))


# ---------------------------------------------------------------------------
# fresh-process digest stability
# ---------------------------------------------------------------------------
def test_digests_are_stable_in_a_fresh_process_with_another_hash_seed(records):
    # The fresh process must import THIS tree's engcore. pytest's pythonpath setting does not reach a subprocess, and
    # without the explicit insert an editable install of another checkout answers instead, so the digests compared
    # would be another tree's (seen during the audit, when the V2 digests had legitimately moved).
    script = f"""
import sys, json
sys.path.insert(0, {str(HERE.parents[1] / "src")!r})
sys.path.insert(1, {str(HERE)!r})
import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, local_gaussian_posterior, assess_routed_identifiability, route_uncertainty
P = S.affine(); cal = P.calibrate()
post = local_gaussian_posterior(cal, P.observations, P.forward, multistart=MultistartPolicy())
routed = route_uncertainty(calibration=cal, observations=P.observations, forward=P.forward, multistart=MultistartPolicy())
print(json.dumps([post.digest, post.diagnostics.digest, assess_routed_identifiability(post).digest, routed.digest, MultistartPolicy(starts=4).digest]))
"""
    import os

    env = dict(os.environ, PYTHONHASHSEED="12345")
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", script], capture_output=True, text=True, env=env, check=True)
    fresh = json.loads(out.stdout.strip().splitlines()[-1])
    posterior = records[LocalGaussianPosterior]
    assert fresh == [posterior.digest, posterior.diagnostics.digest, records[RoutedIdentifiability].digest,
                     records[HybridUQResult].digest, records[MultistartPolicy].digest]


def test_the_rebuild_policy_is_export_only():
    from engcore.hybrid_uq import GridRebuildPolicy

    policy = GridRebuildPolicy(table_builder=lambda points: None)
    assert "table_builder" in policy.to_dict()
    assert not hasattr(GridRebuildPolicy, "from_dict")
