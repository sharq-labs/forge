"""Conjugate heat transfer at a solid/fluid interface: admission of the interface conditions (Phase 3.5 WS3).

STATUS: provider-neutral coupling infrastructure.  It implements no solver and
no provider adapter; a real FE <-> CFD conjugate heat-transfer coupling stays
BLOCKED by policy (OD-P2-1, see :data:`CHT_FENICSX_OPENFOAM`).

A conjugate interface Gamma between a solid S and a fluid F carries two
conditions, and each must be carried by the coupling graph in the right form:

* temperature continuity ``T_S = T_F`` on Gamma -- an INTENSIVE quantity: one
  side's interface temperature is the other side's Dirichlet datum, matched by
  a consistent mapping, never "conserved";
* heat-flux balance ``q_S . n_S + q_F . n_F = 0`` on Gamma -- a FLUX DENSITY
  (W/m**2): the other side's Neumann datum, transferred CONSERVATIVELY (its
  integral over Gamma is not created or lost by the mapping), with a declared
  normal: ``outward_normal_of:<participant>``.  Heat leaving the source along
  its outward normal enters the receiver, so a receiver reads
  ``q_in = +value`` under the source's normal and ``q_in = -value`` under its
  own; the admission records which.

:func:`admit_conjugate_interface` refuses a graph or plan that does not express
both (two field edges between the same two participants in opposite
directions, temperature and power-per-area dimensions, a conservative flux
mapping, a ratio-scale flux unit, an explicit normal; an implicit plan measures
both edges).  It reuses :class:`.interface_exchange.InterfaceContract` for the
flux/intensive semantics.

What an admitted interface does NOT establish: that either solver is correct,
that the Dirichlet-Neumann partition is stable (that depends on the solid and
fluid heat-transfer properties, not on the graph), that a converged coupling is
accurate, or validation.  An EXPLICIT plan satisfies the two conditions only up
to its splitting error, which nothing measures unless window error control is
declared.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CouplingPlan, CouplingScheme, PhysicsGraph, PortKind
from ...scientific.units.quantity import dimensionality
from .interface_exchange import ExchangeKind, InterfaceContract, InterfaceExchange

_TEMPERATURE = dimensionality("kelvin")
_HEAT_FLUX = dimensionality("watt/meter**2")
_NORMAL = "outward_normal_of:"


@dataclass(frozen=True)
class ConjugateHeatTransferInterface:
    interface_id: str
    solid: str
    fluid: str
    #: the edge carrying the interface temperature (Dirichlet datum of its target)
    temperature_edge: str
    #: the edge carrying the interface heat flux density (Neumann datum of its target)
    heat_flux_edge: str
    #: ``outward_normal_of:<participant id>`` -- the normal the transported flux value refers to
    flux_normal: str

    def __post_init__(self) -> None:
        for label in ("interface_id", "solid", "fluid", "temperature_edge", "heat_flux_edge", "flux_normal"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"a conjugate interface declares its {label}")
            object.__setattr__(self, label, value)
        if self.solid == self.fluid:
            raise InvalidScientificProblem("a conjugate interface joins two different participants")
        if self.temperature_edge == self.heat_flux_edge:
            raise InvalidScientificProblem("temperature and heat flux cross the interface on two different edges")
        owner = self.flux_normal.removeprefix(_NORMAL)
        if not self.flux_normal.startswith(_NORMAL) or owner not in (self.solid, self.fluid):
            raise InvalidScientificProblem(
                f"flux_normal must be '{_NORMAL}<solid or fluid participant>', got {self.flux_normal!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "conjugate_heat_transfer_interface", "interface_id": self.interface_id, "solid": self.solid,
                "fluid": self.fluid, "temperature_edge": self.temperature_edge, "heat_flux_edge": self.heat_flux_edge,
                "flux_normal": self.flux_normal}


@dataclass(frozen=True)
class ConjugateInterfaceAdmission:
    interface: ConjugateHeatTransferInterface
    dirichlet_receiver: str
    neumann_receiver: str
    receiver_flux_sign: int
    implicit: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": "interface_condition_admission_not_validation",
            "interface": self.interface.to_dict(),
            "conditions": {
                "temperature_continuity": (f"T_solid = T_fluid on the interface: carried by {self.interface.temperature_edge!r} "
                                           f"(Dirichlet datum of {self.dirichlet_receiver!r}), consistent mapping"),
                "heat_flux_balance": (f"q_solid.n_solid + q_fluid.n_fluid = 0: carried by {self.interface.heat_flux_edge!r} "
                                      f"(Neumann datum of {self.neumann_receiver!r}), conservative mapping, "
                                      f"receiver applies q_in = {'+' if self.receiver_flux_sign > 0 else '-'}value"),
            },
            "satisfied_to": ("the coupling tolerance of both edges (implicit plan)" if self.implicit else
                             "the splitting error of a staggered scheme (explicit plan); not measured unless window error "
                             "control is declared"),
            "does_not_establish": ["either solver's correctness", "stability of the Dirichlet-Neumann partition",
                                   "accuracy of the coupled solution", "validation"],
        }


def admit_conjugate_interface(
    interface: ConjugateHeatTransferInterface, graph: PhysicsGraph, plan: CouplingPlan,
) -> ConjugateInterfaceAdmission:
    """Admit the interface, or refuse naming every condition the graph or plan does not express."""
    problems: list[str] = []
    ids = {p.participant_id for p in graph.participants}
    for name in (interface.solid, interface.fluid):
        if name not in ids:
            problems.append(f"participant {name!r} is not in the graph")
    edges = {}
    for label, edge_id, dimension in (("temperature", interface.temperature_edge, _TEMPERATURE),
                                      ("heat flux", interface.heat_flux_edge, _HEAT_FLUX)):
        try:
            edge = graph.edge(edge_id)
        except InvalidScientificProblem as exc:
            problems.append(str(exc))
            continue
        edges[label] = edge
        port = graph.participant(edge.source.participant_id).port(edge.source.port_id)
        if {edge.source.participant_id, edge.target.participant_id} != {interface.solid, interface.fluid}:
            problems.append(f"the {label} edge {edge_id!r} does not join {interface.solid!r} and {interface.fluid!r}")
        if port.kind is not PortKind.FIELD:
            problems.append(f"the {label} edge {edge_id!r} is not field-valued; an interface {label} is a field on the interface")
        if dimensionality(port.unit) != dimension:
            problems.append(f"the {label} edge {edge_id!r} carries {port.unit!r}, not a {label} dimension")
    if len(edges) == 2:
        t, q = edges["temperature"], edges["heat flux"]
        if (t.source.participant_id, t.target.participant_id) != (q.target.participant_id, q.source.participant_id):
            problems.append("temperature and heat flux must cross the interface in opposite directions")
        contract = InterfaceContract(interface.interface_id, (
            InterfaceExchange(interface.temperature_edge, ExchangeKind.INTENSIVE),
            InterfaceExchange(interface.heat_flux_edge, ExchangeKind.FLUX_DENSITY, interface.flux_normal),
        ))
        problems += contract.problems(graph)
    implicit = plan.scheme is CouplingScheme.IMPLICIT
    if implicit:
        measured = {c.edge_id for c in plan.criteria}
        for edge_id in (interface.temperature_edge, interface.heat_flux_edge):
            if edge_id not in measured:
                problems.append(f"an implicit plan must measure the interface edge {edge_id!r}; it has no criterion")
    if problems:
        raise InvalidScientificProblem(f"conjugate interface {interface.interface_id!r} is not admitted: " + "; ".join(problems))
    q = edges["heat flux"]
    sign = +1 if interface.flux_normal == _NORMAL + q.source.participant_id else -1
    return ConjugateInterfaceAdmission(interface, edges["temperature"].target.participant_id, q.target.participant_id, sign, implicit)


# --------------------------------------------------------------------------------------------------------------------
# Provider-pair maturity (Phase 3.5 WS3): seven stages, the last three only with recorded evidence
# --------------------------------------------------------------------------------------------------------------------


class PairStage(str, Enum):
    ADAPTER_IMPLEMENTED = "adapter_implemented"
    FIELD_EXCHANGE_IMPLEMENTED = "field_exchange_implemented"
    COUPLING_ORCHESTRATION_IMPLEMENTED = "coupling_orchestration_implemented"
    REAL_SESSION_EXECUTABLE_IN_PRINCIPLE = "real_session_executable_in_principle"
    REAL_EXECUTION_DEMONSTRATED = "real_execution_demonstrated"
    NUMERICALLY_VERIFIED = "numerically_verified"
    SCIENTIFICALLY_VALIDATED = "scientifically_validated"


EVIDENCE_STAGES = (PairStage.REAL_EXECUTION_DEMONSTRATED, PairStage.NUMERICALLY_VERIFIED, PairStage.SCIENTIFICALLY_VALIDATED)


@dataclass(frozen=True)
class StageStatus:
    reached: bool
    basis: str
    #: the digest of the recorded run / report that shows it; required for an evidence stage
    evidence_ref: str = ""


@dataclass(frozen=True)
class ProviderPairMaturity:
    pair: str
    stages: Mapping[PairStage, StageStatus]
    policy: str

    def __post_init__(self) -> None:
        stages = {PairStage(k): v for k, v in dict(self.stages).items()}
        if set(stages) != set(PairStage):
            raise InvalidScientificProblem("a provider-pair maturity record states every stage")
        for stage in EVIDENCE_STAGES:
            status = stages[stage]
            if status.reached:
                ref = status.evidence_ref.strip().lower()
                if len(ref) != 64 or set(ref) - set("0123456789abcdef"):
                    raise InvalidScientificProblem(f"{stage.value} needs the sha256 of the recorded run that shows it")
                missing = [s.value for s in list(PairStage)[:4] if not stages[s].reached]
                if missing:
                    raise InvalidScientificProblem(f"{stage.value} cannot be reached before {missing}")
        object.__setattr__(self, "stages", stages)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "provider_pair_maturity", "pair": self.pair, "policy": self.policy,
                "stages": {s.value: {"reached": v.reached, "basis": v.basis, "evidence_ref": v.evidence_ref or None}
                           for s, v in self.stages.items()}}


#: the repository's actual state for the preferred CHT pair (2026-10-18).  Nothing here was executed.
CHT_FENICSX_OPENFOAM = ProviderPairMaturity(
    "fenicsx (solid thermal) <-> openfoam (fluid thermal), conjugate heat transfer",
    {
        PairStage.ADAPTER_IMPLEMENTED: StageStatus(False, (
            "FEniCSx: a coupling participant exists (coupling.adapters.provider_participant over forge_fenicsx). "
            "OpenFOAM: forge_openfoam runs one icoFoam cavity case to endTime; no coupling-participant adapter, no "
            "energy equation case")),
        PairStage.FIELD_EXCHANGE_IMPLEMENTED: StageStatus(False, (
            "no interface boundary-field read-back from OpenFOAM and no FEniCSx boundary-trace flux output; no shared "
            "interface support")),
        PairStage.COUPLING_ORCHESTRATION_IMPLEMENTED: StageStatus(False, (
            "provider-neutral pieces exist (MultiphysicsRuntime, FieldMapper conservative remap, InterfaceContract, "
            "this conjugate-interface admission, window control); nothing orchestrates THIS pair because neither "
            "side's session exists")),
        PairStage.REAL_SESSION_EXECUTABLE_IN_PRINCIPLE: StageStatus(False, "no time-window session for either side"),
        PairStage.REAL_EXECUTION_DEMONSTRATED: StageStatus(False, "never executed"),
        PairStage.NUMERICALLY_VERIFIED: StageStatus(False, "no evidence"),
        PairStage.SCIENTIFICALLY_VALIDATED: StageStatus(False, "no evidence"),
    },
    "BLOCKED: a real FE <-> CFD conjugate heat-transfer capability is a new capability foundation under the active "
    "epic (OD-P2-1; proposal P35-E2 in docs/work/PHASE_3_5_POLICY_PROPOSALS.md)",
)


__all__ = [
    "CHT_FENICSX_OPENFOAM",
    "ConjugateHeatTransferInterface",
    "ConjugateInterfaceAdmission",
    "EVIDENCE_STAGES",
    "PairStage",
    "ProviderPairMaturity",
    "StageStatus",
    "admit_conjugate_interface",
]
