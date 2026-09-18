"""CORE-7 -- structured repair: what would let a claim proceed, from declared requirements only.

When a claim cannot proceed, the answer a caller needs is *what to change*:
which input is missing and why, which validity condition cannot be assessed
and which declared input would unlock it, which capability identifier would
separate two candidates, which evidence no route here can produce.

A :class:`RepairAction` is that answer as a record. Every field is copied from
a declaration or a rule's own inputs -- the missing input's path, dimension and
description come from its :class:`~engcore.claims.capabilities.InputDeclaration`;
the conditions it unlocks come from the system's measured ``unlocks``; a bound a
value would have to move inside comes from the model's own ``RangeCondition``.
Nothing here writes advice. ``source`` names the declared record each action was
read from, so a reader can check it, and the explanation layer renders prose
*from* these records rather than beside them.

What a repair never contains
----------------------------
A number that was not declared or computed by a domain. A condition that was
never assessed has no bound it failed and no value to move; the repair says
what to *supply*, and the domain's exact inversion
(:mod:`engcore.domains.repair`) is the only source of "move X below Y" hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.immutable import freeze
from ..scientific.serialization import schema_string
from ._records import canonical_json, require_text
from .errors import ClaimLayerError

REPAIR_SCHEMA = schema_string("claim_repair_action")


class RepairKind(str, Enum):
    """The closed set of things a repair can ask for."""

    #: The claim is not a well-formed claim; restate the named field.
    RESTATE_CLAIM = "restate_claim"
    #: A required input of the selected capability is missing.
    SUPPLY_INPUT = "supply_input"
    #: An input that would make a validity condition assessable is missing.
    SUPPLY_VALIDITY_EVIDENCE = "supply_validity_evidence"
    #: A supplied input cannot be accepted as declared (dimension, scale, kind).
    CORRECT_INPUT = "correct_input"
    #: A supplied input is not accepted by the capability and would be dropped.
    REMOVE_UNACCEPTED_INPUT = "remove_unaccepted_input"
    #: The target names an input the claim did not supply.
    RESOLVE_TARGET = "resolve_target"
    #: Several capabilities qualify; a declared scientific capability separates them.
    NARROW_CAPABILITY = "narrow_capability"
    #: The quantity is reported per element; name the element.
    SELECT_INSTANCE = "select_instance"
    #: A supplied value lies outside a model's declared validity range.
    MOVE_INSIDE_VALIDITY = "move_inside_validity"
    #: The evidence the decision requires is not attainable on any declared route.
    PROVIDE_EVIDENCE = "provide_evidence"
    #: The uncertainty the decision requires is not quantified by this capability.
    PROVIDE_UNCERTAINTY = "provide_uncertainty"
    #: Model-form discrepancy must be supported and is not.
    SUPPORT_DISCREPANCY = "support_discrepancy"
    #: No registered capability can answer; a domain would have to declare one.
    EXTEND_CAPABILITY = "extend_capability"


@dataclass(frozen=True)
class RepairAction:
    """One structured repair. ``detail`` holds the declared facts it was built from."""

    kind: RepairKind
    target: str
    reason: str
    required_for: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    source: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RepairKind(self.kind))
        object.__setattr__(self, "target", require_text(self.target, field="repair.target", error=ClaimLayerError))
        object.__setattr__(self, "reason", require_text(self.reason, field="repair.reason", error=ClaimLayerError))
        object.__setattr__(self, "required_for", tuple(sorted(set(str(x) for x in self.required_for))))
        object.__setattr__(self, "alternatives", tuple(sorted(set(str(x) for x in self.alternatives))))
        object.__setattr__(self, "source", str(self.source))
        canonical_json(dict(self.detail))  # refuse what cannot be serialized
        object.__setattr__(self, "detail", freeze(dict(self.detail)))

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind.value, self.target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPAIR_SCHEMA,
            "kind": self.kind.value,
            "target": self.target,
            "reason": self.reason,
            "required_for": list(self.required_for),
            "alternatives": list(self.alternatives),
            "source": self.source,
            "detail": _plain(self.detail),
        }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def merge_repairs(repairs: "list[RepairAction] | tuple[RepairAction, ...]") -> tuple[RepairAction, ...]:
    """One action per (kind, target), their ``required_for`` united; deterministic order.

    Never combines two different asks into one: the same missing input needed by
    two conditions is one action needed for both, which is what a caller acts on.
    """
    merged: dict[tuple[str, str], RepairAction] = {}
    for repair in repairs:
        existing = merged.get(repair.key)
        if existing is None:
            merged[repair.key] = repair
            continue
        merged[repair.key] = RepairAction(
            kind=existing.kind,
            target=existing.target,
            reason=existing.reason,
            required_for=existing.required_for + repair.required_for,
            alternatives=existing.alternatives + repair.alternatives,
            source=existing.source,
            detail=existing.detail,
        )
    order = {kind: index for index, kind in enumerate(RepairKind)}
    return tuple(sorted(merged.values(), key=lambda r: (order[r.kind], r.target)))


__all__ = ["REPAIR_SCHEMA", "RepairAction", "RepairKind", "merge_repairs"]
