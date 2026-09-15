"""Predictive uncertainty from either route, with parameter and measurement uncertainty kept apart.

LINEARIZED_PREDICTIVE_UQ: mean g(z_hat), parameter variance diag(G Sigma G^T), measurement variance sigma^2,
total = the sum. Exact only when g is affine over the posterior; the +/-2 sd principal-axis probes compare g
with its linear extrapolation and downgrade when they disagree, and a probe that was not evaluated -- outside
the bounds, refused, or not run at all because ``check_nonlinearity=False`` -- downgrades too.

POSTERIOR_GRID: the frozen ``posterior_predictive_uq``, grid-resolution refusal included, re-expressed in the
same record. Model discrepancy is estimated by neither: every record names MODEL_DISCREPANCY_NOT_MODELLED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import norm

from ..inference.calibration import ForwardEvaluator
from ..inference.grid import AdmittedForwardTable, PosteriorGrid
from ..scientific.ir.problem import ModelReference
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity
from ..uq.predictive import PredictiveObservableSpec, posterior_predictive_uq
from ._records import decode_float, digest_of, encode_float, require_schema
from .local_gaussian import LocalGaussianPosterior, PROBE_SD
from .sensitivity import DEFAULT_RELATIVE_STEP, RouteRefusedError, central_difference, evaluate, to_natural
from .vocabulary import (
    MODEL_DISCREPANCY_NOT_MODELLED, UNCERTAINTY_SOURCES, ApproximationClass, HybridUQError, RouteClaim, RouteReason, claim_for,
)

ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA = "hybrid_uq.routed_predictive_uncertainty/1"
PREDICTIVE_NONLINEARITY_DOWNGRADE = 0.10


def grid_digest(posterior: PosteriorGrid) -> str:
    """Identity of a grid posterior: names, dataset, and the bytes of its points and weights."""
    import hashlib

    h = hashlib.sha256()
    h.update("\x00".join(posterior.parameter_names).encode("utf-8"))
    h.update(b"\x00" + str(posterior.dataset_id).encode("utf-8") + b"\x00")
    h.update(np.ascontiguousarray(posterior.points, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(posterior.weights, dtype="<f8").tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class RoutedPredictiveUncertainty:
    """One predicted quantity, its parameter and measurement uncertainty separately, and where it came from."""

    observation_key: str
    unit: str
    approximation_class: ApproximationClass
    mean: float
    parameter_standard_uncertainty: float
    measurement_standard_uncertainty: float | None
    total_standard_uncertainty: float
    parameter_interval: tuple[float, float]
    total_interval: tuple[float, float]
    confidence_level: float
    sources: tuple[str, ...]
    model_discrepancy: str
    posterior_digest: str
    route_claim: RouteClaim
    reasons: tuple[RouteReason, ...]
    predictive_nonlinearity: float | None

    def __post_init__(self) -> None:
        cls = ApproximationClass(self.approximation_class)
        if cls is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION:
            raise HybridUQError("a predictive record is LINEARIZED_PREDICTIVE_UQ or POSTERIOR_GRID, not a parameter approximation")
        object.__setattr__(self, "approximation_class", cls)
        claim = RouteClaim(self.route_claim)
        if claim is RouteClaim.REFUSED:
            raise HybridUQError("a refused route emits no predictive uncertainty")
        object.__setattr__(self, "route_claim", claim)
        reasons = tuple(sorted({RouteReason(r) for r in self.reasons}, key=lambda r: r.value))
        if claim_for(reasons) is not claim:
            raise HybridUQError(f"claim {claim.value} does not follow from reasons {[r.value for r in reasons]}")
        object.__setattr__(self, "reasons", reasons)
        if tuple(self.sources) != UNCERTAINTY_SOURCES:
            raise HybridUQError(f"a predictive record names exactly the sources {UNCERTAINTY_SOURCES}")
        object.__setattr__(self, "sources", tuple(self.sources))
        if self.model_discrepancy != MODEL_DISCREPANCY_NOT_MODELLED:
            raise HybridUQError("model discrepancy is not modelled by either route, and the record must say so")
        param = float(self.parameter_standard_uncertainty)
        meas = None if self.measurement_standard_uncertainty is None else float(self.measurement_standard_uncertainty)
        total = float(self.total_standard_uncertainty)
        if not (param >= 0.0 and math.isfinite(param)) or (meas is not None and not (meas > 0.0 and math.isfinite(meas))):
            raise HybridUQError("standard uncertainties must be finite and non-negative (measurement strictly positive)")
        if cls is ApproximationClass.LINEARIZED_PREDICTIVE_UQ:
            expected = math.sqrt(param ** 2 + (meas ** 2 if meas is not None else 0.0))
            if not math.isclose(total, expected, rel_tol=1e-12, abs_tol=0.0):
                raise HybridUQError("a linearized total is the root-sum-square of parameter and measurement uncertainty")
        elif total + 1e-12 * max(1.0, total) < param:
            raise HybridUQError("a total uncertainty cannot be smaller than its parameter part")
        for label in ("parameter_interval", "total_interval"):
            low, high = (float(v) for v in getattr(self, label))
            if not low <= high:
                raise HybridUQError(f"{label} is inverted")
            object.__setattr__(self, label, (low, high))
        if not 0.0 < float(self.confidence_level) < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA, "observation_key": self.observation_key, "unit": self.unit,
            "approximation_class": self.approximation_class.value, "exact": False, "mean": encode_float(self.mean),
            "parameter_standard_uncertainty": encode_float(self.parameter_standard_uncertainty),
            "measurement_standard_uncertainty": None if self.measurement_standard_uncertainty is None
            else encode_float(self.measurement_standard_uncertainty),
            "total_standard_uncertainty": encode_float(self.total_standard_uncertainty),
            "parameter_interval": [encode_float(v) for v in self.parameter_interval],
            "total_interval": [encode_float(v) for v in self.total_interval],
            "confidence_level": float(self.confidence_level), "sources": list(self.sources),
            "model_discrepancy": self.model_discrepancy, "posterior_digest": self.posterior_digest,
            "route_claim": self.route_claim.value, "reasons": [r.value for r in self.reasons],
            "predictive_nonlinearity": None if self.predictive_nonlinearity is None else encode_float(self.predictive_nonlinearity),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutedPredictiveUncertainty":
        require_schema(payload, ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA)
        if payload.get("exact") is not False:
            raise HybridUQError("a predictive record claiming to be exact is refused")
        meas = payload["measurement_standard_uncertainty"]
        nonlin = payload["predictive_nonlinearity"]
        return cls(
            observation_key=payload["observation_key"], unit=payload["unit"],
            approximation_class=ApproximationClass(payload["approximation_class"]), mean=decode_float(payload["mean"]),
            parameter_standard_uncertainty=decode_float(payload["parameter_standard_uncertainty"]),
            measurement_standard_uncertainty=None if meas is None else decode_float(meas),
            total_standard_uncertainty=decode_float(payload["total_standard_uncertainty"]),
            parameter_interval=tuple(decode_float(v) for v in payload["parameter_interval"]),
            total_interval=tuple(decode_float(v) for v in payload["total_interval"]),
            confidence_level=float(payload["confidence_level"]), sources=tuple(payload["sources"]),
            model_discrepancy=payload["model_discrepancy"], posterior_digest=payload["posterior_digest"],
            route_claim=RouteClaim(payload["route_claim"]), reasons=tuple(RouteReason(r) for r in payload["reasons"]),
            predictive_nonlinearity=None if nonlin is None else decode_float(nonlin),
        )

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())


def linearized_predictive_uq(
    posterior: LocalGaussianPosterior,
    predict: ForwardEvaluator,
    specs: Sequence[PredictiveObservableSpec],
    *,
    confidence_level: float = 0.95,
    check_nonlinearity: bool = True,
) -> tuple[RoutedPredictiveUncertainty, ...]:
    """Linearized predictive uncertainty from a local Gaussian posterior. Refuses a refused posterior."""
    if not isinstance(posterior, LocalGaussianPosterior):
        raise HybridUQError("linearized_predictive_uq takes a LocalGaussianPosterior")
    cov = posterior._require_numbers()
    if posterior.parameterization != "declared":
        raise HybridUQError("predict from the declared parameterization: a linearly mapped posterior has no forward model")
    specs = tuple(specs)
    if not specs or not all(isinstance(s, PredictiveObservableSpec) for s in specs):
        raise HybridUQError("linearized_predictive_uq takes one or more PredictiveObservableSpec")
    level = float(confidence_level)
    if not 0.0 < level < 1.0:
        raise HybridUQError("confidence_level must lie strictly between 0 and 1")
    keys = tuple(s.observation_key for s in specs)
    units = tuple(s.unit for s in specs)
    references = tuple(Quantity(0.0, u) for u in units)
    transforms = posterior.inference_transforms
    z0 = np.asarray(posterior.inference_point)
    lower, upper = np.asarray(posterior.lower_bounds), np.asarray(posterior.upper_bounds)

    def g(z):
        return evaluate(predict, to_natural(z, transforms), keys, units, references)

    measurement = [None if s.observation_sigma is None else float(s.observation_sigma.magnitude_in(s.unit)) for s in specs]
    try:
        g0, G, _steps, _one_sided, _count = central_difference(
            g, z0, lower, upper, DEFAULT_RELATIVE_STEP, weights=[math.nan if m is None else m for m in measurement])
    except RouteRefusedError as exc:
        raise RouteRefusedError(f"the predictive derivative could not be established near the estimate: {exc}") from None
    parameter_var = np.einsum("ij,jk,ik->i", G, cov, G)
    # g Sigma g^T of a valid covariance is non-negative up to roundoff, which is bounded by |g| |Sigma| |g|^T. A
    # variance below that bound is a defect in the covariance and raises; it is never turned into zero uncertainty.
    roundoff = 64.0 * float(np.finfo(float).eps) * np.einsum("ij,jk,ik->i", np.abs(G), np.abs(cov), np.abs(G))
    if np.any(parameter_var < -roundoff):
        worst = int(np.argmin(parameter_var + roundoff))
        raise HybridUQError(f"the parameter variance of {keys[worst]!r} is {float(parameter_var[worst]):.3g}, negative beyond "
                            f"roundoff ({float(-roundoff[worst]):.3g}): the posterior covariance is not a covariance")
    parameter_var = np.maximum(parameter_var, 0.0)
    parameter_sd = np.sqrt(parameter_var)
    total_sd = np.asarray([math.sqrt(parameter_var[i] + (m ** 2 if m is not None else 0.0)) for i, m in enumerate(measurement)])

    nonlinearity = None
    skipped = 0
    if check_nonlinearity:
        # The largest deviation over the probes that were evaluated. A probe outside the declared bounds or
        # refused by the predictive model was not evaluated, so it is counted, not read as agreement: the
        # nonlinearity it would have measured is unknown, and 0.0 over no probes is not evidence of linearity.
        nonlinearity = 0.0
        lam, vec = np.linalg.eigh(cov)
        for k in range(len(z0)):
            delta = PROBE_SD * math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k]
            for sign in (1.0, -1.0):
                point = z0 + sign * delta
                if np.any(point < lower) or np.any(point > upper):
                    skipped += 1
                    continue
                value = g(point)
                if value is None:
                    skipped += 1
                    continue
                scale = np.where(total_sd > 0.0, total_sd, 1.0)
                nonlinearity = max(nonlinearity, float(np.max(np.abs(value - (g0 + sign * G @ delta)) / scale)))
    else:
        # A caller who chooses not to measure linearity has not shown it: every probe counts as not evaluated, so
        # the claim is capped at DOWNGRADED. predictive_nonlinearity stays None, which says nothing was measured.
        skipped = 2 * len(z0)
    reasons = set(posterior.diagnostics.downgrades)
    if nonlinearity is not None and nonlinearity > PREDICTIVE_NONLINEARITY_DOWNGRADE:
        reasons.add(RouteReason.PREDICTIVE_NONLINEAR)
    if skipped:
        reasons.add(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)
    claim = claim_for(reasons)
    q = float(norm.ppf(0.5 + level / 2.0))
    out = []
    for i, spec in enumerate(specs):
        out.append(RoutedPredictiveUncertainty(
            observation_key=spec.observation_key, unit=spec.unit, approximation_class=ApproximationClass.LINEARIZED_PREDICTIVE_UQ,
            mean=float(g0[i]), parameter_standard_uncertainty=float(parameter_sd[i]),
            measurement_standard_uncertainty=measurement[i], total_standard_uncertainty=float(total_sd[i]),
            parameter_interval=(float(g0[i] - q * parameter_sd[i]), float(g0[i] + q * parameter_sd[i])),
            total_interval=(float(g0[i] - q * total_sd[i]), float(g0[i] + q * total_sd[i])), confidence_level=level,
            sources=UNCERTAINTY_SOURCES, model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED, posterior_digest=posterior.digest,
            route_claim=claim, reasons=tuple(reasons), predictive_nonlinearity=nonlinearity,
        ))
    return tuple(out)


def grid_predictive_uncertainty(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    spec: PredictiveObservableSpec,
    *,
    twin: TwinReference,
    model: ModelReference,
    source_ref: str,
    confidence_level: float = 0.95,
) -> RoutedPredictiveUncertainty:
    """The frozen grid predictive, grid-resolution refusal included, in the V2 record."""
    result = posterior_predictive_uq(posterior, predictive_table, spec, twin=twin, model=model, source_ref=source_ref,
                                     credible_mass=confidence_level)
    unit = result.mean.units
    measurement = None if spec.observation_sigma is None else float(spec.observation_sigma.magnitude_in(unit))
    return RoutedPredictiveUncertainty(
        observation_key=result.observation_key, unit=unit, approximation_class=ApproximationClass.POSTERIOR_GRID,
        mean=float(result.mean.magnitude), parameter_standard_uncertainty=float(result.epistemic_standard_uncertainty.magnitude_in(unit)),
        measurement_standard_uncertainty=measurement,
        total_standard_uncertainty=float(result.total_standard_uncertainty.magnitude_in(unit)),
        parameter_interval=(float(result.epistemic_interval.lower.magnitude_in(unit)), float(result.epistemic_interval.upper.magnitude_in(unit))),
        total_interval=(float(result.total_interval.lower.magnitude_in(unit)), float(result.total_interval.upper.magnitude_in(unit))),
        confidence_level=result.confidence_level, sources=UNCERTAINTY_SOURCES, model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED,
        posterior_digest=grid_digest(posterior), route_claim=RouteClaim.SUPPORTED, reasons=(), predictive_nonlinearity=None,
    )
