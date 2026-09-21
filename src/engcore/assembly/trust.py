"""Completeness, not sufficiency: did every required trust protocol actually run?

The question a certification gate used to ask was "did some validation pass?".
Subset success is not completeness. A pack declaring four validation protocols
and executing one reports four-quarters of nothing, and the record read as a
clean pass because every result present was valid.

So the two completeness reports here compare **exact sets**: what the frozen
Composition Pack snapshot says this blueprint requires, against what the
authorized run actually executed. The difference is enumerated in both
directions, because both directions are defects:

``missing``
    a required protocol never ran.
``unexpected``
    a protocol ran that the pack does not require here -- a substitution, a
    stale artifact, or a protocol belonging to another blueprint.

Version is part of identity. ``ocv_adequacy@1`` executing where
``ocv_adequacy@2`` is required is a missing protocol *and* an unexpected one,
which is exactly what a silent version drift looks like from outside.

UNENFORCEABLE IS NOT SATISFIED
-------------------------------
A snapshot written before requirements were recorded cannot state its required
set. That case reports ``enforceable=False`` and never ``complete=True``: an
old record does not get to certify itself by having nothing to compare against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from ..compositionpacks.snapshot import CompositionPackSnapshot
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.serialization import require_schema, schema_string
from ..sria.uncertainty import UncertaintyChannel

PROTOCOL_COMPLETENESS_SCHEMA = schema_string("forge_protocol_completeness")
UQ_CELL_SCHEMA = schema_string("forge_uq_coverage_cell")
UQ_COVERAGE_SCHEMA = schema_string("forge_uq_coverage")


@dataclass(frozen=True)
class ProtocolCompleteness:
    """Exact-set comparison of required against executed protocols."""

    kind: str
    blueprint_id: str
    required: tuple[tuple[str, str], ...]
    executed: tuple[tuple[str, str], ...]
    enforceable: bool

    def __post_init__(self) -> None:
        for label in ("kind", "blueprint_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"protocol completeness requires {label}")
            object.__setattr__(self, label, value)
        for label in ("required", "executed"):
            items = tuple(
                sorted((str(a), str(b)) for a, b in getattr(self, label))
            )
            object.__setattr__(self, label, items)
        if not isinstance(self.enforceable, bool):
            raise InvalidScientificProblem("enforceable must be a boolean")

    @property
    def missing(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(set(self.required) - set(self.executed)))

    @property
    def unexpected(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(set(self.executed) - set(self.required)))

    @property
    def duplicated(self) -> tuple[tuple[str, str], ...]:
        seen: dict[tuple[str, str], int] = {}
        for item in self.executed:
            seen[item] = seen.get(item, 0) + 1
        return tuple(sorted(key for key, count in seen.items() if count > 1))

    @property
    def complete(self) -> bool:
        """Exact-set equality, and only when the requirement is knowable."""
        return (
            self.enforceable
            and not self.missing
            and not self.unexpected
            and not self.duplicated
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROTOCOL_COMPLETENESS_SCHEMA,
            "kind": self.kind,
            "blueprint_id": self.blueprint_id,
            "required": [list(item) for item in self.required],
            "executed": [list(item) for item in self.executed],
            "enforceable": self.enforceable,
            "missing": [list(item) for item in self.missing],
            "unexpected": [list(item) for item in self.unexpected],
            "duplicated": [list(item) for item in self.duplicated],
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolCompleteness":
        require_schema(payload, PROTOCOL_COMPLETENESS_SCHEMA)
        return cls(
            payload["kind"],
            payload["blueprint_id"],
            tuple(tuple(item) for item in payload.get("required", ())),
            tuple(tuple(item) for item in payload.get("executed", ())),
            bool(payload.get("enforceable", False)),
        )


class UQCellState(str, Enum):
    """What is known about one quantity on one uncertainty channel."""

    #: A quantified result exists for this cell.
    QUANTIFIED = "quantified"
    #: A producer ran and reported the channel as not determinable. Honest, and
    #: never converted to zero.
    UNKNOWN = "unknown"
    #: Required by the pack, and nothing was produced at all.
    MISSING = "missing"
    #: Produced where the pack requires nothing. Recorded, not counted.
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, order=True)
class UQCoverageCell:
    quantity: str
    channel: UncertaintyChannel
    state: UQCellState
    method_id: str = ""

    def __post_init__(self) -> None:
        quantity = str(self.quantity).strip()
        if not quantity:
            raise InvalidScientificProblem("uq coverage cell requires a quantity")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "channel", UncertaintyChannel(self.channel))
        object.__setattr__(self, "state", UQCellState(self.state))
        object.__setattr__(self, "method_id", str(self.method_id).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UQ_CELL_SCHEMA,
            "quantity": self.quantity,
            "channel": self.channel.value,
            "state": self.state.value,
            "method_id": self.method_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UQCoverageCell":
        require_schema(payload, UQ_CELL_SCHEMA)
        return cls(
            payload["quantity"],
            UncertaintyChannel(payload["channel"]),
            UQCellState(payload["state"]),
            payload.get("method_id", ""),
        )


@dataclass(frozen=True)
class UQCoverage:
    """Quantity x uncertainty-channel, every required cell present.

    The matrix is over the *required* cells, so a channel nobody produced shows
    as ``MISSING`` rather than being absent from the report. An absent row and
    an uncovered row read identically to a human skimming, and only one of them
    is a defect.
    """

    blueprint_id: str
    cells: tuple[UQCoverageCell, ...]
    enforceable: bool

    def __post_init__(self) -> None:
        blueprint = str(self.blueprint_id).strip()
        if not blueprint:
            raise InvalidScientificProblem("uq coverage requires blueprint_id")
        object.__setattr__(self, "blueprint_id", blueprint)
        cells = tuple(sorted(self.cells))
        if any(not isinstance(item, UQCoverageCell) for item in cells):
            raise InvalidScientificProblem("uq coverage requires UQCoverageCell records")
        keys = [(item.quantity, item.channel) for item in cells]
        if len(keys) != len(set(keys)):
            raise InvalidScientificProblem("uq coverage repeats a quantity/channel cell")
        object.__setattr__(self, "cells", cells)
        if not isinstance(self.enforceable, bool):
            raise InvalidScientificProblem("enforceable must be a boolean")

    def with_state(self, state: UQCellState) -> tuple[UQCoverageCell, ...]:
        wanted = UQCellState(state)
        return tuple(item for item in self.cells if item.state is wanted)

    @property
    def missing(self) -> tuple[UQCoverageCell, ...]:
        return self.with_state(UQCellState.MISSING)

    @property
    def unknown(self) -> tuple[UQCoverageCell, ...]:
        return self.with_state(UQCellState.UNKNOWN)

    @property
    def complete(self) -> bool:
        """Every required cell quantified. UNKNOWN is not coverage."""
        required = [
            item for item in self.cells if item.state is not UQCellState.NOT_APPLICABLE
        ]
        return (
            self.enforceable
            and bool(required)
            and all(item.state is UQCellState.QUANTIFIED for item in required)
        )

    def counts(self) -> dict[str, int]:
        result = {state.value: 0 for state in UQCellState}
        for item in self.cells:
            result[item.state.value] += 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UQ_COVERAGE_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "cells": [item.to_dict() for item in self.cells],
            "enforceable": self.enforceable,
            "counts": self.counts(),
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UQCoverage":
        require_schema(payload, UQ_COVERAGE_SCHEMA)
        return cls(
            payload["blueprint_id"],
            tuple(UQCoverageCell.from_dict(i) for i in payload.get("cells", ())),
            bool(payload.get("enforceable", False)),
        )


def assess_protocol_completeness(
    snapshot: CompositionPackSnapshot,
    blueprint_id: str,
    kind: str,
    executed: tuple[tuple[str, str], ...],
) -> ProtocolCompleteness:
    """Compare the snapshot's required protocol set against what ran."""
    if not isinstance(snapshot, CompositionPackSnapshot):
        raise TypeError("protocol completeness requires a CompositionPackSnapshot")
    required = snapshot.required_protocols(blueprint_id, kind)
    return ProtocolCompleteness(
        kind=kind,
        blueprint_id=blueprint_id,
        required=tuple(required),
        executed=tuple(executed),
        enforceable=snapshot.declares_requirements,
    )


