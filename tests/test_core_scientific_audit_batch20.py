"""Batch 20 of the 2026-09-16 core re-audit: the route's verdict stops depending on declared units (I-08 part A).

I-08 is five problems over the local route's probes. This part takes the two that are one claim: **the
route's verdict must not depend on the units a parameter is declared in.**

* **R-16.** The probe directions come from `eigh(cov)` in DECLARED units. A covariance's eigenvectors rotate
  under a per-parameter unit change, so the tested directions move with the units: the same model and data
  are SUPPORTED with a parameter in volts and REFUSED (TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN) in millivolts.
* **R-26.** POORLY_SCALED_PARAMETERIZATION is emitted from the RAW condition number, which any caller can
  move by any factor with a smaller unit. Declaring a slope in nanovolts (raw 3.19e9, equilibrated 3.47)
  downgrades an exactly Gaussian result.

The audited reproductions are I-15's conformance cases
(`tests/hybrid_uq/test_core_v4_false_confidence_conformance.py::test_r16_...` and `::test_r26_...`), committed
as strict xfails in batch 6's `5a08eef` and confirmed at this batch's baseline to fail on their own
assertions. What is here is the rule each fix stands on, stated where it can be read alone. Preregistered in
`benchmarks/core_v4_false_confidence/BATCH20_THRESHOLD_PROTOCOL.json`.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from engcore.hybrid_uq import MultistartPolicy, RouteClaim, RouteReason
from engcore.hybrid_uq.vocabulary import HybridUQError


def _module():
    import engcore.hybrid_uq.local_gaussian as module

    return module


def _cases():
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[1] / "tests" / "hybrid_uq"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import false_confidence_cases as F

    return F


def _local(problem, multistart=None):
    from engcore.hybrid_uq import local_gaussian_posterior

    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=multistart if multistart is not None else MultistartPolicy())


def _basis(module, cov):
    """The p unit-Mahalanobis probe axes, whatever the module calls the helper that builds them."""
    builder = getattr(module, "_invariant_basis", None)
    assert builder is not None, "local_gaussian._invariant_basis builds the unit-invariant probe basis"
    lam, vec = builder(np.asarray(cov, dtype=float))
    return [math.sqrt(max(float(lam[k]), 0.0)) * np.asarray(vec)[:, k] for k in range(len(lam))]


CORRELATED = np.array([[4.0, 1.8], [1.8, 1.0]])


# =====================================================================
# R-16: the probe basis
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r16_every_probe_axis_has_mahalanobis_length_one():
    """The property the old basis had and the new one must keep: a Gaussian predicts the same rise on each."""
    module = _module()
    inverse = np.linalg.inv(CORRELATED)
    for delta in _basis(module, CORRELATED):
        assert float(delta @ inverse @ delta) == pytest.approx(1.0, rel=1e-12)


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r16_the_basis_is_the_same_points_under_a_diagonal_reparameterization():
    """R-16's rule. Under z -> S z the basis must transform to S @ delta: the SAME points in parameter space.

    The old `eigh(cov)` basis does not: a covariance's eigenvectors rotate under a per-parameter rescaling,
    which is why the tested directions moved with the declared units.
    """
    module = _module()
    scale = np.array([1.0, 1000.0])
    declared = _basis(module, CORRELATED)
    restated = _basis(module, np.outer(scale, scale) * CORRELATED)
    # match by direction, up to the sign and order eigen-decompositions are free to choose
    for delta in declared:
        want = scale * delta
        assert any(np.allclose(want, other, rtol=1e-9, atol=0.0) or np.allclose(want, -other, rtol=1e-9, atol=0.0)
                   for other in restated), (want, restated)


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r16_an_uncorrelated_posterior_keeps_exactly_the_probes_it_had():
    """The fix moves a correlated posterior's probes and nothing else: at R = I the two bases are identical."""
    module = _module()
    cov = np.diag([4.0, 0.25, 9.0])
    sd = np.sqrt(np.diag(cov))
    got = _basis(module, cov)
    for k in range(3):
        want = np.zeros(3)
        want[k] = sd[k]
        assert any(np.allclose(want, other, atol=1e-12) or np.allclose(want, -other, atol=1e-12) for other in got), k


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r16_restating_a_unit_moves_no_dimensionless_diagnostic():
    """The audited case, with every dimensionless diagnostic checked rather than two of them."""
    F = _cases()
    declared = _local(F.coupled_off_axis_flat_tail(1.0, "B20_declared"))
    restated = _local(F.coupled_off_axis_flat_tail(2.0, "B20_restated"))
    assert restated.claim is declared.claim, (declared.claim.value, restated.claim.value)
    for label in ("nonlinearity_index", "minimum_chi_square_rise", "minimum_tail_rise_ratio", "jacobian_condition"):
        a, b = float(getattr(declared.diagnostics, label)), float(getattr(restated.diagnostics, label))
        assert abs(b - a) <= 1.0e-6 * max(abs(a), 1.0), f"{label} moved from {a:.6g} to {b:.6g}"
    for label in ("nonlinearity_probes_skipped", "tail_probes_skipped"):
        assert int(getattr(restated.diagnostics, label)) == int(getattr(declared.diagnostics, label)), label


