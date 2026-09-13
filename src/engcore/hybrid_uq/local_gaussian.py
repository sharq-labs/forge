"""LOCAL_GAUSSIAN_APPROXIMATION: N(z_hat, (J_w^T J_w)^-1) at the calibrated estimate, and when not to believe it.

It is exact only for a model affine in the inference coordinates, with no bound near the estimate and a
single optimum. Every one of those assumptions has a diagnostic. When a diagnostic fails the route REFUSES
(and emits no covariance) or DOWNGRADES (and says why). It never reports precise uncertainty anyway.

* interior, stationary optimum -- the Gauss-Newton step from the estimate, in sd units;
* usable curvature -- rank and the column-equilibrated condition number of the weighted Jacobian;
* bounds not dominating -- distance to each bound in sd;
* locally affine within about +/-2 sd -- chi-square rise along every principal axis against the 4 a
  Gaussian implies;
* parameterization conditioning -- raw versus equilibrated condition;
* a single mode -- a deterministic multistart through the frozen ``calibrate``. Without one the claim is
  capped at DOWNGRADED: no SUPPORTED claim assumes a single mode nobody looked past.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import chi2, norm

from ..inference.calibration import CalibrationResult, CalibrationSpec, CalibrationStatus, ForwardEvaluator, calibrate
from ..inference.grid import ObservationSet
from ..inference.parameters import CalibrationParameterSet
from ..scientific.results.immutable import freeze
from ..scientific.units.quantity import Quantity
from ._records import (
    decode_float, decode_matrix, decode_vector, digest_of, encode_float, encode_matrix, encode_vector, material,
    require_schema,
)
from .sensitivity import (
    LocalSensitivity, evaluate, inference_bounds, reconstruct_local_sensitivity, to_inference, to_natural, transforms_of,
)
from .vocabulary import (
    ApproximationClass, HybridUQError, RouteClaim, RouteReason, RouteRefusedError, claim_for,
)

MULTISTART_POLICY_SCHEMA = "hybrid_uq.multistart_policy/1"
ROUTE_DIAGNOSTICS_SCHEMA = "hybrid_uq.route_diagnostics/1"
PARAMETER_INTERVAL_SCHEMA = "hybrid_uq.parameter_interval/1"
LOCAL_GAUSSIAN_POSTERIOR_SCHEMA = "hybrid_uq.local_gaussian_posterior/1"

#: Declared validity thresholds, recorded in every RouteDiagnostics. Validated by the HD-UQ review
#: (benchmarks/core_gap_hd_uq) on Battery B3, TCR, K2 and failure cases F1-F6.
NONLINEARITY_DOWNGRADE = 0.10
NONLINEARITY_REFUSE = 0.50
BOUND_DOWNGRADE_SD = 3.0
STATIONARITY_SD = 0.05
AT_BOUND_RELATIVE = 1.0e-6
NUMERICAL_CONDITION_LIMIT = 1.0 / math.sqrt(float(np.finfo(float).eps))
PROBE_SD = 2.0

_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107,
           109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229)


def _prime(index: int) -> int:
    if index < len(_PRIMES):
        return _PRIMES[index]
    candidate, found = _PRIMES[-1], len(_PRIMES) - 1
    while found < index:
        candidate += 2
        if all(candidate % q for q in range(3, int(candidate ** 0.5) + 1, 2)):
            found += 1
    return candidate


def _radical_inverse(n: int, base: int) -> float:
    value, fraction = 0.0, 1.0 / base
    while n > 0:
        n, digit = divmod(n, base)
        value += digit * fraction
        fraction /= base
    return value


def _thresholds() -> dict[str, float]:
    return {
        "nonlinearity_downgrade": NONLINEARITY_DOWNGRADE, "nonlinearity_refuse": NONLINEARITY_REFUSE,
        "bound_downgrade_sd": BOUND_DOWNGRADE_SD, "stationarity_sd": STATIONARITY_SD,
        "at_bound_relative": AT_BOUND_RELATIVE, "numerical_condition_limit": NUMERICAL_CONDITION_LIMIT,
        "probe_sd": PROBE_SD,
    }


# ---------------------------------------------------------------------------
# multistart
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MultistartPolicy:
    """A deterministic multistart. Halton points in the central part of the inference-space bounds box.

    A start the forward model refuses (outside its admissible region, which a bounds box does not describe) is
    retracted toward the calibrated estimate, halving the distance each time, until the model admits it -- at
    most ``maximum_retractions`` times. The retraction is recorded per start; a start that never becomes
    admissible is recorded as such and does not count as converged.
    """

    starts: int = 6
    scheme: str = "halton_in_inference_bounds"
    interior_fraction: float = 0.8
    max_evaluations: int = 2000
    mode_separation_quantile: float = 0.999
    comparable_fit_quantile: float = 0.99
    maximum_retractions: int = 12

    def __post_init__(self) -> None:
        if int(self.starts) < 1:
            raise HybridUQError("a multistart needs at least one start")
        if self.scheme != "halton_in_inference_bounds":
            raise HybridUQError(f"unknown multistart scheme {self.scheme!r}")
        if not 0.0 < float(self.interior_fraction) <= 1.0:
            raise HybridUQError("interior_fraction must lie in (0, 1]")
        if int(self.max_evaluations) < 1:
            raise HybridUQError("max_evaluations must be positive")
        if int(self.maximum_retractions) < 0:
            raise HybridUQError("maximum_retractions must be non-negative")
        for label in ("mode_separation_quantile", "comparable_fit_quantile"):
            if not 0.0 < float(getattr(self, label)) < 1.0:
                raise HybridUQError(f"{label} must lie in (0, 1)")

    def start_points(self, parameter_set: CalibrationParameterSet) -> tuple[tuple[float, ...], ...]:
        """Starts in natural units. The same parameter set always gets the same starts."""
        transforms = transforms_of(parameter_set)
        lower, upper = inference_bounds(parameter_set)
        margin = 0.5 * (1.0 - float(self.interior_fraction))
        points = []
        for index in range(1, int(self.starts) + 1):
            u = np.asarray([_radical_inverse(index, _prime(d)) for d in range(len(lower))])
            z = lower + (margin + float(self.interior_fraction) * u) * (upper - lower)
            points.append(tuple(float(v) for v in to_natural(z, transforms)))
        return tuple(points)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MULTISTART_POLICY_SCHEMA, "starts": int(self.starts), "scheme": self.scheme,
                "interior_fraction": float(self.interior_fraction), "max_evaluations": int(self.max_evaluations),
                "mode_separation_quantile": float(self.mode_separation_quantile),
                "comparable_fit_quantile": float(self.comparable_fit_quantile),
                "maximum_retractions": int(self.maximum_retractions)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MultistartPolicy":
        require_schema(payload, MULTISTART_POLICY_SCHEMA)
        return cls(starts=int(payload["starts"]), scheme=payload["scheme"], interior_fraction=float(payload["interior_fraction"]),
                   max_evaluations=int(payload["max_evaluations"]),
                   mode_separation_quantile=float(payload["mode_separation_quantile"]),
                   comparable_fit_quantile=float(payload["comparable_fit_quantile"]),
                   maximum_retractions=int(payload["maximum_retractions"]))

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteDiagnostics:
    """Whether the local route's assumptions hold, measured. Not whether the parameters are identifiable."""

    parameters: int
    observations: int
    jacobian_rank: int
    jacobian_condition: float
    raw_jacobian_condition: float
    newton_step_in_sd: tuple[float, ...]
    at_bound: tuple[str, ...]
    near_bound: tuple[str, ...]
    minimum_bound_distance_sd: float
    nonlinearity_index: float
    nonlinearity_probes_skipped: int
    minimum_chi_square_rise: float
    multistart: tuple[Mapping[str, Any], ...]
    uniqueness: str
    thresholds: Mapping[str, float]
    evaluation_count: int
    claim: RouteClaim
    refusals: tuple[RouteReason, ...]
    downgrades: tuple[RouteReason, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim", RouteClaim(self.claim))
        refusals = tuple(sorted({RouteReason(r) for r in self.refusals}, key=lambda r: r.value))
        downgrades = tuple(sorted({RouteReason(r) for r in self.downgrades}, key=lambda r: r.value))
        if any(r.severity is not RouteClaim.REFUSED for r in refusals):
            raise HybridUQError("a downgrade reason cannot be recorded as a refusal")
        if any(r.severity is not RouteClaim.DOWNGRADED for r in downgrades):
            raise HybridUQError("a refusal reason cannot be recorded as a downgrade")
        if self.claim is not claim_for(refusals + downgrades):
            raise HybridUQError(f"claim {self.claim.value} does not follow from its reasons")
        object.__setattr__(self, "refusals", refusals)
        object.__setattr__(self, "downgrades", downgrades)
        object.__setattr__(self, "newton_step_in_sd", tuple(float(v) for v in self.newton_step_in_sd))
        object.__setattr__(self, "at_bound", tuple(self.at_bound))
        object.__setattr__(self, "near_bound", tuple(self.near_bound))
        object.__setattr__(self, "multistart", tuple(freeze(dict(m)) for m in self.multistart))
        object.__setattr__(self, "thresholds", freeze(dict(self.thresholds)))

    @property
    def reasons(self) -> tuple[RouteReason, ...]:
        return self.refusals + self.downgrades

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTE_DIAGNOSTICS_SCHEMA, "parameters": int(self.parameters), "observations": int(self.observations),
            "jacobian_rank": int(self.jacobian_rank), "jacobian_condition": encode_float(self.jacobian_condition),
            "raw_jacobian_condition": encode_float(self.raw_jacobian_condition),
            "newton_step_in_sd": encode_vector(self.newton_step_in_sd), "at_bound": list(self.at_bound),
            "near_bound": list(self.near_bound), "minimum_bound_distance_sd": encode_float(self.minimum_bound_distance_sd),
            "nonlinearity_index": encode_float(self.nonlinearity_index),
            "nonlinearity_probes_skipped": int(self.nonlinearity_probes_skipped),
            "minimum_chi_square_rise": encode_float(self.minimum_chi_square_rise),
            "multistart": [_encode_start(m) for m in self.multistart], "uniqueness": self.uniqueness,
            "thresholds": {k: encode_float(v) for k, v in sorted(self.thresholds.items())},
            "evaluation_count": int(self.evaluation_count), "claim": self.claim.value,
            "refusals": [r.value for r in self.refusals], "downgrades": [r.value for r in self.downgrades],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteDiagnostics":
        require_schema(payload, ROUTE_DIAGNOSTICS_SCHEMA)
        return cls(
            parameters=int(payload["parameters"]), observations=int(payload["observations"]),
            jacobian_rank=int(payload["jacobian_rank"]), jacobian_condition=decode_float(payload["jacobian_condition"]),
            raw_jacobian_condition=decode_float(payload["raw_jacobian_condition"]),
            newton_step_in_sd=decode_vector(payload["newton_step_in_sd"]), at_bound=tuple(payload["at_bound"]),
            near_bound=tuple(payload["near_bound"]), minimum_bound_distance_sd=decode_float(payload["minimum_bound_distance_sd"]),
            nonlinearity_index=decode_float(payload["nonlinearity_index"]),
            nonlinearity_probes_skipped=int(payload["nonlinearity_probes_skipped"]),
            minimum_chi_square_rise=decode_float(payload["minimum_chi_square_rise"]),
            multistart=tuple(_decode_start(m) for m in payload["multistart"]), uniqueness=payload["uniqueness"],
            thresholds={k: decode_float(v) for k, v in payload["thresholds"].items()},
            evaluation_count=int(payload["evaluation_count"]), claim=RouteClaim(payload["claim"]),
            refusals=tuple(RouteReason(r) for r in payload["refusals"]), downgrades=tuple(RouteReason(r) for r in payload["downgrades"]),
        )

    @property
    def digest(self) -> str:
        return digest_of(material(self.to_dict(), ("evaluation_count",)))


def _encode_start(entry: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, (list, tuple)):
            out[key] = encode_vector(value)
        elif isinstance(value, float):
            out[key] = encode_float(value)
        else:
            out[key] = value
    return out


def _decode_start(entry: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, list):
            out[key] = decode_vector(value)
        elif key in ("chi_square", "mahalanobis_sq"):
            out[key] = decode_float(value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# intervals and the posterior record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParameterInterval:
    """One marginal interval of an approximation, labelled with the approximation it came from."""

    name: str
    unit: str
    inference_transform: str
    estimate: float
    inference_standard_uncertainty: float
    lower: float
    upper: float
    confidence_level: float
    approximation_class: ApproximationClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "approximation_class", ApproximationClass(self.approximation_class))
        if not 0.0 < float(self.confidence_level) < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")
        if not (self.lower <= self.upper):
            raise HybridUQError("an interval's lower end exceeds its upper end")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PARAMETER_INTERVAL_SCHEMA, "name": self.name, "unit": self.unit,
                "inference_transform": self.inference_transform, "estimate": encode_float(self.estimate),
                "inference_standard_uncertainty": encode_float(self.inference_standard_uncertainty),
                "lower": encode_float(self.lower), "upper": encode_float(self.upper),
                "confidence_level": float(self.confidence_level), "approximation_class": self.approximation_class.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterInterval":
        require_schema(payload, PARAMETER_INTERVAL_SCHEMA)
        return cls(name=payload["name"], unit=payload["unit"], inference_transform=payload["inference_transform"],
                   estimate=decode_float(payload["estimate"]),
                   inference_standard_uncertainty=decode_float(payload["inference_standard_uncertainty"]),
                   lower=decode_float(payload["lower"]), upper=decode_float(payload["upper"]),
                   confidence_level=float(payload["confidence_level"]),
                   approximation_class=ApproximationClass(payload["approximation_class"]))


@dataclass(frozen=True)
class LocalGaussianPosterior:
    """A local Gaussian approximation of a posterior, with the diagnostics that decide whether to use it.

    ``covariance`` is in inference coordinates and is ``None`` when the route REFUSED: a refused route
    emits no numbers. It is never an exact posterior, and nothing on the record can say it is.
    """

    approximation_class: ApproximationClass
    parameter_names: tuple[str, ...]
    parameter_units: tuple[str, ...]
    inference_transforms: tuple[str, ...]
    parameterization: str
    parameterization_digest: str
    estimate: tuple[float, ...]
    inference_point: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...] | None
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    diagnostics: RouteDiagnostics
    sensitivity_digest: str
    dataset_id: str

    def __post_init__(self) -> None:
        cls = ApproximationClass(self.approximation_class)
        if cls is not ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION:
            raise HybridUQError(f"a LocalGaussianPosterior is a LOCAL_GAUSSIAN_APPROXIMATION, not {cls.value}")
        object.__setattr__(self, "approximation_class", cls)
        p = len(self.parameter_names)
        for label in ("parameter_names", "parameter_units", "inference_transforms"):
            object.__setattr__(self, label, tuple(str(v) for v in getattr(self, label)))
        for label in ("estimate", "inference_point", "lower_bounds", "upper_bounds"):
            object.__setattr__(self, label, tuple(float(v) for v in getattr(self, label)))
            if len(getattr(self, label)) != p:
                raise HybridUQError(f"{label} has {len(getattr(self, label))} entries for {p} parameter(s)")
        if len(self.parameter_units) != p or len(self.inference_transforms) != p:
            raise HybridUQError("names, units and transforms must agree in length")
        if not isinstance(self.diagnostics, RouteDiagnostics):
            raise HybridUQError("a LocalGaussianPosterior carries RouteDiagnostics")
        if self.diagnostics.claim is RouteClaim.REFUSED:
            if self.covariance is not None:
                raise HybridUQError("a REFUSED local route emits no covariance")
        else:
            if self.covariance is None:
                raise HybridUQError(f"a {self.diagnostics.claim.value} local route carries its covariance")
            cov = np.asarray(self.covariance, dtype=np.float64)
            if cov.shape != (p, p) or not np.all(np.isfinite(cov)) or not np.allclose(cov, cov.T, rtol=1e-10, atol=0.0):
                raise HybridUQError("covariance must be a finite symmetric p x p matrix")
            if np.any(np.diag(cov) <= 0.0):
                raise HybridUQError("covariance must have a positive diagonal")
            object.__setattr__(self, "covariance", tuple(tuple(float(v) for v in row) for row in cov))
        if not str(self.parameterization).strip() or not str(self.parameterization_digest).strip():
            raise HybridUQError("a local posterior records its parameterization and its identity")

    # -- reading ----------------------------------------------------------------
    @property
    def claim(self) -> RouteClaim:
        return self.diagnostics.claim

    @property
    def reasons(self) -> tuple[RouteReason, ...]:
        return self.diagnostics.reasons

    @property
    def exact_posterior(self) -> bool:
        return False

    def _require_numbers(self) -> np.ndarray:
        if self.covariance is None:
            raise RouteRefusedError(
                f"the local Gaussian route was REFUSED ({', '.join(r.value for r in self.diagnostics.refusals)}); "
                f"it has no covariance, intervals or identifiability to report")
        return np.asarray(self.covariance, dtype=np.float64)

    @property
    def standard_deviations(self) -> tuple[float, ...]:
        return tuple(float(v) for v in np.sqrt(np.diag(self._require_numbers())))

    @property
    def correlation(self) -> np.ndarray:
        cov = self._require_numbers()
        sd = np.sqrt(np.diag(cov))
        return cov / np.outer(sd, sd)

    def intervals(self, confidence_level: float = 0.95) -> tuple[ParameterInterval, ...]:
        cov = self._require_numbers()
        level = float(confidence_level)
        if not 0.0 < level < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")
        q = float(norm.ppf(0.5 + level / 2.0))
        sd = np.sqrt(np.diag(cov))
        out = []
        for i, name in enumerate(self.parameter_names):
            z, t = self.inference_point[i], self.inference_transforms[i]
            if t == "linear_map":
                low, high = z - q * sd[i], z + q * sd[i]
            else:
                low, high = to_natural([z - q * sd[i]], [t])[0], to_natural([z + q * sd[i]], [t])[0]
            out.append(ParameterInterval(name=name, unit=self.parameter_units[i], inference_transform=t,
                                         estimate=self.estimate[i], inference_standard_uncertainty=float(sd[i]),
                                         lower=float(low), upper=float(high), confidence_level=level,
                                         approximation_class=self.approximation_class))
        return tuple(out)

    def reparameterized(self, matrix, names: Sequence[str], units: Sequence[str], label: str) -> "LocalGaussianPosterior":
        """The same Gaussian in linear combinations of the inference coordinates. A new parameterization identity."""
        cov = self._require_numbers()
        T = np.asarray(matrix, dtype=np.float64)
        p = len(self.parameter_names)
        if T.ndim != 2 or T.shape[1] != p or T.shape[0] != len(names) or len(units) != len(names):
            raise HybridUQError(f"a reparameterization of {p} coordinates needs a k x {p} matrix and k names and units")
        if not np.all(np.isfinite(T)) or np.linalg.matrix_rank(T) != T.shape[0]:
            raise HybridUQError("a reparameterization matrix must be finite and of full row rank")
        text = str(label).strip()
        if not text:
            raise HybridUQError("a reparameterization needs a label")
        point = T @ np.asarray(self.inference_point)
        k = T.shape[0]
        identity = digest_of({"parent": self.parameterization_digest, "label": text, "matrix": encode_matrix(T.tolist()),
                              "names": list(map(str, names)), "units": list(map(str, units))})
        return LocalGaussianPosterior(
            approximation_class=self.approximation_class, parameter_names=tuple(map(str, names)),
            parameter_units=tuple(map(str, units)), inference_transforms=("linear_map",) * k,
            parameterization=f"linear_map:{text}", parameterization_digest=identity, estimate=tuple(point),
            inference_point=tuple(point), covariance=tuple(map(tuple, T @ cov @ T.T)),
            lower_bounds=(-math.inf,) * k, upper_bounds=(math.inf,) * k, diagnostics=self.diagnostics,
            sensitivity_digest=self.sensitivity_digest, dataset_id=self.dataset_id,
        )

    # -- records ----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LOCAL_GAUSSIAN_POSTERIOR_SCHEMA, "approximation_class": self.approximation_class.value,
            "exact_posterior": False, "parameter_names": list(self.parameter_names),
            "parameter_units": list(self.parameter_units), "inference_transforms": list(self.inference_transforms),
            "parameterization": self.parameterization, "parameterization_digest": self.parameterization_digest,
            "estimate": encode_vector(self.estimate), "inference_point": encode_vector(self.inference_point),
            "covariance": encode_matrix(self.covariance), "lower_bounds": encode_vector(self.lower_bounds),
            "upper_bounds": encode_vector(self.upper_bounds), "claim": self.claim.value,
            "diagnostics": self.diagnostics.to_dict(), "sensitivity_digest": self.sensitivity_digest,
            "dataset_id": self.dataset_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocalGaussianPosterior":
        require_schema(payload, LOCAL_GAUSSIAN_POSTERIOR_SCHEMA)
        if payload.get("exact_posterior") is not False:
            raise HybridUQError("a local Gaussian posterior record claiming to be exact is refused")
        diagnostics = RouteDiagnostics.from_dict(payload["diagnostics"])
        if payload.get("claim") != diagnostics.claim.value:
            raise HybridUQError("the record's claim disagrees with its diagnostics")
        return cls(
            approximation_class=ApproximationClass(payload["approximation_class"]),
            parameter_names=tuple(payload["parameter_names"]), parameter_units=tuple(payload["parameter_units"]),
            inference_transforms=tuple(payload["inference_transforms"]), parameterization=payload["parameterization"],
            parameterization_digest=payload["parameterization_digest"], estimate=decode_vector(payload["estimate"]),
            inference_point=decode_vector(payload["inference_point"]), covariance=decode_matrix(payload["covariance"]),
            lower_bounds=decode_vector(payload["lower_bounds"]), upper_bounds=decode_vector(payload["upper_bounds"]),
            diagnostics=diagnostics, sensitivity_digest=payload["sensitivity_digest"], dataset_id=payload["dataset_id"],
        )

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        payload["diagnostics"] = self.diagnostics.digest
        return digest_of(payload)


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------
def _declared_parameterization_digest(parameter_set: CalibrationParameterSet) -> str:
    return digest_of({"parameter_set_digest": parameter_set.digest, "label": "declared"})


