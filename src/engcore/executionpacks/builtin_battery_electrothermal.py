"""Execution Pack for the battery electrothermal composition.

Two native adapters. The cell adapter carries the two electrical states across
windows and drives the flagship kernel through its solver; the thermal adapter
is the lumped body with cumulative energy accounting added, which is what the
composition's energy-balance check reads.
"""

from __future__ import annotations

from ..compositionpacks.builtin_battery_electrothermal import (
    ADAPTER_VERSION,
    CELL_ADAPTER_ID,
    CELL_PARTICIPANT,
    MANIFEST as COMPOSITION_MANIFEST,
    THERMAL_ADAPTER_ID,
    THERMAL_PARTICIPANT,
)
from ..domainpacks.frozen import implementation_fingerprint
from ..domains.battery import context as bctx
from ..domains.battery import electrothermal as et
from ..domains.battery import flagship as fl
from ..domains.thermal_models import lumped
from ..execution.multiphysics import (
    AdvanceResult,
    CallbackParticipant,
    InitializationResult,
    ParticipantFactoryDeclaration,
)
from ..scientific.errors import InvalidScientificProblem
from ..scientific.models.definition import ValidityStatus
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity
from .manifest import (
    EXECUTION_PACK_API,
    CompositionDependency,
    ExecutionPackManifest,
    ParticipantFactoryRef,
)

PACK_ID = "system.battery_electrothermal.execution"
PACK_VERSION = "1"


def _unknown(label: str) -> Uncertainty:
    return Uncertainty.unknown(
        f"{label}: participant-local uncertainty is not inferred; the "
        "CompositionPack system UQ is evaluated after the coupled run"
    )


def _window_duration(start: Quantity, end: Quantity) -> Quantity:
    seconds = end.magnitude_in("second") - start.magnitude_in("second")
    if seconds <= 0.0:
        raise InvalidScientificProblem(
            "participant advance window must have positive duration"
        )
    return Quantity(seconds, "second")


