"""Identifiability for either route, under the frozen V1 thresholds and the frozen V1 classification rule.

For a grid it IS the frozen ``assess_identifiability``, refusals included. For the local route it applies the
same rule to the Gaussian: covariance condition number, largest absolute correlation, and each marginal 95%
width divided by the estimate, with Gaussian marginal intervals in inference coordinates in place of the
grid's discrete ones -- except that a log coordinate's width is its natural-scale relative width, which does
not depend on the unit it was declared in. The verdict is stated in a parameterization, and the record says which.

Route validity is not identifiability. A SUPPORTED route may report NOT_IDENTIFIABLE; a REFUSED route reports
no identifiability at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import norm

from ..inference.calibration import (
    _DECLARED_IDENTIFIABILITY_THRESHOLDS,
    WIDTH_REFERENCE_NOTE,
    IdentifiabilityReport,
    IdentifiabilityStatus,
    _require_declared_or_tighter_thresholds,
    assess_identifiability,
)
from ..inference.grid import PosteriorGrid
from ._records import decode_float, decode_vector, digest_of, encode_float, encode_vector, require_schema
from .local_gaussian import LocalGaussianPosterior
from .vocabulary import ApproximationClass, HybridUQError, RouteClaim

#: R-45 (re-audit 2026-09-16): `/2` because CORE-004 changed two things under `/1` -- the conditioning is
#: now computed on the CORRELATION matrix rather than the covariance, and every explanation carries
#: `WIDTH_REFERENCE_NOTE`. A reader re-derives both, so a `/1` record was refused with "the verdict and its
#: explanation do not follow from its own numbers, which give <the same verdict>": a message reporting a
#: contradiction where the record is simply unreadable. The refusal is right -- a `/1` record's stored
#: condition number was computed under a definition this code retired and nothing in the record says which
#: -- so the version carries the reason, as `hybrid_uq.route_diagnostics/1` already does.
ROUTED_IDENTIFIABILITY_SCHEMA = "hybrid_uq.routed_identifiability/2"
ROUTED_IDENTIFIABILITY_SCHEMA_V1 = "hybrid_uq.routed_identifiability/1"


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
    sd = np.sqrt(np.diag(cov))
    correlation = cov / np.outer(sd, sd)
    # CORE-004: the condition number of the correlation matrix, which no parameter's unit or scale moves
    eigenvalues = np.linalg.eigvalsh(correlation)
    smallest, largest = float(np.min(eigenvalues)), float(np.max(eigenvalues))
    condition = math.inf if smallest <= 0.0 else largest / smallest
    off = [abs(float(correlation[i, j])) for i in range(n) for j in range(n) if i != j]
    max_correlation = max(off) if off else 0.0
    widths = []
    for i in range(n):
        scale = abs(float(mean[i]))
        widths.append((highs[i] - lows[i]) / scale if scale > 0.0 else math.inf)
    status, why = _rule(condition, max_correlation, widths, names, correlation_threshold=correlation_threshold,
                        condition_threshold=condition_threshold, width_threshold=width_threshold)
    return status, condition, max_correlation, tuple(widths), why


def _rule(condition: float, max_correlation: float, widths: Sequence[float], names: Sequence[str], *,
          correlation_threshold: float, condition_threshold: float, width_threshold: float) -> tuple[IdentifiabilityStatus, str]:
    """The frozen V1 classification rule over its three numbers: ``(status, why)``. One rule for writing and reading."""
    widths = [float(w) for w in widths]
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
    return status, why + WIDTH_REFERENCE_NOTE


#: The thresholds the router classifies under: the frozen ``assess_identifiability`` defaults.
CANONICAL_IDENTIFIABILITY_THRESHOLDS = {"correlation_threshold": 0.95, "condition_threshold": 1.0e6, "width_threshold": 1.0}


#: Cantelli's constant at 95%: the half-width, in standard deviations, of the widest two-sided interval that
#: can hold 95% of the mass of SOME distribution with a given standard deviation. It is the tightest bound
#: available without assuming a shape, which is why it is what a grid record's widths are held to (R-27).
CANTELLI_95_SD = math.sqrt(0.975 / 0.025)


def grid_record_variance_shrink_window(mean, covariance, relative_widths) -> float:
    """The largest factor a grid record's covariance can be DIVIDED by while the record still reads back.

    This function exists to state a limit, not to enforce one. A serialized grid result does not carry its
    grid, so its mean and covariance cannot be recomputed; what holds them is the Cantelli bound in
    :func:`_grid_report_problems`, which refuses a record whose carried 95% interval is too wide for its
    carried standard deviation. Solving that bound for the shrink factor gives the window inside which
    dividing the covariance alone -- with the integrity-only moments digest recomputed, which anyone can do --
    contradicts nothing in the record:

        ``min_i (2 k sigma_i / (w_i |mu_i|))**2``,  ``k = CANTELLI_95_SD``

    over the parameters with a non-zero mean and a finite width, and ``inf`` when no parameter constrains it
    (a zero mean makes a relative width meaningless, so those parameters are skipped, exactly as the bound
    skips them). On the audited record the window is 7.98: a variance divided by 5 reads back and by 8 does
    not. Callers who need a record's moments to be re-derivable need the grid, not this record.
    """
    mean = np.asarray(mean, dtype=np.float64)
    sd = np.sqrt(np.maximum(np.diag(np.asarray(covariance, dtype=np.float64)), 0.0))
    widths = np.asarray(relative_widths, dtype=np.float64)
    factors = []
    for index in range(min(len(mean), len(sd), len(widths))):
        scale, width = abs(float(mean[index])), float(widths[index])
        if scale == 0.0 or not math.isfinite(width) or width <= 0.0:
            continue
        factors.append((2.0 * CANTELLI_95_SD * float(sd[index]) / (width * scale)) ** 2)
    return min(factors) if factors else math.inf


def _grid_diagnostic_problems(report: IdentifiabilityReport, points) -> list[str]:
    """What a grid record's own resolution diagnostics can be held to (R-27, finding 22's fourth claim).

    The effective sample size, the occupied support fraction and the spacing-to-standard-deviation ratios were
    carried and never read, so a record with an effective sample size of 1.5 and a step 50x the posterior's
    width read back SUPPORTED -- a grid V1 would have refused with GRID_TOO_COARSE_FOR_INFERENCE. Three of the
    four checks here are definitional (a count of nodes lies between 1 and the node count the summary commits
    to; a fraction of a non-empty support lies in (0, 1]; there is one ratio per axis). The fourth is V1's own
    condition verbatim, BOTH halves of it: a small effective sample size alone is a sharply informative
    posterior, and what says 'too coarse' is the step being as wide as the posterior it is meant to resolve.
    """
    problems: list[str] = []
    names = tuple(report.parameter_names)
    spacing = tuple(float(s) for s in report.spacing_to_std)
    if len(spacing) != len(names):
        problems.append(f"identifiability carries {len(spacing)} spacing-to-standard-deviation ratio(s) for "
                        f"{len(names)} parameter(s)")
    ess = float(report.effective_sample_size)
    occupied = float(report.occupied_support_fraction)
    if not math.isfinite(ess) or ess < 1.0 or (points is not None and ess > float(points)):
        problems.append(f"an effective sample size is a count of nodes, so it lies in [1, {points!r}]; this "
                        f"record carries {ess!r}")
    if not math.isfinite(occupied) or not 0.0 < occupied <= 1.0:
        problems.append(f"an occupied support fraction lies in (0, 1]; this record carries {occupied!r}")
    minimum = float(dict(_DECLARED_IDENTIFIABILITY_THRESHOLDS)["minimum_effective_points"])
    worst = max(spacing) if spacing else math.inf
    if math.isfinite(ess) and ess < minimum and worst >= 1.0:
        problems.append(f"an effective sample size {ess:.3g} below {minimum:.3g} with a grid step {worst:.3g}x "
                        f"the posterior's own standard deviation is the grid V1 refuses as too coarse for "
                        f"inference, so no accepted grid produced this record")
    return problems


def _same_number(a: float, b: float) -> bool:
    a, b = float(a), float(b)
    return (math.isnan(a) and math.isnan(b)) or a == b or math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0)


def _report_differences(found: IdentifiabilityReport, expected: IdentifiabilityReport) -> list[str]:
    """Where a carried report differs from the one its numbers produce, field by field (NaN equals NaN)."""
    problems = []
    if found.status is not expected.status:
        problems.append(f"identifiability status {found.status.value} is not the {expected.status.value} its covariance gives")
    for label in ("condition_number", "max_abs_correlation", "correlation_threshold", "condition_threshold", "width_threshold",
                  "effective_sample_size", "occupied_support_fraction"):
        if not _same_number(getattr(found, label), getattr(expected, label)):
            problems.append(f"identifiability {label} {getattr(found, label)!r} is not {getattr(expected, label)!r}")
    for label in ("relative_widths", "spacing_to_std"):
        a, b = tuple(getattr(found, label)), tuple(getattr(expected, label))
        if len(a) != len(b) or not all(_same_number(x, y) for x, y in zip(a, b)):
            problems.append(f"identifiability {label} {list(a)} is not {list(b)}")
    if tuple(found.parameter_names) != tuple(expected.parameter_names):
        problems.append("identifiability names other parameters")
    if found.why != expected.why:
        problems.append("identifiability explains a verdict its numbers do not give")
    return problems


def _grid_report_problems(report: IdentifiabilityReport, mean: Sequence[float], covariance) -> list[str]:
    """What a serialized grid result's identifiability can be held to without its grid (audit HUQ-09).

    The grid is data-plane and is not serialized, so the marginal intervals cannot be recomputed. What can: the
    thresholds are the router's; the condition number and correlation are the carried covariance's, by the frozen
    formulas; the status and ``why`` follow from the carried numbers by the frozen rule; and each relative width,
    times its mean, is a central 95% interval of a distribution with the carried mean and standard deviation, which
    Cantelli's inequality confines to mean +/- ``CANTELLI_95_SD`` sd.

    WHAT THAT DOES NOT CATCH (R-27, finding 22's first two claims). This docstring used to say 'A covariance
    shrunk under a recomputed commitment breaks that bound', which is false inside a window this code can
    compute: see :func:`grid_record_variance_shrink_window`, 7.98 on the audited record. Cantelli is the
    tightest bound that assumes no shape, and it bounds an interval from ABOVE only -- no lower bound on a
    central 95% interval follows from a standard deviation. So a covariance divided inside that window, widths
    lowered with it or lowered alone (turning NOT_IDENTIFIABLE into IDENTIFIABLE), and a small shift of the
    mean are all undetectable from the record, because the digests are integrity-only and anyone can recompute
    them. A grid record's moments and identifiability are therefore NOT re-derived, only bounded, and a caller
    who needs them re-derived needs the grid.
    """
    problems = []
    for key, value in CANONICAL_IDENTIFIABILITY_THRESHOLDS.items():
        if not _same_number(getattr(report, key), value):
            problems.append(f"identifiability {key} {getattr(report, key)!r} is not the router's {value!r}")
    cov = np.asarray(covariance, dtype=np.float64)
    n = cov.shape[0]
    std = np.sqrt(np.maximum(np.diag(cov), 0.0))
    denominator = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = np.divide(cov, denominator, out=np.zeros_like(cov), where=denominator > 0.0)
    eigenvalues = np.linalg.eigvalsh(correlation)  # CORE-004: as assess_identifiability computes it
    smallest, largest = float(np.min(eigenvalues)), float(np.max(eigenvalues))
    condition = math.inf if smallest <= 0.0 else largest / smallest
    off = [abs(float(correlation[i, j])) for i in range(n) for j in range(n) if i != j]
    max_correlation = max(off) if off else 0.0
    if not _same_number(report.condition_number, condition):
        problems.append(f"identifiability condition number {report.condition_number!r} is not the covariance's {condition!r}")
    if not _same_number(report.max_abs_correlation, max_correlation):
        problems.append(f"identifiability correlation {report.max_abs_correlation!r} is not the covariance's {max_correlation!r}")
    widths = tuple(float(w) for w in report.relative_widths)
    if len(widths) != n:
        problems.append(f"{len(widths)} relative widths for {n} parameter(s)")
        return problems
    status, why = _rule(report.condition_number, report.max_abs_correlation, widths, report.parameter_names,
                        correlation_threshold=report.correlation_threshold, condition_threshold=report.condition_threshold,
                        width_threshold=report.width_threshold)
    if status is not report.status or why != report.why:
        problems.append(f"identifiability says {report.status.value} where its own numbers give {status.value}")
    k = CANTELLI_95_SD
    for i in range(n):
        scale = abs(float(mean[i]))
        if not math.isfinite(widths[i]) or scale == 0.0:
            continue
        if widths[i] < 0.0 or widths[i] * scale > 2.0 * k * float(std[i]) * (1.0 + 1e-6) + 1e-12 * scale:
            problems.append(f"a 95% interval {widths[i] * scale:.6g} wide for {report.parameter_names[i]!r} cannot belong to a "
                            f"distribution with standard deviation {float(std[i]):.6g}")
    return problems


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
        # The verdict follows from its own numbers under its own thresholds (audit HUQ-09): a status or an explanation
        # the frozen rule does not give from them is not a verdict. A local report's explanation also names its
        # parameterization after the rule's text.
        r = self.report
        # A RECORD CANNOT CARRY A RULE LOOSER THAN THE ROUTER'S (I-14, R-28).
        #
        # The re-derivation below makes a record SELF-CONSISTENT, which is
        # precisely why the audited forgery read back: its numbers and its moved
        # rule agreed with each other, and neither was compared with the
        # declared rule. These constants are the ones `_report_differences`
        # already checks against; what changes is that the check runs at
        # construction and not only inside a `HybridUQResult`.
        for key, canonical in CANONICAL_IDENTIFIABILITY_THRESHOLDS.items():
            value = float(getattr(r, key))
            if not math.isfinite(value) or value <= 0.0 or value > float(canonical):
                raise HybridUQError(
                    f"identifiability {key}={value!r} is looser than the router's {canonical!r}; a "
                    f"classification may be made stricter by argument, never more lenient, and a record "
                    f"carrying a moved rule is consistent with itself and with nothing else")
        status, why = _rule(r.condition_number, r.max_abs_correlation, r.relative_widths, r.parameter_names,
                            correlation_threshold=r.correlation_threshold, condition_threshold=r.condition_threshold,
                            width_threshold=r.width_threshold)
        # The tightened note is RE-DERIVED from the report's own thresholds, which it carries, so a record
        # that claims a moved rule must carry the rule it claims and a record that claims none must carry
        # none. (I-14, R-28.)
        expected = why + _tightened_note({
            key: float(getattr(r, key))
            for key, declared in _DECLARED_IDENTIFIABILITY_THRESHOLDS
            if key in CANONICAL_IDENTIFIABILITY_THRESHOLDS and float(getattr(r, key)) != float(declared)
        })
        explained = r.why == expected or (cls is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION
                                          and r.why.startswith(expected + " ["))
        if status is not r.status or not explained:
            raise HybridUQError(f"the identifiability verdict {r.status.value} and its explanation do not follow from its own "
                                f"numbers, which give {status.value} and {expected!r} under its thresholds")

    @property
    def status(self) -> IdentifiabilityStatus:
        return self.report.status

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ROUTED_IDENTIFIABILITY_SCHEMA, "approximation_class": self.approximation_class.value,
                "parameterization_digest": self.parameterization_digest, "route_claim": self.route_claim.value,
                "report": _report_to_dict(self.report)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutedIdentifiability":
        if payload.get("schema") == ROUTED_IDENTIFIABILITY_SCHEMA_V1:
            raise HybridUQError(
                f"{ROUTED_IDENTIFIABILITY_SCHEMA_V1} records cannot be read: CORE-004 changed the "
                f"conditioning definition (the condition number is the CORRELATION matrix's, not the "
                f"covariance's) and appended the width-reference note to every explanation, both under that "
                f"same version. A stored condition number does not say which definition produced it, so the "
                f"verdict cannot be re-derived from it. Re-derive the identifiability from the covariance "
                f"instead of reading the record"
            )
        require_schema(payload, ROUTED_IDENTIFIABILITY_SCHEMA)
        return cls(approximation_class=ApproximationClass(payload["approximation_class"]),
                   parameterization_digest=payload["parameterization_digest"], route_claim=RouteClaim(payload["route_claim"]),
                   report=_report_from_dict(payload["report"]))

    @property
    def digest(self) -> str:
        # ``why`` is material (audit HUQ-14): two records that explain one verdict in opposite words are not one record.
        return digest_of(self.to_dict())


def _local_marginal_intervals(point: Sequence[float], sd: Sequence[float], transforms: Sequence[str],
                              q: float) -> tuple[list[float], list[float], list[float]]:
    """``(scales, lows, highs)`` whose ``(high - low) / |scale|`` is each parameter's relative 95% width.

    For an ``identity`` or ``linear_map`` coordinate that is the Gaussian interval over the estimate. For a ``log``
    coordinate the inference point is ln(value / declared unit), whose origin moves with the declared unit, so
    dividing by it made the verdict depend on the unit a parameter was written in (audit HUQ-03). Its width is the
    natural-scale interval exp(z +/- q sd) relative to exp(z) instead, exp(q sd) - exp(-q sd), which no unit moves.
    """
    scales, lows, highs = [], [], []
    with np.errstate(over="ignore"):
        for z, s, transform in zip(point, sd, transforms):
            if transform == "log":
                scales.append(1.0)
                lows.append(float(np.exp(-q * float(s))))
                highs.append(float(np.exp(q * float(s))))
            else:
                scales.append(float(z))
                lows.append(float(z) - q * float(s))
                highs.append(float(z) + q * float(s))
    return scales, lows, highs


def _tightened_note(tightened: Mapping[str, float]) -> str:
    """The grid path's own sentence for a caller-tightened rule, or nothing (I-14, R-28)."""
    if not tightened:
        return ""
    return (f". Classified under caller-tightened thresholds {dict(tightened)}; the "
            f"declared defaults are {dict(_DECLARED_IDENTIFIABILITY_THRESHOLDS)}")


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
    # THE DECLARED-OR-TIGHTER GUARD RUNS HERE TOO (I-14, R-28).
    #
    # It ran for a grid and not for the local route, so a verdict was BOUGHT by
    # argument: the weak-identification case is canonically NOT_IDENTIFIABLE
    # with widths [8.553, 1.842] and correlation 0.9999985, and under
    # (0.99999, 1e300, 1e9) it reads WEAKLY_IDENTIFIABLE -- while the SAME
    # thresholds on the same problem's grid raise `looser than the declared
    # 1.0`. That is an inconsistency inside one function, thirty lines apart.
    # `minimum_effective_points` is passed at its declared value: a local
    # Gaussian has no effective-point count, so the check for it is a no-op.
    declared = dict(_DECLARED_IDENTIFIABILITY_THRESHOLDS)
    tightened = _require_declared_or_tighter_thresholds(
        correlation_threshold=correlation_threshold,
        condition_threshold=condition_threshold,
        width_threshold=width_threshold,
        minimum_effective_points=declared["minimum_effective_points"],
    )
    cov = posterior._require_numbers()
    level = float(confidence_level)
    if not 0.0 < level < 1.0:
        raise HybridUQError("confidence_level must lie strictly between 0 and 1")
    q = float(norm.ppf(0.5 + level / 2.0))
    sd = np.sqrt(np.diag(cov))
    scales, lows, highs = _local_marginal_intervals(posterior.inference_point, sd, posterior.inference_transforms, q)
    status, condition, max_corr, widths, why = classify(
        scales, cov, lows, highs, posterior.parameter_names,
        correlation_threshold=correlation_threshold, condition_threshold=condition_threshold, width_threshold=width_threshold)
    report = IdentifiabilityReport(
        status=status, condition_number=condition, max_abs_correlation=max_corr, relative_widths=widths,
        parameter_names=posterior.parameter_names, correlation_threshold=correlation_threshold,
        condition_threshold=condition_threshold, width_threshold=width_threshold,
        # A STRICTER RULE IS STILL A RULE THAT MOVED (I-14, R-28). The grid path
        # appends this note, in these words, and a reader comparing two reports
        # has no other way to know which rule each was reached under. The
        # parameterization suffix stays LAST, because `RoutedIdentifiability`
        # re-derives `why` and accepts the local class's report only as the
        # rule's text followed by that bracket.
        why=(f"{why}{_tightened_note(tightened)} "
             f"[LOCAL_GAUSSIAN_APPROXIMATION in parameterization {posterior.parameterization!r}]"),
    )
    return RoutedIdentifiability(approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
                                 parameterization_digest=posterior.parameterization_digest,
                                 route_claim=posterior.claim, report=report)
