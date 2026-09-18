"""Phase 2B -- parameter uncertainty by forward propagation, or UNKNOWN.

The caller declares what is uncertain about the *inputs* -- a distribution per
input path, with its rationale -- exactly as it declares the inputs themselves.
That declaration is an input to the calculation and is part of the claim's
identity; it is never evidence. What Forge computes is the consequence for the
quantity of interest: every sample is a real execution of the selected
capability, and the propagated spread is read off those executions.

The estimate
------------
Independent random samples (a seeded generator, so a replay draws the same
inputs) and **Wilks' distribution-free tolerance interval**: the range
``[min, max]`` of ``n`` iid outputs contains at least a fraction ``beta`` of the
propagated output distribution with confidence
``gamma = 1 - n*beta**(n-1) + (n-1)*beta**n``. No normality, linearity or
monotonicity is assumed. The record is an INTERVAL with
``source_kind = PARAMETER`` whose ``method`` states ``beta`` and ``gamma``; it
claims nothing more.

UNKNOWN, never a narrower answer
--------------------------------
* ``gamma`` below the required confidence for the requested ``n`` -- too few
  samples say nothing at the declared content;
* any sample run refused, unbound, unfinished, outside a model's validated
  domain or NOT_SUPPORTED -- dropping it would bias the propagated
  distribution towards the region where the model happens to hold;
* the reported (nominal) value outside ``[min, max]`` -- the interval then
  does not describe the reported value's uncertainty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np

from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.units.quantity import Quantity, dimensionality
from ..scientific.serialization import schema_string
from ._records import (
    require_keys,
    require_list,
    require_mapping,
    require_path,
    require_schema_exact,
    require_text,
    tagged_digest,
)
from .errors import ClaimContractError, ClaimLayerError

DISTRIBUTION_SCHEMA = schema_string("claim_input_distribution")
INPUT_UNCERTAINTY_SCHEMA = schema_string("claim_input_uncertainty")
_SEED_TAG = "crafty.claims.parameter_uq.seed/1"
_TAG = "crafty.claims.parameter_uq/1"
METHOD = "wilks_two_sided_tolerance"

#: The content and confidence a propagated interval must reach (95/95, two-sided).
TOLERANCE_CONTENT = 0.95
TOLERANCE_CONFIDENCE = 0.95
MAX_SAMPLES = 4096


class ParameterUQError(ClaimLayerError):
    """A parameter-uncertainty record cannot be read or does not re-derive."""


class DistributionKind(str, Enum):
    NORMAL = "normal"
    UNIFORM = "uniform"


def _quantity(value: Any, field: str) -> Quantity:
    if isinstance(value, Mapping):
        try:
            return Quantity.from_dict(value)
        except Exception as exc:
            raise ClaimContractError(f"{field} is not a quantity record: {exc}") from exc
    if not isinstance(value, Quantity):
        raise ClaimContractError(f"{field} must be a Quantity (magnitude and unit)")
    return value


@dataclass(frozen=True)
class InputDistribution:
    """What the caller states is uncertain about one input, and why. A declaration, never evidence."""

    path: str
    kind: DistributionKind
    first: Quantity  # NORMAL: mean; UNIFORM: lower
    second: Quantity  # NORMAL: standard deviation; UNIFORM: upper
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", require_path(self.path, field="input_uncertainty.path"))
        try:
            object.__setattr__(self, "kind", DistributionKind(self.kind))
        except ValueError as exc:
            raise ClaimContractError(f"input_uncertainty.kind: {exc}") from exc
        first = _quantity(self.first, "input_uncertainty.first")
        second = _quantity(self.second, "input_uncertainty.second")
        if dimensionality(first.units) != dimensionality(second.units):
            raise ClaimContractError(f"{self.path}: the distribution's two parameters have different dimensions")
        object.__setattr__(self, "first", first)
        object.__setattr__(self, "second", second.to(first.units) if self.kind is DistributionKind.UNIFORM else second)
        object.__setattr__(self, "rationale", require_text(self.rationale, field="input_uncertainty.rationale"))
        if self.kind is DistributionKind.NORMAL:
            if second.magnitude <= 0.0 or not math.isfinite(second.magnitude):
                raise ClaimContractError(f"{self.path}: a normal distribution needs a positive standard deviation")
        elif self.second.magnitude <= self.first.magnitude:
            raise ClaimContractError(f"{self.path}: a uniform distribution needs lower < upper")

    @property
    def center(self) -> Quantity:
        if self.kind is DistributionKind.NORMAL:
            return self.first
        return Quantity(0.5 * (self.first.magnitude + self.second.magnitude), self.first.units)

    def sample(self, unit_draws: np.ndarray) -> list[Quantity]:
        """Map uniform draws in (0, 1) through the inverse CDF, in the distribution's own unit."""
        units = self.first.units
        if self.kind is DistributionKind.NORMAL:
            sigma = self.second.magnitude_as_spread_in(units)
            normal = NormalDist(self.first.magnitude, sigma)
            return [Quantity(normal.inv_cdf(float(u)), units) for u in unit_draws]
        lo, hi = self.first.magnitude, self.second.magnitude
        return [Quantity(lo + float(u) * (hi - lo), units) for u in unit_draws]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DISTRIBUTION_SCHEMA,
            "path": self.path,
            "kind": self.kind.value,
            "first": self.first.to_dict(),
            "second": self.second.to_dict(),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InputDistribution":
        payload = require_mapping(payload, field="input distribution")
        require_keys(payload, required=("schema", "path", "kind", "first", "second", "rationale"), record="input distribution")
        require_schema_exact(payload, DISTRIBUTION_SCHEMA, record="input distribution")
        return cls(payload["path"], payload["kind"], _quantity(payload["first"], "first"), _quantity(payload["second"], "second"), payload["rationale"])


