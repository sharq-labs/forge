"""Built-in execution adapters for thermal -> material resistance composition."""

from __future__ import annotations

from ..compositionpacks.builtin_thermal_resistance import (
    ADAPTER_VERSION,
    MANIFEST as COMPOSITION_MANIFEST,
    MATERIAL_ADAPTER_ID,
    MATERIAL_PARTICIPANT,
    THERMAL_ADAPTER_ID,
    THERMAL_PARTICIPANT,
)
from ..domainpacks.frozen import implementation_fingerprint
from ..domains.electrical import material
from ..domains.thermal_models import lumped
from ..execution.multiphysics import (
    AdvanceResult,
    CallbackParticipant,
    InitializationResult,
    ParticipantFactoryDeclaration,
)
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from .manifest import (
    EXECUTION_PACK_API,
    CompositionDependency,
    ExecutionPackManifest,
    ParticipantFactoryRef,
)

PACK_ID = "system.thermal_resistance.execution"
PACK_VERSION = "1"


def _unknown(label: str) -> Uncertainty:
    return Uncertainty.unknown(
        f"{label}: no quantified uncertainty producer is declared by this "
        "ExecutionPack"
    )


def _window_duration(start: Quantity, end: Quantity) -> Quantity:
    seconds = end.magnitude_in("second") - start.magnitude_in("second")
    if seconds <= 0.0:
        raise InvalidScientificProblem(
            "participant advance window must have positive duration"
        )
    return Quantity(seconds, "second")


def build_thermal_participant(spec):
    if spec.participant_id != THERMAL_PARTICIPANT:
        raise InvalidScientificProblem(
            f"thermal adapter received participant {spec.participant_id!r}"
        )

    state = {"temperature": None}

    def initialize(instant, external_inputs, external_uncertainty):
        initial = external_inputs["initial_temperature"]
        state["temperature"] = initial
        return InitializationResult(
            outputs={"temperature": initial},
            uncertainty={"temperature": _unknown("thermal temperature")},
            diagnostics={
                "basis": (
                    "initial output is the declared body initial temperature"
                )
            },
        )

    def advance(request):
        current = state["temperature"]
        if current is None:
            raise InvalidScientificProblem(
                "thermal participant advanced before initialization"
            )
        duration = _window_duration(request.start, request.end)
        body = lumped.ThermalBody(
            body_id=spec.participant_id,
            heat_capacity=request.inputs["heat_capacity"],
            ambient_conductance=request.inputs["ambient_conductance"],
            ambient_temperature=request.inputs["ambient_temperature"],
            initial_temperature=current,
            duration=duration,
        )
        problem_id = (
            f"{spec.participant_id}-"
            f"{request.start.magnitude_in('second'):.17g}-"
            f"{request.end.magnitude_in('second'):.17g}"
        )
        problem = lumped.build_lumped_thermal_problem(
            body,
            problem_id=problem_id,
        )
        solver = lumped.LumpedThermalSolver()
        solver.bind_body(
            body,
            problem.problem_id,
            heat_input=request.inputs["heat_input"],
        )
        prepared = solver.prepare(
            problem,
            realization=lumped.LUMPED_CLOSED_FORM_REALIZATION,
        )
        raw = solver.solve(prepared)
        if not raw.succeeded:
            raise InvalidScientificProblem(
                "lumped thermal solver did not produce a usable state"
            )
        metrics = solver.extract_metrics(prepared, raw)
        temperature = metrics[lumped.TEMPERATURE_METRIC]
        state["temperature"] = temperature
        validation = solver.validate(prepared, raw)
        return AdvanceResult(
            end=request.end,
            outputs={"temperature": temperature},
            uncertainty={"temperature": _unknown("thermal temperature")},
            substeps=1,
            internal_converged=True,
            max_internal_step=duration,
            diagnostics={
                "solver": solver.identity.to_dict(),
                "realization": (
                    f"{lumped.LUMPED_CLOSED_FORM_REALIZATION.realization_id}@"
                    f"{lumped.LUMPED_CLOSED_FORM_REALIZATION.version}"
                ),
                "validation": validation.to_dict(),
                "heat_input": request.inputs["heat_input"].to_dict(),
                "initial_temperature": current.to_dict(),
                "final_temperature": temperature.to_dict(),
            },
        )

    return CallbackParticipant(
        spec,
        initialize=initialize,
        advance=advance,
    )


