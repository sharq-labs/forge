"""D2 — deterministic mixed-variable generation geometry.

This module maps a domain-neutral DesignSpace onto a reproducible Halton
sequence. It does not optimize, rank, evaluate, or interpret system-specific
constraints. Scientific values remain typed at the design boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue, ScientificValue
from ..scientific.ir.variables import VariableKind
from ..scientific.units.quantity import Quantity, dimensionality
from .space import DesignSpace

HALTON_V1 = "halton_v1"


def _first_primes(count: int) -> tuple[int, ...]:
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise InvalidScientificProblem("Halton dimension must be a positive integer")
    primes: list[int] = []
    candidate = 2
    while len(primes) < count:
        is_prime = True
        divisor = 2
        while divisor * divisor <= candidate:
            if candidate % divisor == 0:
                is_prime = False
                break
            divisor += 1
        if is_prime:
            primes.append(candidate)
        candidate += 1
    return tuple(primes)


def _radical_inverse(index: int, base: int) -> float:
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise InvalidScientificProblem("Halton sequence index must be >= 1")
    inverse = 1.0 / base
    factor = inverse
    value = 0.0
    current = index
    while current:
        current, digit = divmod(current, base)
        value += digit * factor
        factor *= inverse
    # Radical inverse is mathematically in [0, 1). Guard floating arithmetic.
    if not isfinite(value) or not 0.0 <= value < 1.0:
        raise InvalidScientificProblem(
            f"Halton radical inverse escaped [0, 1): index={index}, base={base}"
        )
    return value


@dataclass(frozen=True)
class MixedVariableSampler:
    """Fail-closed mixed-variable decoder for one exact DesignSpace.

    D0 may represent more declarations than D2 can safely generate. This
    sampler therefore performs an explicit *searchability* validation rather
    than silently ignoring bounds, units, or discrete semantics.
    """

    design_space: DesignSpace

    def __post_init__(self) -> None:
        if not isinstance(self.design_space, DesignSpace):
            raise InvalidScientificProblem("mixed sampler requires DesignSpace")
        for variable in self.design_space.variables:
            self._require_searchable(variable)
        object.__setattr__(self, "_bases", _first_primes(len(self.design_space.variables)))

    @staticmethod
    def _require_dimensionless(variable) -> None:
        if dimensionality(variable.unit) != "dimensionless":
            raise InvalidScientificProblem(
                f"{variable.kind.value} design variable {variable.name!r} must be "
                "dimensionless for D2 generation"
            )

    @classmethod
    def _require_searchable(cls, variable) -> None:
        if variable.kind is VariableKind.CONTINUOUS:
            if not variable.is_bounded:
                raise InvalidScientificProblem(
                    f"continuous design variable {variable.name!r} requires finite "
                    "lower and upper bounds for D2 generation"
                )
            return

        if variable.kind is VariableKind.INTEGER:
            cls._require_dimensionless(variable)
            if not variable.is_bounded:
                raise InvalidScientificProblem(
                    f"integer design variable {variable.name!r} requires finite "
                    "lower and upper bounds for D2 generation"
                )
            low = variable.lower.magnitude
            high = variable.upper.magnitude
            if not float(low).is_integer() or not float(high).is_integer():
                raise InvalidScientificProblem(
                    f"integer design variable {variable.name!r} requires exactly "
                    f"integer-valued bounds, got {low!r}..{high!r}"
                )
            return

        if variable.kind is VariableKind.CATEGORICAL:
            cls._require_dimensionless(variable)
            if variable.lower is not None or variable.upper is not None:
                raise InvalidScientificProblem(
                    f"categorical design variable {variable.name!r} cannot carry "
                    "numeric bounds in D2 generation"
                )
            return

        if variable.kind is VariableKind.BOOLEAN:
            cls._require_dimensionless(variable)
            if variable.lower is not None or variable.upper is not None:
                raise InvalidScientificProblem(
                    f"boolean design variable {variable.name!r} cannot carry "
                    "numeric bounds in D2 generation"
                )
            return

        raise InvalidScientificProblem(
            f"unsupported D2 variable kind {variable.kind!r}"
        )

    @property
    def dimension(self) -> int:
        return len(self.design_space.variables)

    @property
    def fully_discrete_cardinality(self) -> int | None:
        """Exact number of unique assignments when no continuous variable exists."""
        cardinality = 1
        for variable in self.design_space.variables:
            if variable.kind is VariableKind.CONTINUOUS:
                return None
            if variable.kind is VariableKind.INTEGER:
                low = int(variable.lower.magnitude)
                high = int(variable.upper.magnitude)
                cardinality *= high - low + 1
            elif variable.kind is VariableKind.CATEGORICAL:
                cardinality *= len(variable.categories)
            elif variable.kind is VariableKind.BOOLEAN:
                cardinality *= 2
        return cardinality

    def point(self, sequence_index: int) -> tuple[float, ...]:
        if isinstance(sequence_index, bool) or not isinstance(sequence_index, int):
            raise InvalidScientificProblem("Halton sequence index must be an integer")
        if sequence_index < 1:
            raise InvalidScientificProblem("Halton sequence index must be >= 1")
        return tuple(
            _radical_inverse(sequence_index, base) for base in self._bases
        )

    def decode_point(self, point: Sequence[float]) -> dict[str, ScientificValue]:
        values = tuple(float(component) for component in point)
        if len(values) != self.dimension:
            raise InvalidScientificProblem(
                f"mixed point length {len(values)} does not match design-space "
                f"dimension {self.dimension}"
            )
        if any(not isfinite(value) or not 0.0 <= value < 1.0 for value in values):
            raise InvalidScientificProblem(
                "D2 generation points must contain finite components in [0, 1)"
            )

        assignments: dict[str, ScientificValue] = {}
        for variable, component in zip(self.design_space.variables, values):
            if variable.kind is VariableKind.CONTINUOUS:
                low = variable.lower.magnitude
                high = variable.upper.magnitude
                assignments[variable.name] = Quantity(
                    low + component * (high - low), variable.unit
                )
                continue

            if variable.kind is VariableKind.INTEGER:
                low = int(variable.lower.magnitude)
                high = int(variable.upper.magnitude)
                count = high - low + 1
                assignments[variable.name] = IntegerValue(
                    low + min(int(component * count), count - 1)
                )
                continue

            if variable.kind is VariableKind.CATEGORICAL:
                count = len(variable.categories)
                index = min(int(component * count), count - 1)
                assignments[variable.name] = CategoricalValue(
                    variable.categories[index], vocabulary=variable.categories
                )
                continue

            if variable.kind is VariableKind.BOOLEAN:
                assignments[variable.name] = BooleanValue(component >= 0.5)
                continue

            raise InvalidScientificProblem(
                f"unsupported D2 variable kind {variable.kind!r}"
            )

        # D0 remains the authority on exact assignment coverage/types/bounds.
        return self.design_space.validate_assignments(assignments)

    def assignments_at(self, sequence_index: int) -> dict[str, ScientificValue]:
        return self.decode_point(self.point(sequence_index))
