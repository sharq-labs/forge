"""Optimizer adapter contract.

The boundary this module defends:

    ScientificProblem / Quantity / ScientificResult   <- unit-aware, always
                     |
             CandidateCodec (here)                    <- the ONE translation
                     v
    normalized float vectors                          <- what search sees

The Scientific Core depends on the :class:`NumericSearchBackend` *protocol*,
never on a concrete optimizer. ``stacked_v0301`` and ``adaptive_stacked_v034``
are existing research backends; nothing here imports them, and this module
must never import them. A future adapter package wires a backend to this
protocol without either side learning about the other.

The optimizer never sees units. The scientific layer never sees a bare
number. The codec is where — and only where — those two facts meet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..errors import InvalidScientificProblem, ScientificCoreError
from ..ir.problem import ScientificProblem
from ..ir.variables import ScientificVariable, VariableKind
from ..units.quantity import Quantity


@runtime_checkable
class NumericSearchBackend(Protocol):
    """Minimal ask/tell contract a numeric optimizer must satisfy.

    Vectors are normalized to the unit hypercube: every backend sees the same
    geometry regardless of the physical units of the problem.
    """

    def ask(self, count: int = 1) -> Sequence[Sequence[float]]:
        """Propose ``count`` points in [0, 1]^d."""
        ...

    def tell(
        self, points: Sequence[Sequence[float]], scores: Sequence[float]
    ) -> None:
        """Report observed scores for previously proposed points."""
        ...


@dataclass(frozen=True)
class CandidateCodec:
    """Two-way translation between scientific candidates and unit-cube vectors.

    Round-trip exactness is a contract, not an aspiration: ``decode(encode(c))``
    must reproduce ``c`` in the variables' declared units.
    """

    variables: tuple[ScientificVariable, ...]

    def __post_init__(self) -> None:
        variables = tuple(self.variables)
        if not variables:
            raise InvalidScientificProblem(
                "a codec requires at least one design variable"
            )
        names = [v.name for v in variables]
        if len(set(names)) != len(names):
            raise InvalidScientificProblem("codec variable names must be unique")
        for variable in variables:
            if not variable.is_bounded:
                raise InvalidScientificProblem(
                    f"variable {variable.name!r} needs finite bounds to be "
                    f"searched; normalization is undefined without them"
                )
            if variable.kind is not VariableKind.CONTINUOUS:
                # V0 scope: representation for other kinds exists, but encoding
                # them is deferred rather than silently approximated.
                raise InvalidScientificProblem(
                    f"variable {variable.name!r} of kind "
                    f"{variable.kind.value!r} is not encodable in V0; only "
                    f"continuous variables are supported"
                )
        object.__setattr__(self, "variables", variables)

    @classmethod
    def from_problem(cls, problem: ScientificProblem) -> "CandidateCodec":
        return cls(variables=problem.design_variables)

    # ---- geometry --------------------------------------------------------
    @property
    def dimension(self) -> int:
        return len(self.variables)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables)

    def bounds(self) -> tuple[tuple[float, float], ...]:
        """Physical bounds in each variable's declared unit."""
        return tuple(
            (v.lower.magnitude, v.upper.magnitude) for v in self.variables
        )

    # ---- translation -----------------------------------------------------
    def encode(self, candidate: Mapping[str, Quantity]) -> tuple[float, ...]:
        """Scientific candidate -> normalized vector in [0, 1]^d.

        Rejects a candidate outside its declared physical bounds. Producing a
        component outside the unit cube would break this codec's own contract
        and hand a search backend a point the problem never authorized.
        """
        vector: list[float] = []
        for variable in self.variables:
            if variable.name not in candidate:
                raise ScientificCoreError(
                    f"candidate is missing variable {variable.name!r}"
                )
            value = candidate[variable.name]
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"candidate value {variable.name!r} must be a Quantity — "
                    f"the codec never accepts unit-less scientific input"
                )
            # Raises on out-of-bounds; conversion also proves dimensionality.
            magnitude = variable.require_within_bounds(value).magnitude
            low = variable.lower.magnitude
            high = variable.upper.magnitude
            component = (magnitude - low) / (high - low)
            # Defensive: bound membership already guarantees this, but a
            # silent escape here would be unrecoverable downstream.
            if not 0.0 <= component <= 1.0:
                raise ScientificCoreError(
                    f"variable {variable.name!r} normalized to {component!r}, "
                    f"outside the unit cube"
                )
            vector.append(component)
        return tuple(vector)

    def decode(self, vector: Sequence[float]) -> dict[str, Quantity]:
        """Normalized vector -> scientific candidate with units restored.

        Rejects any component outside ``[0, 1]``: extrapolating past a
        declared design bound would silently invent a candidate the problem
        never authorized. A backend that legitimately proposes just outside
        the cube must call :meth:`clip` explicitly, so the correction is
        recorded rather than assumed.
        """
        values = list(vector)
        if len(values) != self.dimension:
            raise ScientificCoreError(
                f"vector of length {len(values)} does not match codec "
                f"dimension {self.dimension}"
            )
        candidate: dict[str, Quantity] = {}
        for variable, component in zip(self.variables, values):
            component = float(component)
            if not math.isfinite(component):
                raise ScientificCoreError(
                    f"non-finite component for variable {variable.name!r}"
                )
            if not 0.0 <= component <= 1.0:
                raise ScientificCoreError(
                    f"component {component!r} for variable "
                    f"{variable.name!r} lies outside [0, 1]; use clip() to "
                    f"correct a proposal explicitly"
                )
            low = variable.lower.magnitude
            high = variable.upper.magnitude
            candidate[variable.name] = Quantity(
                low + component * (high - low), variable.unit
            )
        return candidate

    def clip(self, vector: Sequence[float]) -> tuple[float, ...]:
        """Explicitly clamp a proposal into the unit cube.

        The sanctioned correction path for backends that propose slightly
        outside a box constraint. Never called implicitly by encode/decode.
        """
        clipped: list[float] = []
        for value in vector:
            component = float(value)
            if not math.isfinite(component):
                raise ScientificCoreError(
                    "cannot clip a non-finite component"
                )
            clipped.append(min(1.0, max(0.0, component)))
        return tuple(clipped)