def wilks_confidence(n: int, content: float = TOLERANCE_CONTENT) -> float:
    """Confidence that ``[min, max]`` of ``n`` iid draws covers ``content`` of the distribution."""
    return 1.0 - n * content ** (n - 1) + (n - 1) * content ** n


def minimum_samples(content: float = TOLERANCE_CONTENT, confidence: float = TOLERANCE_CONFIDENCE) -> int:
    n = 2
    while wilks_confidence(n, content) < confidence:
        n += 1
    return n


@dataclass(frozen=True)
class InputUncertainty:
    """The claim's declared input distributions and how many propagated runs to spend on them."""

    distributions: tuple[InputDistribution, ...]
    samples: int

    def __post_init__(self) -> None:
        items = tuple(self.distributions)
        if not items or any(not isinstance(d, InputDistribution) for d in items):
            raise ClaimContractError("input_uncertainty names at least one InputDistribution")
        paths = [d.path for d in items]
        if len(set(paths)) != len(paths):
            raise ClaimContractError("input_uncertainty names one input twice")
        object.__setattr__(self, "distributions", tuple(sorted(items, key=lambda d: d.path)))
        if isinstance(self.samples, bool) or not isinstance(self.samples, int):
            raise ClaimContractError("input_uncertainty.samples must be an integer")
        floor = minimum_samples()
        if not floor <= self.samples <= MAX_SAMPLES:
            raise ClaimContractError(
                f"input_uncertainty.samples must lie in [{floor}, {MAX_SAMPLES}]: fewer than {floor} independent "
                f"runs cannot support a two-sided {TOLERANCE_CONTENT:.0%}/{TOLERANCE_CONFIDENCE:.0%} tolerance interval"
            )

    def path_set(self) -> frozenset[str]:
        return frozenset(d.path for d in self.distributions)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INPUT_UNCERTAINTY_SCHEMA, "distributions": [d.to_dict() for d in self.distributions], "samples": self.samples}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InputUncertainty":
        payload = require_mapping(payload, field="input_uncertainty")
        require_keys(payload, required=("schema", "distributions", "samples"), record="input_uncertainty")
        require_schema_exact(payload, INPUT_UNCERTAINTY_SCHEMA, record="input_uncertainty")
        return cls(
            tuple(InputDistribution.from_dict(d) for d in require_list(payload["distributions"], field="input_uncertainty.distributions")),
            payload["samples"],
        )


def draw_samples(spec: InputUncertainty, seed_material: str) -> list[dict[str, Quantity]]:
    """Independent draws, seeded from ``seed_material`` so the same plan draws the same inputs."""
    seed = int(tagged_digest(_SEED_TAG, {"seed_material": seed_material, "spec": spec.to_dict()})[:16], 16)
    rng = np.random.Generator(np.random.PCG64(seed))
    columns = {}
    for dist in spec.distributions:
        draws = rng.random(spec.samples)
        draws = np.clip(draws, np.finfo(float).tiny, 1.0 - np.finfo(float).eps)
        columns[dist.path] = dist.sample(draws)
    return [{path: columns[path][i] for path in columns} for i in range(spec.samples)]


@dataclass(frozen=True)
class PropagatedRun:
    index: int
    run_id: str
    inputs: dict[str, Quantity]
    value: float | None
    usable: bool
    problem: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "run_id": self.run_id,
            "inputs": {k: v.to_dict() for k, v in sorted(self.inputs.items())},
            "value": self.value,
            "usable": self.usable,
            "problem": self.problem,
        }