def build_material_participant(spec):
    if spec.participant_id != MATERIAL_PARTICIPANT:
        raise InvalidScientificProblem(
            f"material adapter received participant {spec.participant_id!r}"
        )

    def initialize(instant, external_inputs, external_uncertainty):
        # This output is not a source of any graph edge. It is the exact
        # linear-TCR value at the declared reference temperature, R_ref, and
        # exists only because the generic participant contract requires every
        # output at initialization.
        resistance = external_inputs["reference_resistance"]
        return InitializationResult(
            outputs={"resistance": resistance},
            uncertainty={"resistance": _unknown("material resistance")},
            diagnostics={
                "basis": (
                    "initial seed equals R_ref at T_ref and is not consumed "
                    "by any coupling edge"
                )
            },
        )

    def advance(request):
        conductor = material.TemperatureDependentConductor(
            component_id=spec.participant_id,
            reference_resistance=request.inputs["reference_resistance"],
            temperature_coefficient=request.inputs[
                "temperature_coefficient"
            ],
            reference_temperature=request.inputs[
                "reference_temperature"
            ],
        )
        problem_id = (
            f"{spec.participant_id}-"
            f"{request.start.magnitude_in('second'):.17g}-"
            f"{request.end.magnitude_in('second'):.17g}"
        )
        problem = material.build_resistance_problem(
            conductor,
            problem_id=problem_id,
        )
        solver = material.ResistancePropertySolver()
        solver.bind_conductor(
            conductor,
            problem.problem_id,
            temperature=request.inputs["temperature"],
        )
        prepared = solver.prepare(
            problem,
            realization=material.LINEAR_TCR_REALIZATION,
        )
        raw = solver.solve(prepared)
        if not raw.succeeded:
            raise InvalidScientificProblem(
                "linear-TCR solver did not produce a usable resistance"
            )
        metrics = solver.extract_metrics(prepared, raw)
        resistance = metrics[material.RESISTANCE_METRIC]
        validation = solver.validate(prepared, raw)
        return AdvanceResult(
            end=request.end,
            outputs={"resistance": resistance},
            uncertainty={"resistance": _unknown("material resistance")},
            substeps=1,
            internal_converged=True,
            max_internal_step=None,
            diagnostics={
                "solver": solver.identity.to_dict(),
                "realization": (
                    f"{material.LINEAR_TCR_REALIZATION.realization_id}@"
                    f"{material.LINEAR_TCR_REALIZATION.version}"
                ),
                "validation": validation.to_dict(),
                "operating_temperature": (
                    request.inputs["temperature"].to_dict()
                ),
                "reference_resistance": (
                    request.inputs["reference_resistance"].to_dict()
                ),
                "temperature_coefficient": (
                    request.inputs["temperature_coefficient"].to_dict()
                ),
                "reference_temperature": (
                    request.inputs["reference_temperature"].to_dict()
                ),
                "resistance": resistance.to_dict(),
            },
        )

    return CallbackParticipant(
        spec,
        initialize=initialize,
        advance=advance,
    )


THERMAL_FACTORY = ParticipantFactoryDeclaration(
    model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
    model_version=lumped.LUMPED_CAPACITY_MODEL.version,
    realization_id=lumped.LUMPED_CLOSED_FORM_REALIZATION.realization_id,
    realization_version=lumped.LUMPED_CLOSED_FORM_REALIZATION.version,
    solver_id=lumped.SOLVER_ID,
    solver_version=lumped.SOLVER_VERSION,
    adapter_id=THERMAL_ADAPTER_ID,
    adapter_version=ADAPTER_VERSION,
    factory=build_thermal_participant,
    description="Native lumped-thermal participant adapter.",
)

MATERIAL_FACTORY = ParticipantFactoryDeclaration(
    model_id=material.LINEAR_TCR_MODEL.model_id,
    model_version=material.LINEAR_TCR_MODEL.version,
    realization_id=material.LINEAR_TCR_REALIZATION.realization_id,
    realization_version=material.LINEAR_TCR_REALIZATION.version,
    solver_id=material.SOLVER_ID,
    solver_version=material.SOLVER_VERSION,
    adapter_id=MATERIAL_ADAPTER_ID,
    adapter_version=ADAPTER_VERSION,
    factory=build_material_participant,
    description="Native linear-TCR material participant adapter.",
)


def _factory_ref(
    declaration: ParticipantFactoryDeclaration,
) -> ParticipantFactoryRef:
    digest, _basis = implementation_fingerprint(declaration.factory)
    return ParticipantFactoryRef(
        model_id=declaration.model_id,
        model_version=declaration.model_version,
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
                _factory_ref(THERMAL_FACTORY),
                _factory_ref(MATERIAL_FACTORY),
            )
        )
    ),
)


class ThermalResistanceExecutionPack:
    manifest = MANIFEST

    def participant_factories(self):
        return (THERMAL_FACTORY, MATERIAL_FACTORY)


BUILTIN_THERMAL_RESISTANCE_EXECUTION = ThermalResistanceExecutionPack()

__all__ = [
    "BUILTIN_THERMAL_RESISTANCE_EXECUTION",
    "MANIFEST",
    "MATERIAL_FACTORY",
    "PACK_ID",
    "PACK_VERSION",
    "THERMAL_FACTORY",
    "ThermalResistanceExecutionPack",
    "build_material_participant",
    "build_thermal_participant",
]
