"""Execution Pack for the closed-loop electrothermal feedback composition."""

from __future__ import annotations

from ..compositionpacks.builtin_electrothermal_feedback import (
    ADAPTER_VERSION,
    ELECTRICAL_ADAPTER_ID,
    ELECTRICAL_MODELS,
    ELECTRICAL_PARTICIPANT,
    MANIFEST as COMPOSITION_MANIFEST,
)
from ..domainpacks.frozen import implementation_fingerprint
from ..domains.electrical.dc.circuit import DCCircuit
from ..domains.electrical.dc.components import (
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from ..domains.electrical.dc.problem import build_dc_problem
from ..domains.electrical.dc.realizations import MNA_NETWORK_REALIZATION
from ..domains.electrical.dc.solver import (
    ElectricalDCSolver,
    SOLVER_ID,
    SOLVER_VERSION,
)
from ..execution.multiphysics import (
    AdvanceResult,
    CallbackParticipant,
    InitializationResult,
    ParticipantFactoryDeclaration,
)
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from .builtin_thermal_resistance import (
    MATERIAL_FACTORY,
    THERMAL_FACTORY,
)
from .manifest import (
    EXECUTION_PACK_API,
    CompositionDependency,
    ExecutionPackManifest,
    ParticipantFactoryRef,
)

PACK_ID = "system.electrothermal_feedback.execution"
PACK_VERSION = "1"


def _unknown(label: str) -> Uncertainty:
    return Uncertainty.unknown(
        f"{label}: participant-local uncertainty is not inferred; "
        "CompositionPack system UQ is evaluated after the coupled run"
    )


def build_electrical_participant(spec):
    if spec.participant_id != ELECTRICAL_PARTICIPANT:
        raise InvalidScientificProblem(
            f"DC adapter received participant {spec.participant_id!r}"
        )
    if spec.model_keys != tuple(
        sorted(item.key for item in ELECTRICAL_MODELS)
    ):
        raise InvalidScientificProblem(
            "DC participant model assembly disagrees with the "
            "electrothermal CompositionPack"
        )

    def initialize(instant, external_inputs, external_uncertainty):
        # The serial order is material -> electrical -> thermal. The zero seed
        # is therefore replaced by a real DC solve before thermal consumes the
        # electrical output in the first coupling window.
        return InitializationResult(
            outputs={"heat_generation": Quantity(0.0, "watt")},
            uncertainty={
                "heat_generation": _unknown(
                    "electrical heat generation"
                )
            },
            diagnostics={
                "basis": (
                    "zero initialization seed is not consumed before the "
                    "first electrical advance under the declared serial order"
                )
            },
        )

    def advance(request):
        resistance = request.inputs["resistance"]
        source_voltage = request.inputs["source_voltage"]
        circuit = DCCircuit(
            circuit_id=(
                f"{spec.participant_id}-"
                f"{request.start.magnitude_in('second'):.17g}-"
                f"{request.end.magnitude_in('second'):.17g}"
            ),
            nodes=(
                ElectricalNode("gnd", is_reference=True),
                ElectricalNode("n1"),
            ),
            resistors=(
                Resistor("R1", "n1", "gnd", resistance),
            ),
            voltage_sources=(
                DCVoltageSource(
                    "V1",
                    "n1",
                    "gnd",
                    source_voltage,
                ),
            ),
            description=(
                "One ideal voltage source drives one TCR-controlled resistor."
            ),
        )
        problem = build_dc_problem(
            circuit,
            problem_id=f"electrothermal:{circuit.circuit_id}",
        )
        solver = ElectricalDCSolver()
        solver.bind_circuit(circuit, problem.problem_id)
        prepared = solver.prepare(problem)
        raw = solver.solve(prepared)
        if not raw.succeeded:
            raise InvalidScientificProblem(
                "electrical DC participant failed to solve its network"
            )
        metrics = solver.extract_metrics(prepared, raw)
        heat_generation = metrics["resistor_power:R1"]
        validation = solver.validate(prepared, raw)
        return AdvanceResult(
            end=request.end,
            outputs={"heat_generation": heat_generation},
            uncertainty={
                "heat_generation": _unknown(
                    "electrical heat generation"
                )
            },
            substeps=1,
            internal_converged=True,
            max_internal_step=None,
            diagnostics={
                "solver": solver.identity.to_dict(),
                "realization": (
                    f"{MNA_NETWORK_REALIZATION.realization_id}@"
                    f"{MNA_NETWORK_REALIZATION.version}"
                ),
                "model_assembly": [
                    item.to_dict() for item in spec.models
                ],
                "validation": validation.to_dict(),
                "source_voltage": source_voltage.to_dict(),
                "resistance": resistance.to_dict(),
                "heat_generation": heat_generation.to_dict(),
                "circuit_fingerprint": circuit.fingerprint(),
            },
        )

    return CallbackParticipant(
        spec,
        initialize=initialize,
        advance=advance,
    )


ELECTRICAL_FACTORY = ParticipantFactoryDeclaration(
    model_id=ELECTRICAL_MODELS[0].model_id,
    model_version=ELECTRICAL_MODELS[0].model_version,
    models=ELECTRICAL_MODELS,
    realization_id=MNA_NETWORK_REALIZATION.realization_id,
    realization_version=MNA_NETWORK_REALIZATION.version,
    solver_id=SOLVER_ID,
    solver_version=SOLVER_VERSION,
    adapter_id=ELECTRICAL_ADAPTER_ID,
    adapter_version=ADAPTER_VERSION,
    factory=build_electrical_participant,
    description=(
        "Native MNA adapter for the exact KCL/resistor/ideal-voltage-source "
        "model assembly used by electrothermal feedback."
    ),
)


def _factory_ref(
    declaration: ParticipantFactoryDeclaration,
) -> ParticipantFactoryRef:
    digest, _basis = implementation_fingerprint(declaration.factory)
    return ParticipantFactoryRef(
        model_id=declaration.model_id,
        model_version=declaration.model_version,
        models=declaration.models,
        realization_id=declaration.realization_id,
        realization_version=declaration.realization_version,
        solver_id=declaration.solver_id,
        solver_version=declaration.solver_version,
        adapter_id=declaration.adapter_id,
        adapter_version=declaration.adapter_version,
        implementation_digest=digest,
    )


MANIFEST = ExecutionPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    compatible_core_apis=(EXECUTION_PACK_API,),
    composition=CompositionDependency(
        COMPOSITION_MANIFEST.pack_id,
        COMPOSITION_MANIFEST.pack_version,
        COMPOSITION_MANIFEST.digest,
    ),
    participant_factories=tuple(
        sorted(
            (
                _factory_ref(MATERIAL_FACTORY),
                _factory_ref(ELECTRICAL_FACTORY),
                _factory_ref(THERMAL_FACTORY),
            )
        )
    ),
)


class ElectrothermalFeedbackExecutionPack:
    manifest = MANIFEST

    def participant_factories(self):
        return (
            MATERIAL_FACTORY,
            ELECTRICAL_FACTORY,
            THERMAL_FACTORY,
        )


BUILTIN_ELECTROTHERMAL_FEEDBACK_EXECUTION = (
    ElectrothermalFeedbackExecutionPack()
)

__all__ = [
    "BUILTIN_ELECTROTHERMAL_FEEDBACK_EXECUTION",
    "ELECTRICAL_FACTORY",
    "ElectrothermalFeedbackExecutionPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
    "build_electrical_participant",
]