@dataclass(frozen=True)
class ParameterUncertaintyEstimate:
    quantified: bool
    quantity: str
    units: str
    nominal: float
    runs: tuple[PropagatedRun, ...]
    content: float
    confidence: float | None
    lower: float | None
    upper: float | None
    failure_reason: str | None

    def to_uncertainty(self) -> Uncertainty:
        if not self.quantified:
            return Uncertainty.unknown(f"parameter uncertainty not quantified: {self.failure_reason}")
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(self.lower, self.units),
            upper=Quantity(self.upper, self.units),
            source=f"parameter_propagation:{self.digest[:16]}",
            method=(
                f"{METHOD}: [min, max] of {len(self.runs)} independent propagated runs contains at least "
                f"{self.content:.0%} of the output distribution with confidence {self.confidence:.4f}"
            ),
            notes="propagates only the caller-declared input distributions; not numerical, measurement or model-form uncertainty",
            source_kind=UncertaintySource.PARAMETER,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": METHOD,
            "quantified": self.quantified,
            "quantity": self.quantity,
            "units": self.units,
            "nominal": self.nominal,
            "runs": [r.to_dict() for r in self.runs],
            "content": self.content,
            "confidence": self.confidence,
            "lower": self.lower,
            "upper": self.upper,
            "failure_reason": self.failure_reason,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def estimate_parameter_uncertainty(
    runs: Sequence[PropagatedRun], *, quantity: str, units: str, nominal: float,
    content: float = TOLERANCE_CONTENT, required_confidence: float = TOLERANCE_CONFIDENCE,
) -> ParameterUncertaintyEstimate:
    """Wilks' interval over the propagated runs, or UNKNOWN. Pure."""
    runs = tuple(sorted(runs, key=lambda r: r.index))
    base = dict(quantity=quantity, units=units, nominal=float(nominal), runs=runs, content=content)
    n = len(runs)
    unusable = [r for r in runs if not r.usable]
    if unusable:
        return ParameterUncertaintyEstimate(
            quantified=False, confidence=None, lower=None, upper=None,
            failure_reason=(
                f"{len(unusable)} of {n} propagated runs are not usable (first: run {unusable[0].index}: "
                f"{unusable[0].problem}); dropping them would bias the distribution toward where the model holds"
            ),
            **base,
        )
    gamma = wilks_confidence(n, content)
    if gamma < required_confidence:
        return ParameterUncertaintyEstimate(
            quantified=False, confidence=gamma, lower=None, upper=None,
            failure_reason=f"{n} runs give confidence {gamma:.4f} < {required_confidence} at content {content}",
            **base,
        )
    values = [float(r.value) for r in runs]
    if any(not math.isfinite(v) for v in values):
        return ParameterUncertaintyEstimate(quantified=False, confidence=gamma, lower=None, upper=None, failure_reason="a propagated value is not finite", **base)
    lo, hi = min(values), max(values)
    if not lo <= nominal <= hi:
        return ParameterUncertaintyEstimate(
            quantified=False, confidence=gamma, lower=lo, upper=hi,
            failure_reason=f"the reported value {nominal!r} lies outside the propagated range [{lo!r}, {hi!r}]",
            **base,
        )
    return ParameterUncertaintyEstimate(quantified=True, confidence=gamma, lower=lo, upper=hi, failure_reason=None, **base)


def parameter_estimate_from_dict(payload: Mapping[str, Any]) -> ParameterUncertaintyEstimate:
    """Re-derive a recorded estimate from its runs; a record whose outputs were edited is refused."""
    try:
        runs = tuple(
            PropagatedRun(
                int(r["index"]), str(r["run_id"]),
                {k: Quantity.from_dict(v) for k, v in r["inputs"].items()},
                None if r["value"] is None else float(r["value"]), bool(r["usable"]), r["problem"],
            )
            for r in payload["runs"]
        )
        rebuilt = estimate_parameter_uncertainty(
            runs, quantity=payload["quantity"], units=payload["units"], nominal=payload["nominal"], content=payload["content"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ParameterUQError(f"a parameter-uncertainty record is not readable: {exc}") from exc
    if rebuilt.to_dict() != dict(payload):
        raise ParameterUQError("a parameter-uncertainty record does not re-derive from the runs it carries")
    return rebuilt


__all__ = [
    "DistributionKind",
    "InputDistribution",
    "InputUncertainty",
    "ParameterUQError",
    "ParameterUncertaintyEstimate",
    "PropagatedRun",
    "draw_samples",
    "estimate_parameter_uncertainty",
    "minimum_samples",
    "parameter_estimate_from_dict",
    "wilks_confidence",
]