@dataclass(frozen=True)
class ObjectiveEncoder:
    """Turns a unit-carrying objective value into the scalar a search sees.

    Search backends in this project maximize. Encoding the direction here —
    once, explicitly, in the adapter — is what keeps sense-handling out of
    both the scientific layer and the optimizer.
    """

    metric: str
    unit: str
    sense: int  # +1 maximize, -1 minimize

    @classmethod
    def from_objective(cls, objective) -> "ObjectiveEncoder":
        return cls(
            metric=objective.metric, unit=objective.unit, sense=objective.sense
        )

    def encode(self, value: Quantity) -> float:
        if not isinstance(value, Quantity):
            raise ScientificCoreError(
                f"objective value for {self.metric!r} must be a Quantity"
            )
        return self.sense * value.to(self.unit).magnitude

    def decode(self, score: float) -> Quantity:
        return Quantity(self.sense * float(score), self.unit)


@dataclass(frozen=True)
class OptimizerAdapter:
    """Bundles the codec and objective encoding for one experiment.

    This is the whole contract a future execution layer needs: it can drive
    any :class:`NumericSearchBackend` against any :class:`ScientificProblem`
    without either side importing the other.
    """

    codec: CandidateCodec
    objective: ObjectiveEncoder

    @classmethod
    def for_problem(
        cls, problem: ScientificProblem, objective_name: str | None = None
    ) -> "OptimizerAdapter":
        if not problem.objectives:
            raise InvalidScientificProblem(
                f"problem {problem.problem_id!r} declares no objective to search"
            )
        if objective_name is None:
            if len(problem.objectives) > 1:
                raise InvalidScientificProblem(
                    "problem declares multiple objectives; name the one to "
                    "search — the adapter never picks silently"
                )
            objective = problem.objectives[0]
        else:
            objective = next(
                (o for o in problem.objectives if o.name == objective_name), None
            )
            if objective is None:
                raise InvalidScientificProblem(
                    f"unknown objective {objective_name!r}"
                )
        return cls(
            codec=CandidateCodec.from_problem(problem),
            objective=ObjectiveEncoder.from_objective(objective),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "optimizer_adapter/1",
            "variables": list(self.codec.names),
            "bounds": [list(b) for b in self.codec.bounds()],
            "objective_metric": self.objective.metric,
            "objective_unit": self.objective.unit,
            "objective_sense": self.objective.sense,
        }