def _refused(calibration: CalibrationResult, observations: ObservationSet, reason: RouteReason, *,
             sensitivity_digest: str = "", evaluations: int = 0, rank: int = 0,
             condition: float = math.nan, raw_condition: float = math.nan) -> LocalGaussianPosterior:
    parameters = calibration.spec.parameters
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    estimate = calibration.estimate_vector if calibration.status is CalibrationStatus.CONVERGED else calibration.spec.initial_vector
    p = len(parameters.names)
    diagnostics = RouteDiagnostics(
        parameters=p, observations=len(observations.observations), jacobian_rank=rank, jacobian_condition=condition,
        raw_jacobian_condition=raw_condition, newton_step_in_sd=(), at_bound=(), near_bound=(),
        minimum_bound_distance_sd=math.nan, nonlinearity_index=math.nan, nonlinearity_probes_skipped=0,
        minimum_chi_square_rise=math.nan, multistart=(), uniqueness="NOT_ASSESSED", thresholds=_thresholds(),
        evaluation_count=evaluations, claim=RouteClaim.REFUSED, refusals=(reason,), downgrades=(),
    )
    return LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=parameters.names,
        parameter_units=parameters.units, inference_transforms=transforms, parameterization="declared",
        parameterization_digest=_declared_parameterization_digest(parameters), estimate=tuple(estimate),
        inference_point=tuple(to_inference(estimate, transforms)), covariance=None, lower_bounds=tuple(lower),
        upper_bounds=tuple(upper), diagnostics=diagnostics, sensitivity_digest=sensitivity_digest or "none",
        dataset_id=observations.dataset_id,
    )


