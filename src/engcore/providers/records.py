"""Generic provider execution record: what an external provider computed, bound to its identity.

Classification is ``provider_computation_not_evidence``: a converged provider
run is a numerical fact about that configuration, never validation.  Output
uncertainty is UNKNOWN unless the provider adapter can compute it from declared
information; a failed record exposes no outputs; non-finite outputs are refused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from .identity import ProviderExecutionIdentity, content_digest

CLASSIFICATION = "provider_computation_not_evidence"


class ProviderRefusal(InvalidScientificProblem):
    """A provider execution was refused (input generation, unsupported case, failure, bad output)."""


@dataclass(frozen=True)
class QuantitySeries:
    """A provider output over time: ``times`` (seconds, on the request's BIG 2 basis) and values."""

    quantity_id: str
    unit: str
    times_s: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.times_s) != len(self.values) or not self.values:
            raise ProviderRefusal(f"series {self.quantity_id!r} is empty or misaligned")
        if not all(math.isfinite(v) for v in self.values) or not all(math.isfinite(t) for t in self.times_s):
            raise ProviderRefusal(f"series {self.quantity_id!r} contains non-finite values")
        if any(b < a for a, b in zip(self.times_s, self.times_s[1:])):
            raise ProviderRefusal(f"series {self.quantity_id!r} times are not ordered")
        Quantity(1, self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {"quantity_id": self.quantity_id, "unit": self.unit, "times_s": [repr(t) for t in self.times_s],
                "values": [repr(v) for v in self.values]}


@dataclass(frozen=True)
class ProviderExecutionRecord:
    identity: ProviderExecutionIdentity
    succeeded: bool
    reason: str
    scalars: Mapping[str, Quantity] = field(default_factory=dict)
    series: tuple[QuantitySeries, ...] = ()
    #: named array outputs (e.g. nodal fields) with their unit: name -> (unit, ndarray)
    arrays: Mapping[str, tuple[str, Any]] = field(default_factory=dict)
    #: generated provider configuration, inspectable and replayable (name -> text)
    artifacts: Mapping[str, str] = field(default_factory=dict)
    #: process-boundary record digest for file-based providers
    process_digest: str = ""
    #: operational metrics (startup/solve/parse seconds, problem size): NOT identity
    metrics: Mapping[str, Any] = field(default_factory=dict)
    uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.unknown(
        "provider output uncertainty is not quantified; solver convergence says nothing about model or input uncertainty"))

    def __post_init__(self) -> None:
        if not self.succeeded:
            if self.scalars or self.series or self.arrays:
                raise ProviderRefusal("a failed provider execution exposes no outputs")
            if not str(self.reason).strip():
                raise ProviderRefusal("a failed provider execution states its reason")
            return
        for name, q in self.scalars.items():
            if not isinstance(q, Quantity) or not math.isfinite(float(q.magnitude)):
                raise ProviderRefusal(f"output {name!r} is not a finite Quantity")
        for name, (unit, arr) in self.arrays.items():
            a = np.asarray(arr, dtype=float)
            if a.size == 0 or not np.all(np.isfinite(a)):
                raise ProviderRefusal(f"array output {name!r} is empty or non-finite")
            Quantity(1, unit)
        requested = set(self.identity.output_request)
        produced = set(self.scalars) | {s.quantity_id for s in self.series} | set(self.arrays)
        missing = sorted(requested - produced)
        if missing:
            raise ProviderRefusal(f"provider produced no {missing}; a missing output is never a default")

    def series_for(self, quantity_id: str) -> QuantitySeries:
        for s in self.series:
            if s.quantity_id == quantity_id:
                return s
        raise ProviderRefusal(f"no series {quantity_id!r}")

    @property
    def execution_identity(self) -> str:
        return self.identity.digest

    def to_dict(self) -> dict[str, Any]:
        return {"classification": CLASSIFICATION, "identity": self.identity.to_dict(), "succeeded": self.succeeded,
                "reason": self.reason, "scalars": {k: v.to_dict() for k, v in sorted(self.scalars.items())},
                "series": [s.to_dict() for s in self.series],
                "arrays": {k: [u, content_digest(np.ascontiguousarray(np.asarray(a, dtype="<f8")).tobytes())] for k, (u, a) in sorted(self.arrays.items())},
                "artifacts": {k: content_digest(v) for k, v in sorted(self.artifacts.items())},
                "process_digest": self.process_digest, "uncertainty": self.uncertainty.to_dict()}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def failed(identity: ProviderExecutionIdentity, reason: str, **kw) -> ProviderExecutionRecord:
    return ProviderExecutionRecord(identity, False, reason, **kw)
