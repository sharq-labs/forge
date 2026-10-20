"""The experimental problem a Minimal Mind works on, stated without any benchmark vocabulary.

A problem is what an experimenter is told before the first query: the settable inputs and the box they may be set in,
the passively observed covariates (returned with every observation, never set), the observable, the query budget and
cost, and the region where the conclusion will be used.  It carries no law, kind, tolerance or truth.

Two presentations of one problem that differ only in NAMES or in the ORDER of the inputs are the same problem to the
Mind: :meth:`ExperimentalProblem.canonical_inputs` orders inputs by their box, and :meth:`design_seed` is derived from
the box, the budget and the region values only.  Renaming or reordering therefore leaves the experiment design, the
hypotheses and the conclusion unchanged up to the renaming (acceptance test 5).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from typing import Any, Mapping

PROBLEM_SCHEMA = "forge.mind.minimal.problem/1"


class ProblemRefused(ValueError):
    """A problem statement the Mind cannot work on (no settable input, a non-positive range, a missing budget)."""


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class InputSpec:
    name: str
    low: float
    high: float
    unit: str = "1"

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ProblemRefused("an input has a name")
        lo, hi = float(self.low), float(self.high)
        if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo < hi):
            raise ProblemRefused(f"input {self.name!r}: the settable box is a positive interval low < high")
        object.__setattr__(self, "low", lo)
        object.__setattr__(self, "high", hi)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "low": self.low, "high": self.high, "unit": self.unit}


@dataclass(frozen=True)
class ExperimentalProblem:
    problem_id: str
    inputs: tuple[InputSpec, ...]
    covariates: tuple[str, ...]
    observable: str
    observable_unit: str
    budget: int
    query_cost: float
    region: Mapping[str, tuple[float, float]]

    def __post_init__(self) -> None:
        if not str(self.problem_id).strip():
            raise ProblemRefused("a problem has an id")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "covariates", tuple(sorted(self.covariates)))
        if not self.inputs:
            raise ProblemRefused("a problem without a settable input admits no experiment")
        names = [x.name for x in self.inputs] + list(self.covariates) + [self.observable]
        if len(set(names)) != len(names):
            raise ProblemRefused("input, covariate and observable names are distinct")
        if isinstance(self.budget, bool) or not isinstance(self.budget, int) or self.budget < 1:
            raise ProblemRefused("the query budget is a positive integer")
        if not (math.isfinite(float(self.query_cost)) and float(self.query_cost) > 0):
            raise ProblemRefused("the query cost is positive")
        region = {}
        for x in self.inputs:
            lo, hi = self.region.get(x.name, (x.low, x.high))
            lo, hi = float(lo), float(hi)
            if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo <= hi):
                raise ProblemRefused(f"the region for {x.name!r} is a positive interval")
            region[x.name] = (lo, hi)
        unknown = set(self.region) - {x.name for x in self.inputs}
        if unknown:
            raise ProblemRefused(f"the region names unknown inputs {sorted(unknown)}")
        object.__setattr__(self, "region", region)

    # ---- canonical, name-free views -------------------------------------------------------------------------------
    def canonical_inputs(self) -> tuple[InputSpec, ...]:
        """Inputs ordered by their box (then region): independent of names and of presentation order."""
        return tuple(sorted(self.inputs, key=lambda x: (x.low, x.high, self.region[x.name], x.unit)))

    def design_seed(self, seed: int) -> str:
        """The Mind's randomness is derived from the problem's numbers only (never names, never the pseudonymous id)."""
        shape = [[x.low, x.high, list(self.region[x.name])] for x in self.canonical_inputs()]
        return _digest({"seed": int(seed), "shape": shape, "covariates": len(self.covariates), "budget": self.budget})

    def rng(self, seed: int, purpose: str) -> random.Random:
        return random.Random(f"{self.design_seed(seed)}\n{purpose}")

    @property
    def extrapolates(self) -> bool:
        """Whether the region where the conclusion will be used leaves the box any experiment can reach."""
        return any(self.region[x.name][0] < x.low * (1 - 1e-12) or self.region[x.name][1] > x.high * (1 + 1e-12)
                   for x in self.inputs)

    def region_points(self, n: int = 24) -> list[dict[str, float]]:
        """A deterministic, name-free sample of the region (corners of the log box when few, else a Halton-like grid)."""
        xs = self.canonical_inputs()
        pts = []
        for i in range(n):
            pt = {}
            for j, x in enumerate(xs):
                lo, hi = self.region[x.name]
                frac = _van_der_corput(i + 1, _PRIMES[j % len(_PRIMES)])
                pt[x.name] = math.exp(math.log(lo) + frac * (math.log(hi) - math.log(lo))) if hi > lo else lo
            pts.append(pt)
        return pts

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROBLEM_SCHEMA, "problem_id": self.problem_id, "inputs": [x.to_dict() for x in self.inputs],
                "covariates": list(self.covariates), "observable": self.observable, "observable_unit": self.observable_unit,
                "budget": self.budget, "query_cost": float(self.query_cost),
                "region": {k: list(v) for k, v in sorted(self.region.items())}}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


_PRIMES = (2, 3, 5, 7, 11, 13)


def _van_der_corput(i: int, base: int) -> float:
    out, f = 0.0, 1.0 / base
    while i > 0:
        out += f * (i % base)
        i //= base
        f /= base
    return out


__all__ = ["ExperimentalProblem", "InputSpec", "PROBLEM_SCHEMA", "ProblemRefused"]
