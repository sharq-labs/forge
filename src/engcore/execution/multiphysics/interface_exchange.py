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

:class:`InterfaceContract` declares, per graph edge, which quantity it
carries, and :meth:`InterfaceContract.check` refuses a graph whose edges do
not honour it (a flux edge without a conservative mapping, without a sign
convention, on an offset scale, or not field-valued; a two-way interface
without exactly one flux edge one way and one intensive edge back).
:func:`interface_flux_balance` reads, per window, the conservation residual
the conservative transfer recorded on every flux edge -- a DIAGNOSTIC of the
transfer (Phase 1 BR3), never a bound, and UNKNOWN where nothing recorded one.

A-4 requires an executable typed InterfaceTransfer on every flux edge, including
integrated flux. Legacy prose normals alone refuse. The mapper executes orientation
and normal sign; transfer-integral diagnostics never establish independent coupled
physical conservation. Neutral Dirichlet-Neumann admission takes explicit meanings.

Nothing here names a physics: the contract is about how a quantity crosses,
which is the same for heat and for momentum.  It does not make any coupled
result correct, and a satisfied contract is not validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import MultiphysicsRunRecord, PhysicsGraph, PortKind
from ...scientific.fields.interface_transfer import InterfaceRepresentation
from ...scientific.fields.semantics import FieldKind
from ...scientific.semantics import QuantitySemantics
from ...scientific.multiphysics import CouplingScheme


class ExchangeKind(str, Enum):
    FLUX_DENSITY = "flux_density"
    INTENSIVE = "intensive"
    INTEGRATED_FLUX = "integrated_flux"


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
        if self.kind is not ExchangeKind.INTENSIVE and not self.sign_convention:
            raise InvalidScientificProblem(
                f"flux edge {self.edge_id!r} declares no sign convention; a flux without the normal it refers to "
                f"can arrive with either sign"
            )
        if self.kind is ExchangeKind.INTENSIVE and self.sign_convention:
            raise InvalidScientificProblem(f"intensive edge {self.edge_id!r} has no sign convention to declare")

    def to_dict(self) -> dict[str, Any]:
        return {"edge_id": self.edge_id, "kind": self.kind.value, "sign_convention": self.sign_convention}


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
            if exchange.kind is not ExchangeKind.INTENSIVE:
                if port.kind is not PortKind.FIELD:
                    problems.append(f"flux edge {edge.edge_id!r} is not field-valued; an interface flux is a field")
                    continue
                transfer = edge.interface_transfer
                if transfer is None or exchange.sign_convention != "edge_interface_transfer":
                    problems.append("legacy prose normal cannot authorize interface execution; explicit typed migration required")
                    continue
                expected = InterfaceRepresentation.NORMAL_DENSITY if exchange.kind is ExchangeKind.FLUX_DENSITY else InterfaceRepresentation.INTEGRATED
                if transfer.representation is not expected:
                    problems.append("interface exchange representation differs from executed transfer")
                target = graph.participant(edge.target.participant_id).port(edge.target.port_id)
                try:
                    transfer.admit(port.field, graph.support(port.field.mesh_id), target.field,
                                   graph.support(target.field.mesh_id), edge.mapping)
                except InvalidScientificProblem as exc:
                    problems.append(str(exc))
            else:
                target = graph.participant(edge.target.participant_id).port(edge.target.port_id)
                if (port.kind is not PortKind.FIELD or target.kind is not PortKind.FIELD
                        or port.field.semantics is None or target.field.semantics is None
                        or port.field.semantics.kind is not FieldKind.INTENSIVE
                        or target.field.semantics.kind is not FieldKind.INTENSIVE):
                    problems.append("intensive interface exchange requires declared intensive field semantics")
        if self.two_way:
            flux = [e for e in self.exchanges if e.kind is not ExchangeKind.INTENSIVE]
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
    flux_edges = {e.edge_id for e in contract.exchanges if e.kind is not ExchangeKind.INTENSIVE}
    entries: list[dict[str, Any]] = []
    for window in run.windows:
        recorded = {item.get("edge_id"): item.get("mapping") or {} for item in window.iterations[-1].mapping_diagnostics}
        for edge_id in sorted(flux_edges):
            mapping = recorded.get(edge_id)
            provenance = (mapping or {}).get("provenance") or {}
            if provenance.get("method") == "executed_common_plane_interface_overlap":
                entries.append({"window_index": window.index, "edge_id": edge_id, "status": "transfer_integral_diagnostic",
                                "local_mapping_relative_residual": provenance.get("local_mapping_relative_residual"),
                                "oriented_integral_absolute_residual": provenance.get("oriented_integral_absolute_residual"),
                                "unit": provenance.get("conservation_unit"),
                                "coupled_physical_conservation": "unknown",
                                "numerical_solution_verification": "not established", "experimental_validation": "not established",
                                "notice": "constructed interface transfer; independent solver balance is not established"})
                continue
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


