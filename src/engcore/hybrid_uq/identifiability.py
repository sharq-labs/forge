"""Identifiability for either route, under the frozen V1 thresholds and the frozen V1 classification rule.

For a grid it IS the frozen ``assess_identifiability``, refusals included. For the local route it applies the
same rule to the Gaussian: covariance condition number, largest absolute correlation, and each marginal 95%
width divided by the estimate, with Gaussian marginal intervals in inference coordinates in place of the
grid's discrete ones. The verdict is therefore stated in a parameterization, and the record says which.

Route validity is not identifiability. A SUPPORTED route may report NOT_IDENTIFIABLE; a REFUSED route reports
no identifiability at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import norm

from ..inference.calibration import IdentifiabilityReport, IdentifiabilityStatus, assess_identifiability
from ..inference.grid import PosteriorGrid
from ._records import decode_float, decode_vector, digest_of, encode_float, encode_vector, require_schema
from .local_gaussian import LocalGaussianPosterior
from .vocabulary import ApproximationClass, HybridUQError, RouteClaim

ROUTED_IDENTIFIABILITY_SCHEMA = "hybrid_uq.routed_identifiability/1"


def grid_parameterization_digest(posterior: PosteriorGrid) -> str:
    """The identity of a grid's coordinates: its parameter names, in order, and its dataset."""
    return _grid_axes_digest(posterior.parameter_names)


def _grid_axes_digest(parameter_names: Sequence[str]) -> str:
    """The same identity from the names alone, so a record without its grid can still be checked against it."""
    return digest_of({"grid_parameter_names": list(parameter_names), "label": "grid_axes"})


def classify(mean: Sequence[float], covariance, lows: Sequence[float], highs: Sequence[float],
             names: Sequence[str], *, correlation_threshold: float, condition_threshold: float,
             width_threshold: float) -> tuple[IdentifiabilityStatus, float, float, tuple[float, ...], str]:
    """The frozen V1 rule, over any covariance and any marginal intervals. Private to V2."""
    cov = np.asarray(covariance, dtype=np.float64)
    n = cov.shape[0]
    eigenvalues = np.linalg.eigvalsh(cov)
    smallest, largest = float(np.min(eigenvalues)), float(np.max(eigenvalues))
    condition = math.inf if smallest <= 0.0 else largest / smallest
    sd = np.sqrt(np.diag(cov))
    correlation = cov / np.outer(sd, sd)
    off = [abs(float(correlation[i, j])) for i in range(n) for j in range(n) if i != j]
    max_correlation = max(off) if off else 0.0
    widths = []
    for i in range(n):
        scale = abs(float(mean[i]))
        widths.append((highs[i] - lows[i]) / scale if scale > 0.0 else math.inf)
    reasons = []
    if not math.isfinite(condition) or condition > condition_threshold:
        reasons.append(f"posterior covariance condition number {condition:.3g} exceeds {condition_threshold:.3g}")
    if max_correlation > correlation_threshold:
        reasons.append(f"parameters are correlated at {max_correlation:.4f}, above {correlation_threshold}")
    over_wide = [names[i] for i, w in enumerate(widths) if not math.isfinite(w) or w > width_threshold]
    if over_wide:
        reasons.append(f"the 95% interval is wider than the estimate itself for {over_wide!r}")
    widest = max(widths) if widths else math.inf
    if over_wide:
        status = IdentifiabilityStatus.NOT_IDENTIFIABLE
        why = "a parameter's 95% interval is wider than the parameter itself, so the data do not determine it: " + "; ".join(reasons)
    elif not reasons:
        status = IdentifiabilityStatus.IDENTIFIABLE
        why = (f"every parameter's 95% interval is small relative to its own value (widest {widest:.3g}, threshold "
               f"{width_threshold:.3g}), and neither the correlation ({max_correlation:.4f}) nor the conditioning "
               f"({condition:.3g}) reaches its threshold")
    elif len(reasons) >= 2:
        status = IdentifiabilityStatus.NOT_IDENTIFIABLE
        why = "; ".join(reasons)
    else:
        status = IdentifiabilityStatus.WEAKLY_IDENTIFIABLE
        why = (f"{reasons[0]}, but every marginal interval is still narrower than its own parameter (widest {widest:.3g}): "
               f"the posterior is a ridge, and the data constrain along it but weakly across it")
    if status is IdentifiabilityStatus.IDENTIFIABLE and max_correlation > 0.8:
        why += (f". The parameters are strongly correlated ({max_correlation:.4f}) and this is still IDENTIFIABLE on purpose: "
                f"correlation says a ridge exists, not that it is long, and both marginal intervals here are within "
                f"{widest:.3g} of their own values")
    return status, condition, max_correlation, tuple(widths), why


def _report_to_dict(report: IdentifiabilityReport) -> dict[str, Any]:
    return {
        "status": report.status.value, "condition_number": encode_float(report.condition_number),
        "max_abs_correlation": encode_float(report.max_abs_correlation), "relative_widths": encode_vector(report.relative_widths),
        "parameter_names": list(report.parameter_names), "correlation_threshold": float(report.correlation_threshold),
        "condition_threshold": float(report.condition_threshold), "width_threshold": float(report.width_threshold),
        "why": report.why, "effective_sample_size": encode_float(report.effective_sample_size),
        "occupied_support_fraction": encode_float(report.occupied_support_fraction),
        "spacing_to_std": encode_vector(report.spacing_to_std),
    }


