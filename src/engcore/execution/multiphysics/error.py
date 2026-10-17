"""Field-mapping diagnostics a coupled run measured about its own transfers.

Phase 1 BR3: this record used to be a "coupling error budget" whose
``relative_bound`` summed round-trip and conservation residuals.  Neither is a
bound.  A round-trip residual measures how well a mapping and its reverse
undo each other; it does not bound the error of the forward transfer.  A
conservation residual measures an integral imbalance; it says nothing about
the transferred field's pointwise accuracy.  Summing them produced a number
with no meaning that was then stored as ``coupling_error_bound``.

What remains is a typed list of DIAGNOSTICS, each with its evidence class and
the method that produced it.  Nothing here is summed, nothing is called a
bound, and the run record's ``coupling_error_bound`` is no longer filled from
it.  :mod:`.numerical_error` reads these as diagnostic evidence beside the
error sources they cannot close.  This is coupling-numerical evidence only:
not physical, parameter, measurement or model-form uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

from ...scientific.errors import InvalidScientificProblem

#: kind of the record stored in ``final_outputs["_coupling_error"]``
MAPPING_DIAGNOSTICS_KIND = "coupling_mapping_diagnostics"

#: evidence class of each measured quantity; neither is an error bound
EVIDENCE_CLASSES = {
    "mapping_round_trip": "round_trip_residual",
    "mapping_conservation": "conservation_residual",
}


@dataclass(frozen=True)
class CouplingErrorContribution:
    """One measured mapping diagnostic (a residual), never a bound."""

    source: str
    relative_value: float
    method: str

    def __post_init__(self) -> None:
        source = str(self.source).strip()
        method = str(self.method).strip()
        value = float(self.relative_value)
        if not source or method not in EVIDENCE_CLASSES or not math.isfinite(value) or value < 0.0:
            raise InvalidScientificProblem(
                "a mapping diagnostic requires a source, a known method "
                f"({sorted(EVIDENCE_CLASSES)}) and a finite non-negative value"
            )
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "relative_value", value)

    @property
    def evidence_class(self) -> str:
        return EVIDENCE_CLASSES[self.method]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relative_value": self.relative_value,
            "method": self.method,
            "evidence_class": self.evidence_class,
        }


@dataclass(frozen=True)
class CouplingErrorBudget:
    """The mapping diagnostics of one run (name kept for import compatibility; it is not a budget)."""

    contributions: tuple[CouplingErrorContribution, ...]

    def __post_init__(self) -> None:
        items = tuple(self.contributions)
        if any(
            not isinstance(item, CouplingErrorContribution)
            for item in items
        ):
            raise InvalidScientificProblem(
                "mapping diagnostics require typed contributions"
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": MAPPING_DIAGNOSTICS_KIND,
            "evidence_class": "diagnostic_not_bound",
            "contributions": [
                item.to_dict() for item in self.contributions
            ],
            "notice": (
                "Field-mapping diagnostics only. A round-trip residual does not bound the forward "
                "transfer error and a conservation residual does not bound the field error; nothing "
                "here is summed or read as a bound. Not physical, parameter, measurement or "
                "model-form uncertainty."
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
                        relative_value=float(raw),
                        method=method,
                    )
                )
        return cls(tuple(contributions))


__all__ = [
    "CouplingErrorBudget",
    "CouplingErrorContribution",
    "EVIDENCE_CLASSES",
    "MAPPING_DIAGNOSTICS_KIND",
]