# Already held at the baseline and unmarked at preregistration: the raw condition was always recorded.
# It is kept because the fix STOPS reading it for a claim, and a number nobody reads is a number that
# quietly stops being computed.
def test_r16_the_raw_condition_number_is_the_one_diagnostic_that_must_move():
    """It is unit-dependent by definition, and recording it is the whole of what it is for."""
    F = _cases()
    declared = _local(F.rescaled_slope(1.0, "B20_volt"))
    restated = _local(F.rescaled_slope(1.0e9, "B20_nanovolt"))
    assert float(restated.diagnostics.raw_jacobian_condition) > 1.0e3 * float(
        declared.diagnostics.raw_jacobian_condition)
    assert math.isfinite(float(restated.diagnostics.raw_jacobian_condition))


# =====================================================================
# R-26: the scaling downgrade
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r26_the_limit_is_the_two_constants_this_module_already_declares():
    """eps*kappa^2 = 1 is the refusal; eps*kappa^2 = NONLINEARITY_DOWNGRADE is the downgrade. No new number."""
    module = _module()
    limit = getattr(module, "POORLY_SCALED_CONDITION_LIMIT", None)
    assert limit is not None, "the scaling downgrade needs a scale-free limit to be judged against"
    assert float(limit) == pytest.approx(
        math.sqrt(module.NONLINEARITY_DOWNGRADE) * module.NUMERICAL_CONDITION_LIMIT, rel=1e-15)
    assert float(limit) == pytest.approx(21221686.1426478, rel=1e-12)
    assert float(limit) < module.NUMERICAL_CONDITION_LIMIT, "the downgrade sits below the refusal"


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r26_a_smaller_unit_no_longer_downgrades_an_exactly_gaussian_result():
    """The audited case: raw condition 3.19e9, equilibrated 3.47, exactly Gaussian."""
    F = _cases()
    restated = _local(F.rescaled_slope(1.0e9, "B20_nanovolt_claim"))
    assert float(restated.diagnostics.jacobian_condition) < 1.0e3
    assert RouteReason.POORLY_SCALED_PARAMETERIZATION not in restated.diagnostics.downgrades, (
        [r.value for r in restated.reasons])
    assert restated.claim is RouteClaim.SUPPORTED, [r.value for r in restated.reasons]


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r26_an_equilibrated_condition_above_the_limit_must_carry_the_downgrade():
    """Read-back, both ways: the rule the route emits by is the rule a record is read by."""
    F = _cases()
    module = _module()
    good = _local(F.rescaled_slope(1.0, "B20_readback")).diagnostics
    assert RouteReason.POORLY_SCALED_PARAMETERIZATION not in good.downgrades
    above = 1.5 * float(module.POORLY_SCALED_CONDITION_LIMIT)
    with pytest.raises(HybridUQError):
        dataclasses.replace(good, jacobian_condition=above)
    carried = dataclasses.replace(
        good, jacobian_condition=above,
        downgrades=tuple(good.downgrades) + (RouteReason.POORLY_SCALED_PARAMETERIZATION,),
        claim=RouteClaim.DOWNGRADED)
    assert RouteReason.POORLY_SCALED_PARAMETERIZATION in carried.downgrades


@pytest.mark.xfail(strict=True, reason="I-08 part A not implemented yet (batch 20 preregistration)")
def test_r26_a_large_raw_condition_alone_may_not_be_read_back_as_a_downgrade():
    """The other direction of the same rule: the record may not carry a reason its numbers do not imply."""
    F = _cases()
    good = _local(F.rescaled_slope(1.0e9, "B20_readback_raw")).diagnostics
    assert float(good.raw_jacobian_condition) > 1.0e8
    with pytest.raises(HybridUQError):
        dataclasses.replace(good, downgrades=tuple(good.downgrades) + (RouteReason.POORLY_SCALED_PARAMETERIZATION,),
                            claim=RouteClaim.DOWNGRADED)


# Already raised at the baseline and unmarked at preregistration -- but for the opposite reason: the old
# rule FORCED the downgrade on a NaN raw condition, so a record without the downgrade contradicted its
# own numbers. The record is still refused after the fix, now as a record that does not carry a number
# it claims to record. The test pins the refusal; the audit document states which rule refuses it.
def test_r26_a_record_that_does_not_carry_its_raw_condition_is_refused():
    """It was a forced downgrade, which is a statement about the evidence for a fact about the record."""
    F = _cases()
    good = _local(F.rescaled_slope(1.0, "B20_readback_nan")).diagnostics
    with pytest.raises(HybridUQError):
        dataclasses.replace(good, raw_jacobian_condition=math.nan)


# Already held at the baseline and unmarked at preregistration: it is the no-regression guard on the one
# compatibility decision this batch makes -- the new constant stays OUT of the serialized thresholds map.
def test_r26_the_recorded_thresholds_map_gains_no_key():
    """It is re-derived exactly on read-back, so a new key would refuse every record ever written."""
    module = _module()
    assert set(module._thresholds()) == {
        "nonlinearity_downgrade", "nonlinearity_refuse", "bound_downgrade_sd", "stationarity_sd",
        "at_bound_relative", "numerical_condition_limit", "probe_sd", "goodness_of_fit_alpha",
        "misfit_refuse_variance_ratio", "tail_probe_sd_inner", "tail_probe_sd_outer", "tail_downgrade_ratio",
        "tail_refuse_ratio",
    }