def assess_uq_coverage(
    snapshot: CompositionPackSnapshot,
    blueprint_id: str,
    produced: Mapping[tuple[str, str], tuple[Uncertainty, str]],
) -> UQCoverage:
    """Build the quantity x channel matrix for one blueprint.

    ``produced`` maps ``(quantity, channel)`` to the uncertainty that was
    emitted and the method that emitted it. An emitted-but-unquantified record
    lands in ``UNKNOWN``, which is a different statement from ``MISSING`` and
    from a value of zero. None of the three is convertible into another.
    """
    if not isinstance(snapshot, CompositionPackSnapshot):
        raise TypeError("uq coverage requires a CompositionPackSnapshot")
    required = snapshot.required_uncertainty_cells(blueprint_id)
    cells: list[UQCoverageCell] = []
    for quantity, channel in sorted(required):
        found = produced.get((quantity, channel))
        if found is None:
            cells.append(
                UQCoverageCell(quantity, UncertaintyChannel(channel), UQCellState.MISSING)
            )
            continue
        uncertainty, method = found
        state = (
            UQCellState.QUANTIFIED
            if isinstance(uncertainty, Uncertainty) and uncertainty.is_quantified
            else UQCellState.UNKNOWN
        )
        cells.append(
            UQCoverageCell(quantity, UncertaintyChannel(channel), state, method)
        )
    for (quantity, channel), (uncertainty, method) in sorted(produced.items()):
        if (quantity, channel) in required:
            continue
        cells.append(
            UQCoverageCell(
                quantity,
                UncertaintyChannel(channel),
                UQCellState.NOT_APPLICABLE,
                method,
            )
        )
    return UQCoverage(
        blueprint_id=blueprint_id,
        cells=tuple(cells),
        enforceable=bool(snapshot.uncertainty_requirements),
    )


def evidence_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "PROTOCOL_COMPLETENESS_SCHEMA",
    "UQ_CELL_SCHEMA",
    "UQ_COVERAGE_SCHEMA",
    "ProtocolCompleteness",
    "UQCellState",
    "UQCoverage",
    "UQCoverageCell",
    "assess_protocol_completeness",
    "assess_uq_coverage",
    "evidence_digest",
]
