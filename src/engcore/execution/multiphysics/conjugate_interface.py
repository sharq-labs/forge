"""Thermal instance of physics-neutral typed Dirichlet-Neumann admission.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. OD-6 permits E2 build work; this module
implements no FE/CFD solver or provider adapter and grants no provider-pair stage.

The caller declares exact domain-owned temperature and heat-flux meanings. Shared
admission and execution live in interface_exchange and InterfaceTransfer. CHT adds
its thermal dimensions and an equal-and-opposite outward normal relation. Execution
applies the derived sign, so receivers consume the mapped record without another
sign multiplication. Legacy prose-only or pre-signed target conventions require
explicit migration and cannot authorize execution.

Temperature continuity and heat-flux balance are domain conditions to be solved,
not established by admission, a mapping residual or an iterative tolerance. The
constructed transferred integral is not an independent target-solver flux. Solver
verification, experimental validation, interface-law applicability and provider
maturity require separately admitted evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CouplingPlan, PhysicsGraph
from ...scientific.units.quantity import dimensionality
from .interface_exchange import DirichletNeumannAdmission, admit_dirichlet_neumann_interface
from ...scientific.semantics import QuantitySemantics
from ...scientific.fields.interface_transfer import InterfaceRelation, InterfaceRepresentation

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
    execution: DirichletNeumannAdmission | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "classification": "interface_condition_admission_not_validation",
            "interface": self.interface.to_dict(),
            "conditions": {
                "temperature_continuity": (f"T_solid = T_fluid on the interface: carried by {self.interface.temperature_edge!r} "
                                           f"(Dirichlet datum of {self.dirichlet_receiver!r}), consistent mapping"),
                "heat_flux_balance": (f"q_solid.n_solid + q_fluid.n_fluid = 0: carried by {self.interface.heat_flux_edge!r} "
                                      f"(Neumann datum of {self.neumann_receiver!r}), conservative mapping, "
                                      f"transfer already applies sign {self.receiver_flux_sign}; receiver consumes transferred value"),
            },
            "satisfied_to": "not established by admission; iterative or splitting diagnostics are not physical interface verification",
            "does_not_establish": ["either solver's correctness", "stability of the Dirichlet-Neumann partition",
                                   "accuracy of the coupled solution", "validation"],
        }
        if self.execution is not None:
            payload["schema"] = "conjugate_interface_admission/2"
            payload["execution"] = self.execution.to_dict()
        return payload


def admit_conjugate_interface(
    interface: ConjugateHeatTransferInterface, graph: PhysicsGraph, plan: CouplingPlan,
    *, temperature_semantics: QuantitySemantics | None = None,
    heat_flux_semantics: QuantitySemantics | None = None,
) -> ConjugateInterfaceAdmission:
    """Thermal instance of neutral admission, requiring explicit domain meanings.

    Legacy prose normals alone refuse. The transfer applies the sign; receivers
    consume the transferred value without applying that sign a second time.
    """
    if not isinstance(temperature_semantics, QuantitySemantics) or not isinstance(heat_flux_semantics, QuantitySemantics):
        raise InvalidScientificProblem("CHT requires explicit thermal quantity semantics; legacy migration required")
    if dimensionality(temperature_semantics.unit) != _TEMPERATURE or dimensionality(heat_flux_semantics.unit) != _HEAT_FLUX:
        raise InvalidScientificProblem("CHT declared meanings require temperature and heat-flux dimensions")
    flux = graph.edge(interface.heat_flux_edge)
    intensive = graph.edge(interface.temperature_edge)
    for edge in (flux, intensive):
        if {edge.source.participant_id, edge.target.participant_id} != {interface.solid, interface.fluid}:
            raise InvalidScientificProblem("CHT edges must join declared solid and fluid participants")
    transfer = flux.interface_transfer
    if (transfer is None or transfer.relation is not InterfaceRelation.EQUAL_AND_OPPOSITE_OUTWARD
            or transfer.representation is not InterfaceRepresentation.NORMAL_DENSITY):
        raise InvalidScientificProblem("CHT requires executed equal-and-opposite outward flux-density transfer")
    if interface.flux_normal != _NORMAL + flux.source.participant_id:
        raise InvalidScientificProblem("legacy presigned CHT flux requires explicit source-normal migration")
    admission = admit_dirichlet_neumann_interface(interface.interface_id, interface.temperature_edge,
        interface.heat_flux_edge, temperature_semantics, heat_flux_semantics, graph, plan)
    return ConjugateInterfaceAdmission(interface, admission.intensive_receiver, admission.flux_receiver,
                                      admission.receiver_flux_sign, admission.implicit, admission)


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
        order = list(PairStage)
        for stage in EVIDENCE_STAGES:
            status = stages[stage]
            if status.reached:
                ref = status.evidence_ref.strip().lower()
                if len(ref) != 64 or set(ref) - set("0123456789abcdef"):
                    raise InvalidScientificProblem(f"{stage.value} needs the sha256 of the recorded run that shows it")
                # review M3: EVERY earlier stage, so validation can never be claimed without execution and verification
                missing = [s.value for s in order[:order.index(stage)] if not stages[s].reached]
                if missing:
                    raise InvalidScientificProblem(f"{stage.value} cannot be reached before {missing}")
        object.__setattr__(self, "stages", stages)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "provider_pair_maturity", "pair": self.pair, "policy": self.policy,
                "stages": {s.value: {"reached": v.reached, "basis": v.basis, "evidence_ref": v.evidence_ref or None}
                           for s, v in self.stages.items()},
                # an evidence reference is a stated digest; nothing here looks it up
                "evidence_ref_status": "asserted_not_resolved"}


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