def build_cell_participant(spec):
    if spec.participant_id != CELL_PARTICIPANT:
        raise InvalidScientificProblem(
            f"battery cell adapter received participant {spec.participant_id!r}"
        )

    state: dict[str, object] = {
        "electrical": None,
        "cell": None,
        "dissipated_joule": 0.0,
        "windows": 0,
    }
    solver = fl.ElectrothermalCellSolver()

    def _cell_from(inputs) -> et.ElectrothermalCell:
        return fl.flagship_cell(
            cell_id=spec.participant_id,
            ohmic_resistance_reference=inputs["ohmic_resistance_reference"],
            ohmic_activation_energy=inputs["ohmic_activation_energy"],
            polarization_resistance_reference=inputs[
                "polarization_resistance_reference"
            ],
            polarization_activation_energy=inputs[
                "polarization_activation_energy"
            ],
            polarization_capacitance=inputs["polarization_capacitance"],
            reference_temperature=inputs["reference_temperature"],
            charge_state_basis=inputs["charge_state_basis"],
            coulombic_efficiency=inputs["coulombic_efficiency"],
        )

    def initialize(instant, external_inputs, external_uncertainty):
        cell = _cell_from(external_inputs)
        electrical = et.ElectricalState(
            external_inputs["initial_state_of_charge"],
            external_inputs["initial_polarization_voltage"],
        )
        state["cell"] = cell
        state["electrical"] = electrical
        state["dissipated_joule"] = 0.0
        state["windows"] = 0

        evaluated = cell.open_circuit_voltage_curve.evaluate(
            electrical.state_of_charge
        )
        if evaluated.status is not ValidityStatus.IN_DOMAIN or evaluated.value is None:
            raise InvalidScientificProblem(
                f"the declared open-circuit voltage authority gives no value at "
                f"the initial charge state "
                f"{electrical.state_of_charge.magnitude:g}: {evaluated.reason}"
            )
        seed_voltage = Quantity(
            evaluated.value.magnitude_in(bctx.VOLTAGE_UNIT)
            - electrical.polarization_voltage.magnitude_in(bctx.VOLTAGE_UNIT),
            bctx.VOLTAGE_UNIT,
        )
        return InitializationResult(
            outputs={
                # Zero, and it is not consumed: under the declared serial order
                # the cell advances before the thermal body in every window, so
                # the body never sees this seed.
                "heat_generation": Quantity(0.0, bctx.POWER_UNIT),
                "terminal_voltage": seed_voltage,
                "state_of_charge": electrical.state_of_charge,
                "polarization_voltage": electrical.polarization_voltage,
            },
            uncertainty={
                "heat_generation": _unknown("cell heat generation"),
                "terminal_voltage": _unknown("cell terminal voltage"),
                "state_of_charge": _unknown("cell charge state"),
                "polarization_voltage": _unknown("cell polarization voltage"),
            },
            diagnostics={
                "basis": (
                    "the zero heat seed is not consumed before the first cell "
                    "advance under the declared serial order; the seed terminal "
                    "voltage is the declared initial charge state's "
                    "open-circuit value less the declared initial polarization, "
                    "with no ohmic term because no current has been applied and "
                    "no cell temperature exists at initialization"
                ),
                "initial_state": electrical.to_dict(),
                "cell": cell.to_dict(),
            },
        )

    def advance(request):
        cell = state["cell"]
        electrical = state["electrical"]
        if cell is None or electrical is None:
            raise InvalidScientificProblem(
                "battery cell participant advanced before initialization"
            )
        duration = _window_duration(request.start, request.end)
        current = request.inputs["load_current"]
        temperature = request.inputs["cell_temperature"]

        problem_id = (
            f"{spec.participant_id}-"
            f"{request.start.magnitude_in('second'):.17g}-"
            f"{request.end.magnitude_in('second'):.17g}"
        )
        problem = fl.build_electrothermal_problem(
            cell,
            electrical,
            duration=duration,
            problem_id=problem_id,
        )
        solver.bind_step(
            cell,
            electrical,
            problem.problem_id,
            current=current,
            duration=duration,
            temperature=temperature,
        )
        prepared = solver.prepare(problem)
        raw = solver.solve(prepared)
        if not raw.succeeded:
            raise InvalidScientificProblem(
                "the flagship cell solver did not produce a usable step"
            )
        metrics = solver.extract_metrics(prepared, raw)
        validation = solver.validate(prepared, raw)

        advanced = et.ElectricalState(
            metrics[fl.STATE_OF_CHARGE_METRIC],
            metrics[fl.POLARIZATION_VOLTAGE_METRIC],
        )
        state["electrical"] = advanced
        state["dissipated_joule"] = float(state["dissipated_joule"]) + metrics[
            fl.ELECTRICAL_LOSS_METRIC
        ].magnitude_in("joule")
        state["windows"] = int(state["windows"]) + 1

        step = raw.diagnostics["step"]
        return AdvanceResult(
            end=request.end,
            outputs={
                "heat_generation": metrics[fl.HEAT_GENERATION_METRIC],
                "terminal_voltage": metrics[fl.TERMINAL_VOLTAGE_METRIC],
                "state_of_charge": advanced.state_of_charge,
                "polarization_voltage": advanced.polarization_voltage,
            },
            uncertainty={
                "heat_generation": _unknown("cell heat generation"),
                "terminal_voltage": _unknown("cell terminal voltage"),
                "state_of_charge": _unknown("cell charge state"),
                "polarization_voltage": _unknown("cell polarization voltage"),
            },
            substeps=1,
            internal_converged=True,
            max_internal_step=duration,
            diagnostics={
                "solver": solver.identity.to_dict(),
                "realization": (
                    f"{fl.ELECTROTHERMAL_1RC_REALIZATION.realization_id}@"
                    f"{fl.ELECTROTHERMAL_1RC_REALIZATION.version}"
                ),
                "validation": validation.to_dict(),
                "step": step,
                "operating_temperature": temperature.to_dict(),
                "load_current": current.to_dict(),
                "cumulative_dissipated_joule": float(state["dissipated_joule"]),
                "windows_advanced": int(state["windows"]),
                "ocv_authority_digest": cell.ocv_digest,
            },
        )

    return CallbackParticipant(spec, initialize=initialize, advance=advance)