__all__ = ["ExchangeKind", "InterfaceContract", "InterfaceExchange", "interface_flux_balance",
           "DirichletNeumannAdmission", "admit_dirichlet_neumann_interface"]


@dataclass(frozen=True)
class DirichletNeumannAdmission:
    interface_id: str
    graph_fingerprint: str
    intensive_receiver: str
    flux_receiver: str
    receiver_flux_sign: int
    implicit: bool
    intensive_quantity: QuantitySemantics
    flux_quantity: QuantitySemantics

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "dirichlet_neumann_admission/1", "classification": "interface_condition_admission_not_validation",
                "interface_id": self.interface_id, "graph_fingerprint": self.graph_fingerprint,
                "intensive_receiver": self.intensive_receiver, "flux_receiver": self.flux_receiver,
                "executed_flux_sign": self.receiver_flux_sign, "implicit": self.implicit,
                "intensive_quantity": self.intensive_quantity.to_dict(), "flux_quantity": self.flux_quantity.to_dict(),
                "coupled_physical_conservation": "unknown", "numerical_solution_verification": "not established",
                "experimental_validation": "not established"}


def admit_dirichlet_neumann_interface(interface_id, intensive_edge, flux_edge, intensive_quantity,
                                      flux_quantity, graph, plan) -> DirichletNeumannAdmission:
    """Generic declared interface admission; never a physical conservation verdict."""
    if not isinstance(intensive_quantity, QuantitySemantics) or not isinstance(flux_quantity, QuantitySemantics):
        raise InvalidScientificProblem("interface admission requires explicit domain-owned quantity meanings")
    intensive, flux = graph.edge(intensive_edge), graph.edge(flux_edge)
    if flux.interface_transfer is None:
        raise InvalidScientificProblem("interface flux requires executable typed transfer")
    representation = flux.interface_transfer.representation
    kind = ExchangeKind.FLUX_DENSITY if representation is InterfaceRepresentation.NORMAL_DENSITY else ExchangeKind.INTEGRATED_FLUX
    contract = InterfaceContract(interface_id, (InterfaceExchange(intensive_edge, ExchangeKind.INTENSIVE),
                                               InterfaceExchange(flux_edge, kind, "edge_interface_transfer")))
    contract.check(graph)
    for edge, expected in ((intensive, intensive_quantity), (flux, flux_quantity)):
        for endpoint in (edge.source, edge.target):
            port = graph.participant(endpoint.participant_id).port(endpoint.port_id)
            if port.semantics != expected:
                raise InvalidScientificProblem("declared interface physical meaning differs from connected port")
    plan.validate_against(graph)
    implicit = plan.scheme is CouplingScheme.IMPLICIT
    if implicit and not {intensive_edge, flux_edge}.issubset({c.edge_id for c in plan.criteria}):
        raise InvalidScientificProblem("implicit interface must measure both intensive and flux edges")
    return DirichletNeumannAdmission(interface_id, graph.fingerprint(), intensive.target.participant_id,
                                     flux.target.participant_id, flux.interface_transfer.sign, implicit,
                                     intensive_quantity, flux_quantity)