def _report_from_dict(payload: Mapping[str, Any]) -> IdentifiabilityReport:
    return IdentifiabilityReport(
        status=IdentifiabilityStatus(payload["status"]), condition_number=decode_float(payload["condition_number"]),
        max_abs_correlation=decode_float(payload["max_abs_correlation"]), relative_widths=decode_vector(payload["relative_widths"]),
        parameter_names=tuple(payload["parameter_names"]), correlation_threshold=float(payload["correlation_threshold"]),
        condition_threshold=float(payload["condition_threshold"]), width_threshold=float(payload["width_threshold"]),
        why=payload["why"], effective_sample_size=decode_float(payload["effective_sample_size"]),
        occupied_support_fraction=decode_float(payload["occupied_support_fraction"]),
        spacing_to_std=decode_vector(payload["spacing_to_std"]),
    )


@dataclass(frozen=True)
class RoutedIdentifiability:
    """An identifiability verdict, and the approximation and parameterization it was read from."""

    approximation_class: ApproximationClass
    parameterization_digest: str
    route_claim: RouteClaim
    report: IdentifiabilityReport

    def __post_init__(self) -> None:
        cls = ApproximationClass(self.approximation_class)
        if cls is ApproximationClass.LINEARIZED_PREDICTIVE_UQ:
            raise HybridUQError("identifiability is a statement about parameters, not about a predictive approximation")
        object.__setattr__(self, "approximation_class", cls)
        claim = RouteClaim(self.route_claim)
        if claim is RouteClaim.REFUSED:
            raise HybridUQError("a refused route has no identifiability to report")
        object.__setattr__(self, "route_claim", claim)
        if not isinstance(self.report, IdentifiabilityReport):
            raise HybridUQError("RoutedIdentifiability carries an IdentifiabilityReport")

    @property
    def status(self) -> IdentifiabilityStatus:
        return self.report.status

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTED_IDENTIFIABILITY_SCHEMA, "approximation_class": self.approximation_class.value,
                "parameterization_digest": self.parameterization_digest, "route_claim": self.route_claim.value,
                "report": _report_to_dict(self.report)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutedIdentifiability":
        require_schema(payload, ROUTED_IDENTIFIABILITY_SCHEMA)
        return cls(approximation_class=ApproximationClass(payload["approximation_class"]),
                   parameterization_digest=payload["parameterization_digest"], route_claim=RouteClaim(payload["route_claim"]),
                   report=_report_from_dict(payload["report"]))

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        payload["report"].pop("why")
        return digest_of(payload)


def assess_routed_identifiability(
    posterior: LocalGaussianPosterior | PosteriorGrid,
    *,
    correlation_threshold: float = 0.95,
    condition_threshold: float = 1.0e6,
    width_threshold: float = 1.0,
    confidence_level: float = 0.95,
) -> RoutedIdentifiability:
    """Identifiability under the frozen thresholds (the defaults are the frozen function's defaults)."""
    if isinstance(posterior, PosteriorGrid):
        if confidence_level != 0.95:
            raise HybridUQError("the frozen grid classification reads 95% intervals; confidence_level must be 0.95 for a grid")
        report = assess_identifiability(posterior, correlation_threshold=correlation_threshold,
                                        condition_threshold=condition_threshold, width_threshold=width_threshold)
        return RoutedIdentifiability(approximation_class=ApproximationClass.POSTERIOR_GRID,
                                     parameterization_digest=grid_parameterization_digest(posterior),
                                     route_claim=RouteClaim.SUPPORTED, report=report)
    if not isinstance(posterior, LocalGaussianPosterior):
        raise HybridUQError("assess_routed_identifiability takes a LocalGaussianPosterior or a PosteriorGrid")
    cov = posterior._require_numbers()
    level = float(confidence_level)
    if not 0.0 < level < 1.0:
        raise HybridUQError("confidence_level must lie strictly between 0 and 1")
    q = float(norm.ppf(0.5 + level / 2.0))
    sd = np.sqrt(np.diag(cov))
    point = np.asarray(posterior.inference_point)
    status, condition, max_corr, widths, why = classify(
        point, cov, point - q * sd, point + q * sd, posterior.parameter_names,
        correlation_threshold=correlation_threshold, condition_threshold=condition_threshold, width_threshold=width_threshold)
    report = IdentifiabilityReport(
        status=status, condition_number=condition, max_abs_correlation=max_corr, relative_widths=widths,
        parameter_names=posterior.parameter_names, correlation_threshold=correlation_threshold,
        condition_threshold=condition_threshold, width_threshold=width_threshold,
        why=f"{why} [LOCAL_GAUSSIAN_APPROXIMATION in parameterization {posterior.parameterization!r}]",
    )
    return RoutedIdentifiability(approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
                                 parameterization_digest=posterior.parameterization_digest,
                                 route_claim=posterior.claim, report=report)