def build_thermal_participant(spec):
    if spec.participant_id != THERMAL_PARTICIPANT:
        raise InvalidScientificProblem(
            f"battery thermal adapter received participant {spec.participant_id!r}"
        )

    state: dict[str, object] = {
        "temperature": None,
        "initial": None,
        "capacity": None,
        "rejected_joule": 0.0,
    }

    def initialize(instant, external_inputs, external_uncertainty):
        initial = external_inputs["initial_temperature"]
        state["temperature"] = initial
        state["initial"] = initial
        state["capacity"] = external_inputs["heat_capacity"]
        state["rejected_joule"] = 0.0
        return InitializationResult(
            outputs={"temperature": initial},
            uncertainty={"temperature": _unknown("cell body temperature")},
            diagnostics={
                "basis": "the initial output is the declared body temperature"
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
        problem = lumped.build_lumped_thermal_problem(body, problem_id=problem_id)
        solver = lumped.LumpedThermalSolver()
        solver.bind_body(
            body, problem.problem_id, heat_input=request.inputs["heat_input"]
        )
        prepared = solver.prepare(
            problem, realization=lumped.LUMPED_CLOSED_FORM_REALIZATION
        )
        raw = solver.solve(prepared)
        if not raw.succeeded:
            raise InvalidScientificProblem(
                "lumped thermal solver did not produce a usable state"
            )
        metrics = solver.extract_metrics(prepared, raw)
        temperature = metrics[lumped.TEMPERATURE_METRIC]
        validation = solver.validate(prepared, raw)

        # What the body rejected over this window, by the same closed form the
        # solver used: the deposited energy less the change in stored energy.
        # Accumulated so the composition can check the balance over the run
        # instead of over one window.
        capacity = request.inputs["heat_capacity"].magnitude_in("joule/kelvin")
        deposited = (
            request.inputs["heat_input"].magnitude_in("watt")
            * duration.magnitude_in("second")
        )
        gained = capacity * (
            temperature.magnitude_in("kelvin")
            - current.magnitude_in("kelvin")
        )
        state["rejected_joule"] = float(state["rejected_joule"]) + (
            deposited - gained
        )
        state["temperature"] = temperature

        initial = state["initial"]
        stored = capacity * (
            temperature.magnitude_in("kelvin") - initial.magnitude_in("kelvin")
        )
        return AdvanceResult(
            end=request.end,
            outputs={"temperature": temperature},
            uncertainty={"temperature": _unknown("cell body temperature")},
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
                "cumulative_stored_joule": stored,
                "cumulative_rejected_joule": float(state["rejected_joule"]),
            },
        )

    return CallbackParticipant(spec, initialize=initialize, advance=advance)


CELL_FACTORY = ParticipantFactoryDeclaration(
    model_id=fl.ELECTROTHERMAL_1RC_MODEL.model_id,
    model_version=fl.ELECTROTHERMAL_1RC_MODEL.version,
    realization_id=fl.ELECTROTHERMAL_1RC_REALIZATION.realization_id,
    realization_version=fl.ELECTROTHERMAL_1RC_REALIZATION.version,
    solver_id=fl.SOLVER_ID,
    solver_version=fl.SOLVER_VERSION,
    adapter_id=CELL_ADAPTER_ID,
    adapter_version=ADAPTER_VERSION,
    factory=build_cell_participant,
    description=(
        "Native adapter for the 1-RC electrothermal cell: carries the charge "
        "state and the polarization voltage across coupling windows."
    ),
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
    description=(
        "Lumped-thermal participant adapter with cumulative energy accounting, "
        "which the composition's energy-balance check reads."
    ),
)


def _factory_ref(declaration: ParticipantFactoryDeclaration) -> ParticipantFactoryRef:
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
        sorted((_factory_ref(CELL_FACTORY), _factory_ref(THERMAL_FACTORY)))
    ),
)


class BatteryElectrothermalExecutionPack:
    manifest = MANIFEST

    def participant_factories(self):
        return (CELL_FACTORY, THERMAL_FACTORY)


BUILTIN_BATTERY_ELECTROTHERMAL_EXECUTION = BatteryElectrothermalExecutionPack()

__all__ = [
    "BUILTIN_BATTERY_ELECTROTHERMAL_EXECUTION",
    "CELL_FACTORY",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
    "THERMAL_FACTORY",
    "BatteryElectrothermalExecutionPack",
    "build_cell_participant",
    "build_thermal_participant",
]