def local_gaussian_posterior(
    calibration: CalibrationResult,
    observations: ObservationSet,
    forward: ForwardEvaluator,
    *,
    multistart: MultistartPolicy | None,
    sensitivity: LocalSensitivity | None = None,
) -> LocalGaussianPosterior:
    """Build the local Gaussian approximation at a converged calibration, with every validity diagnostic.

    ``multistart`` is required: pass a :class:`MultistartPolicy`, or ``None`` to record that global
    uniqueness was not assessed (which caps the claim at DOWNGRADED).
    """
    if not isinstance(calibration, CalibrationResult):
        raise HybridUQError("local_gaussian_posterior takes a CalibrationResult")
    if not isinstance(observations, ObservationSet):
        raise HybridUQError("local_gaussian_posterior takes an ObservationSet")
    if multistart is not None and not isinstance(multistart, MultistartPolicy):
        raise HybridUQError("multistart must be a MultistartPolicy or None")
    if calibration.status is not CalibrationStatus.CONVERGED:
        return _refused(calibration, observations, RouteReason.CALIBRATION_NOT_CONVERGED)

    parameters = calibration.spec.parameters
    names = parameters.names
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    estimate = np.asarray(calibration.estimate_vector, dtype=np.float64)
    z0 = to_inference(estimate, transforms)
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    observed, sigma = observations.numeric_vectors()
    evaluations = 0

    if sensitivity is None:
        try:
            sensitivity = reconstruct_local_sensitivity(calibration, observations, forward)
        except RouteRefusedError:
            return _refused(calibration, observations, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE)
    else:
        if not isinstance(sensitivity, LocalSensitivity):
            raise HybridUQError("sensitivity must be a LocalSensitivity")
        mismatches = []
        if sensitivity.parameter_set_digest != parameters.digest:
            mismatches.append("parameter set")
        if tuple(sensitivity.observation_keys) != tuple(keys) or sensitivity.dataset_id != observations.dataset_id:
            mismatches.append("observations")
        if not np.allclose(sensitivity.estimate, estimate, rtol=1e-12, atol=0.0):
            mismatches.append("estimate")
        if mismatches:
            raise HybridUQError(f"the supplied sensitivity is not this calibration's: {mismatches} differ")
    evaluations += sensitivity.evaluation_count

    p, n = len(names), len(keys)
    A = sensitivity.weighted_jacobian
    refusals: list[RouteReason] = []
    downgrades: list[RouteReason] = []

    # usable curvature: rank and conditioning, scale-free through column equilibration
    norms = np.linalg.norm(A, axis=0)
    raw_s = np.linalg.svd(A, compute_uv=False)
    raw_condition = float(raw_s[0] / raw_s[-1]) if raw_s[-1] > 0 else math.inf
    if np.any(norms == 0.0):
        return _refused(calibration, observations, RouteReason.STRUCTURALLY_UNIDENTIFIABLE, sensitivity_digest=sensitivity.digest,
                        evaluations=evaluations, rank=int(np.linalg.matrix_rank(A)), condition=math.inf, raw_condition=raw_condition)
    scaled = A / norms
    U, S, Vt = np.linalg.svd(scaled, full_matrices=False)
    rank = int(np.sum(S > S[0] * max(n, p) * np.finfo(float).eps))
    condition = float(S[0] / S[-1]) if S[-1] > 0 else math.inf
    structural = None
    if p >= n:
        structural = RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM
    elif rank < p:
        structural = RouteReason.STRUCTURALLY_UNIDENTIFIABLE
    elif condition > NUMERICAL_CONDITION_LIMIT:
        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN
    if structural is not None:
        return _refused(calibration, observations, structural, sensitivity_digest=sensitivity.digest, evaluations=evaluations,
                        rank=rank, condition=condition, raw_condition=raw_condition)
    if raw_condition > NUMERICAL_CONDITION_LIMIT:
        downgrades.append(RouteReason.POORLY_SCALED_PARAMETERIZATION)
    scaled_cov = (Vt.T / S ** 2) @ Vt
    cov = scaled_cov / np.outer(norms, norms)
    cov = 0.5 * (cov + cov.T)
    sd = np.sqrt(np.diag(cov))
    chi_min = sensitivity.chi_square

    # interior, stationary optimum: the Gauss-Newton step from the estimate, in sd units
    residual = sensitivity.standardized_residuals
    step = -(cov @ (A.T @ residual))
    step_sd = step / sd
    span = upper - lower
    at_lower = (z0 - lower) <= AT_BOUND_RELATIVE * span
    at_upper = (upper - z0) <= AT_BOUND_RELATIVE * span
    at_bound = []
    for i in range(p):
        if abs(step_sd[i]) > STATIONARITY_SD:
            if (at_lower[i] and step[i] < 0) or (at_upper[i] and step[i] > 0):
                at_bound.append(names[i])
    if at_bound:
        refusals.append(RouteReason.PARAMETER_AT_BOUND)
    elif np.any(np.abs(step_sd) > STATIONARITY_SD):
        refusals.append(RouteReason.NOT_STATIONARY)

    # bounds not dominating
    distance = np.minimum(z0 - lower, upper - z0) / sd
    near = tuple(names[i] for i in range(p) if distance[i] < BOUND_DOWNGRADE_SD and names[i] not in at_bound)
    if near:
        downgrades.append(RouteReason.BOUND_WITHIN_3_SD)

    # locally affine within +/-2 sd: chi-square rise along every principal axis, against the Gaussian's 4
    def chi_square_at(z):
        values = evaluate(forward, to_natural(z, transforms), keys, units, references)
        return None if values is None else float(np.sum(((values - observed) / sigma) ** 2))

    lam, vec = np.linalg.eigh(cov)
    worst, skipped, min_rise, not_minimum = 0.0, 0, math.inf, False
    expected = PROBE_SD ** 2
    for k in range(p):
        delta = PROBE_SD * math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k]
        for sign in (1.0, -1.0):
            point = z0 + sign * delta
            if np.any(point < lower) or np.any(point > upper):
                skipped += 1
                continue
            value = chi_square_at(point)
            evaluations += 1
            if value is None:
                skipped += 1
                continue
            rise = value - chi_min
            min_rise = min(min_rise, rise)
            if rise < -1e-9 * max(1.0, chi_min):
                not_minimum = True
            worst = max(worst, abs(rise / expected - 1.0))
    if not_minimum:
        refusals.append(RouteReason.NOT_A_LOCAL_MINIMUM)
    if worst > NONLINEARITY_REFUSE:
        refusals.append(RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN)
    elif worst > NONLINEARITY_DOWNGRADE:
        downgrades.append(RouteReason.NONLINEAR_WITHIN_2_SD)
    if skipped:
        downgrades.append(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)

    # a single mode: deterministic multistart through the frozen calibrate
    starts_record: list[dict[str, Any]] = []
    if multistart is None:
        uniqueness = "NOT_ASSESSED"
        downgrades.append(RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED)
    else:
        separation = float(chi2.ppf(multistart.mode_separation_quantile, p))
        comparable = float(chi2.ppf(multistart.comparable_fit_quantile, p))
        spec = calibration.spec
        converged = 0
        found_second = found_better = False
        for start in multistart.start_points(parameters):
            proposed = tuple(start)
            zs = to_inference(start, transforms)
            retractions = 0
            admissible = evaluate(forward, start, keys, units, references) is not None
            evaluations += 1
            while not admissible and retractions < int(multistart.maximum_retractions):
                retractions += 1
                start = tuple(float(v) for v in to_natural(z0 + (zs - z0) / 2.0 ** retractions, transforms))
                admissible = evaluate(forward, start, keys, units, references) is not None
                evaluations += 1
            if not admissible:
                starts_record.append({"start": proposed, "status": "NO_ADMISSIBLE_START", "retractions": retractions})
                continue
            restart = CalibrationSpec(parameters=spec.parameters, fixed=spec.fixed,
                                      initial_point={nm: Quantity(v, u) for nm, v, u in zip(names, start, parameters.units)},
                                      noise_model=spec.noise_model, objective=spec.objective, method=spec.method)
            refit = calibrate(restart, observations, forward, heldout_dataset_id=calibration.provenance.heldout_dataset_id,
                              max_evaluations=int(multistart.max_evaluations), seed=calibration.provenance.seed)
            evaluations += int(refit.evaluation_count)
            entry: dict[str, Any] = {"start": tuple(start), "proposed_start": proposed, "retractions": retractions,
                                     "status": refit.status.value}
            if refit.status is CalibrationStatus.CONVERGED:
                converged += 1
                other = to_inference(refit.estimate_vector, transforms)
                m2 = float(np.sum((A @ (other - z0)) ** 2))
                entry.update({"estimate": tuple(refit.estimate_vector), "chi_square": float(refit.objective_value),
                              "mahalanobis_sq": m2})
                if m2 > separation:
                    if refit.objective_value < chi_min - comparable:
                        entry["classification"] = "BETTER_OPTIMUM"
                        found_better = True
                    elif refit.objective_value <= chi_min + comparable:
                        entry["classification"] = "SECOND_MODE"
                        found_second = True
                    else:
                        entry["classification"] = "WORSE_LOCAL_OPTIMUM"
                else:
                    entry["classification"] = "SAME_OPTIMUM"
            starts_record.append(entry)
        if found_better:
            refusals.append(RouteReason.BETTER_OPTIMUM_FOUND)
        if found_second:
            refusals.append(RouteReason.SECOND_MODE_FOUND)
        if converged * 2 < len(starts_record):
            downgrades.append(RouteReason.MULTISTART_INCOMPLETE)
        uniqueness = ("BETTER_OPTIMUM_FOUND" if found_better else "SECOND_MODE_FOUND" if found_second
                      else "MULTISTART_INCOMPLETE" if converged * 2 < len(starts_record) else "MULTISTART_NO_SECOND_MODE")

    claim = claim_for(refusals + downgrades)
    diagnostics = RouteDiagnostics(
        parameters=p, observations=n, jacobian_rank=rank, jacobian_condition=condition, raw_jacobian_condition=raw_condition,
        newton_step_in_sd=tuple(step_sd), at_bound=tuple(at_bound), near_bound=near,
        minimum_bound_distance_sd=float(np.min(distance)), nonlinearity_index=float(worst),
        nonlinearity_probes_skipped=skipped, minimum_chi_square_rise=float(min_rise),
        multistart=tuple(starts_record), uniqueness=uniqueness, thresholds=_thresholds(), evaluation_count=evaluations,
        claim=claim, refusals=tuple(r for r in refusals if r.severity is RouteClaim.REFUSED),
        downgrades=tuple(d for d in downgrades if d.severity is RouteClaim.DOWNGRADED),
    )
    posterior = LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=names,
        parameter_units=parameters.units, inference_transforms=transforms, parameterization="declared",
        parameterization_digest=_declared_parameterization_digest(parameters), estimate=tuple(estimate),
        inference_point=tuple(z0), covariance=None if claim is RouteClaim.REFUSED else tuple(map(tuple, cov)),
        lower_bounds=tuple(lower), upper_bounds=tuple(upper), diagnostics=diagnostics,
        sensitivity_digest=sensitivity.digest, dataset_id=observations.dataset_id,
    )
    # Held for the router's grid rebuild only: a covariance the route refused to report is still the best
    # available DESIGN for a grid that the frozen V1 checks will then verify or refuse. Never serialized.
    object.__setattr__(posterior, "_design_covariance", cov)
    object.__setattr__(posterior, "_modes", tuple(
        to_inference(m["estimate"], transforms) for m in starts_record
        if m.get("classification") in ("SECOND_MODE", "BETTER_OPTIMUM")))
    return posterior
