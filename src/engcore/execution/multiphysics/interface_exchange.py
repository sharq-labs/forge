"""What crosses a coupled interface, and with what conservation semantics (Phase 2 BR12).

Coupling two field solvers at a shared boundary (a finite-element body and a
fluid domain, say) exchanges two kinds of quantity, and they must not be
transferred alike:

* a **flux density** (heat flux in W/m**2, traction in Pa): its INTEGRAL over
  the interface is what one side gives the other.  Across two different
  interface meshes it must be transferred conservatively, so the total is not
  created or lost by the transfer; it needs a declared sign convention (which
  side's outward normal), and an offset-scale unit is meaningless for it;
* an **intensive** state (temperature, displacement): its VALUE is matched,
  by a consistent interpolation.  It is not conserved and is never described
  as conserved.

:class:`InterfaceContract` declares, per graph edge, which of the two it
carries, and :meth:`InterfaceContract.check` refuses a graph whose edges do
not honour it (a flux edge without a conservative mapping, without a sign
convention, on an offset scale, or not field-valued; a two-way interface
without exactly one flux edge one way and one intensive edge back).
:func:`interface_flux_balance` reads, per window, the conservation residual
the conservative transfer recorded on every flux edge -- a DIAGNOSTIC of the
transfer (Phase 1 BR3), never a bound, and UNKNOWN where nothing recorded one.

Nothing here names a physics: the contract is about how a quantity crosses,
which is the same for heat and for momentum.  It does not make any coupled
result correct, and a satisfied contract is not validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import FieldMappingMethod, MultiphysicsRunRecord, PhysicsGraph, PortKind
from ...scientific.units.quantity import is_ratio_scale


class ExchangeKind(str, Enum):
    FLUX_DENSITY = "flux_density"
    INTENSIVE = "intensive"


@dataclass(frozen=True)
class InterfaceExchange:
    edge_id: str
    kind: ExchangeKind
    #: for a flux: whose outward normal the sign refers to (required); empty for an intensive quantity
    sign_convention: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ExchangeKind(self.kind))
        object.__setattr__(self, "edge_id", str(self.edge_id).strip())
        object.__setattr__(self, "sign_convention", str(self.sign_convention).strip())
        if not self.edge_id:
            raise InvalidScientificProblem("an interface exchange names its edge")
        if self.kind is ExchangeKind.FLUX_DENSITY and not self.sign_convention:
            raise InvalidScientificProblem(
                f"flux edge {self.edge_id!r} declares no sign convention; a flux without the normal it refers to "
                f"can arrive with either sign"
            )
        if self.kind is ExchangeKind.INTENSIVE and self.sign_convention:
            raise InvalidScientificProblem(f"intensive edge {self.edge_id!r} has no sign convention to declare")

    def to_dict(self) -> dict[str, Any]:
        return {"edge_id": self.edge_id, "kind": self.kind.value, "sign_convention": self.sign_convention}


#: mapping methods that transfer a flux density's integral (identity: one support, nothing to lose)
_CONSERVING = frozenset({FieldMappingMethod.CONSERVATIVE_CELL, FieldMappingMethod.IDENTITY})


@dataclass(frozen=True)
class InterfaceContract:
    interface_id: str
    exchanges: tuple[InterfaceExchange, ...]
    #: True: a two-way interface (one flux edge one way, one intensive edge back)
    two_way: bool = True

    def __post_init__(self) -> None:
        if not str(self.interface_id).strip():
            raise InvalidScientificProblem("an interface contract has an id")
        items = tuple(self.exchanges)
        if not items or any(not isinstance(item, InterfaceExchange) for item in items):
            raise InvalidScientificProblem("an interface contract declares InterfaceExchange records")
        if len({item.edge_id for item in items}) != len(items):
            raise InvalidScientificProblem("one exchange declaration per edge")
        object.__setattr__(self, "exchanges", tuple(sorted(items, key=lambda item: item.edge_id)))

    def problems(self, graph: PhysicsGraph) -> list[str]:
        """Why ``graph`` does not honour this contract (empty when it does)."""
        problems: list[str] = []
        participants: dict[str, tuple[str, str]] = {}
        for exchange in self.exchanges:
            try:
                edge = graph.edge(exchange.edge_id)
            except InvalidScientificProblem as exc:
                problems.append(str(exc))
                continue
            port = graph.participant(edge.source.participant_id).port(edge.source.port_id)
            participants[exchange.edge_id] = (edge.source.participant_id, edge.target.participant_id)
            if exchange.kind is ExchangeKind.FLUX_DENSITY:
                if port.kind is not PortKind.FIELD:
                    problems.append(f"flux edge {edge.edge_id!r} is not field-valued; an interface flux is a field")
                    continue
                method = None if edge.mapping is None else edge.mapping.method
                if method not in _CONSERVING:
                    problems.append(
                        f"flux edge {edge.edge_id!r} is mapped by {getattr(method, 'value', method)!r}; a flux density "
                        f"crosses an interface conservatively (conservative_cell, or identity on one support)"
                    )
                if not is_ratio_scale(port.unit):
                    problems.append(f"flux edge {edge.edge_id!r} uses offset-scale unit {port.unit!r}")
        if self.two_way:
            flux = [e for e in self.exchanges if e.kind is ExchangeKind.FLUX_DENSITY]
            intensive = [e for e in self.exchanges if e.kind is ExchangeKind.INTENSIVE]
            if len(flux) != 1 or len(intensive) != 1:
                problems.append("a two-way interface exchanges exactly one flux density and one intensive quantity")
            elif flux[0].edge_id in participants and intensive[0].edge_id in participants:
                there, back = participants[flux[0].edge_id], participants[intensive[0].edge_id]
                if back != (there[1], there[0]):
                    problems.append("the intensive quantity must flow back between the same two participants")
        return problems

    def check(self, graph: PhysicsGraph) -> None:
        found = self.problems(graph)
        if found:
            raise InvalidScientificProblem(f"interface {self.interface_id!r} is not honoured: " + "; ".join(found))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "interface_contract", "interface_id": self.interface_id, "two_way": self.two_way,
                "exchanges": [e.to_dict() for e in self.exchanges],
                "notice": "how quantities cross the interface; a honoured contract is not validation"}


def interface_flux_balance(run: MultiphysicsRunRecord, contract: InterfaceContract) -> tuple[Mapping[str, Any], ...]:
    """Per window and flux edge: the conservation residual its transfer recorded -- a diagnostic, or UNKNOWN."""
    if not isinstance(run, MultiphysicsRunRecord):
        raise InvalidScientificProblem("interface_flux_balance reads a MultiphysicsRunRecord")
    contract.check(run.graph)
    flux_edges = {e.edge_id for e in contract.exchanges if e.kind is ExchangeKind.FLUX_DENSITY}
    entries: list[dict[str, Any]] = []
    for window in run.windows:
        recorded = {item.get("edge_id"): item.get("mapping") or {} for item in window.iterations[-1].mapping_diagnostics}
        for edge_id in sorted(flux_edges):
            mapping = recorded.get(edge_id)
            provenance = (mapping or {}).get("provenance") or {}
            residual = provenance.get("conservation_absolute_residual")
            scale = provenance.get("conservation_scale_l1")
            if mapping is None or residual is None:
                entries.append({"window_index": window.index, "edge_id": edge_id, "status": "unknown",
                                "reason": "no conservative transfer recorded a residual for this edge"})
                continue
            entries.append({"window_index": window.index, "edge_id": edge_id, "status": "diagnostic",
                            "absolute_residual": list(residual), "scale_l1": list(scale or ()),
                            "relative": mapping.get("conservation_relative_error"),
                            "unit": provenance.get("conservation_unit"),
                            "notice": "the integral imbalance of the transfer; not a bound on the coupled solution"})
    return tuple(entries)


__all__ = ["ExchangeKind", "InterfaceContract", "InterfaceExchange", "interface_flux_balance"]
