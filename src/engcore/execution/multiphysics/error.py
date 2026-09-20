"""Conservative accounting of coupling-induced numerical error.

This record is deliberately separate from physical/model-form uncertainty.
It contains only numerical errors the coupling runtime actually quantified
(for example mapping round-trip or conservative-transfer residual) and combines
them by linear sum, making no independence assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

from ...scientific.errors import InvalidScientificProblem


@dataclass(frozen=True)
class CouplingErrorContribution:
    source: str
    relative_bound: float
    method: str

    def __post_init__(self) -> None:
        source = str(self.source).strip()
        method = str(self.method).strip()
        bound = float(self.relative_bound)
        if (
            not source
            or not method
            or not math.isfinite(bound)
            or bound < 0.0
        ):
            raise InvalidScientificProblem(
                "coupling error contribution requires source, method and "
                "finite non-negative bound"
            )
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "relative_bound", bound)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relative_bound": self.relative_bound,
            "method": self.method,
        }


@dataclass(frozen=True)
class CouplingErrorBudget:
    contributions: tuple[CouplingErrorContribution, ...]

    def __post_init__(self) -> None:
        items = tuple(self.contributions)
        if any(
            not isinstance(item, CouplingErrorContribution)
            for item in items
        ):
            raise InvalidScientificProblem(
                "coupling error budget requires typed contributions"
            )
        object.__setattr__(
            self,
            "contributions",
            tuple(
                sorted(
                    items,
                    key=lambda item: (item.source, item.method),
                )
            ),
        )

    @property
    def relative_bound(self) -> float | None:
        if not self.contributions:
            return None
        return sum(
            item.relative_bound for item in self.contributions
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "coupling_numerical_error",
            "combination": (
                "linear_sum_no_independence_assumption"
            ),
            "relative_bound": self.relative_bound,
            "contributions": [
                item.to_dict() for item in self.contributions
            ],
            "notice": (
                "Coupling-induced numerical error only; not physical, "
                "parameter, measurement or model-form uncertainty."
            ),
        }

    @classmethod
    def from_mapping_diagnostics(
        cls,
        diagnostics: Iterable[Mapping[str, Any]],
    ) -> "CouplingErrorBudget":
        contributions: list[CouplingErrorContribution] = []
        occurrences: dict[tuple[str, str], int] = {}
        for item in diagnostics:
            edge_id = str(item.get("edge_id", "")).strip()
            mapping = item.get("mapping")
            if not edge_id or not isinstance(mapping, Mapping):
                continue
            for field, method in (
                (
                    "round_trip_relative_l2",
                    "mapping_round_trip",
                ),
                (
                    "conservation_relative_error",
                    "mapping_conservation",
                ),
            ):
                raw = mapping.get(field)
                if raw is None:
                    continue
                key = (edge_id, method)
                occurrence = occurrences.get(key, 0) + 1
                occurrences[key] = occurrence
                contributions.append(
                    CouplingErrorContribution(
                        source=(
                            f"edge:{edge_id}:occurrence:{occurrence}"
                        ),
                        relative_bound=float(raw),
                        method=method,
                    )
                )
        return cls(tuple(contributions))
