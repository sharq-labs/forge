"""Drive one measured trajectory through Forge's authorized execution path.

Plan -> scenario -> authorized multiphysics run -> per-window trajectory. There
is no second state engine here: the marching is the multiphysics runtime's, the
physics is the flagship kernel's, and this module only builds the intent and the
scenario and reads the run record back.

What the model is given, and what it is not
--------------------------------------------
Given: the measured current at every sample instant, the ambient temperature,
the measured cell temperature **at the first instant only**, and the charge
protocol's full-charge initial state. Not given: any measured voltage at any
instant, and any measured temperature after the first.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from engcore.assembly.domainpacks import (
    production_composition_packs,
    production_execution_packs,
)
from engcore.assembly.multiphysics import execute_authorized_graph_plan
from engcore.compositionpacks.builtin_battery_electrothermal import (
    CAPABILITY_ID,
    CELL_PARTICIPANT,
    F_C1,
    F_CTH,
    F_CURRENT,
    F_EA0,
    F_EA1,
    F_ETA,
    F_HA,
    F_QBASIS,
    F_R0,
    F_R1,
    F_T0,
    F_TAMB,
    F_TREF,
    F_VP0,
    F_Z0,
    THERMAL_PARTICIPANT,
)
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.battery import context as bctx
from engcore.domains.battery import electrothermal as et
from engcore.domains.battery.flagship_ocv import (
    CHARGE_STATE_BASIS_AH,
    OCV_LOWER,
)
from engcore.planning import (
    ContextOfUse,
    EngineeringComponent,
    EngineeringIntent,
    FactRole,
    IntentFact,
    IntentQuantityOfInterest,
    PlannerPolicy,
    SimulationHorizon,
    plan_engineering_intent,
)
from engcore.planning.production import production_planning_registries
from engcore.planning.records import PlannedQuantityBinding
from engcore.scenarios import (
    InterpolationKind,
    QuantityOfInterest,
    ScenarioEvent,
    ScenarioSpecification,
    ScenarioSegment,
    TerminationCondition,
    TimeSample,
    TimeSeriesInput,
)
from engcore.scientific.ir.constraints import (
    ConstraintDefinition,
    ConstraintOperator,
)
from engcore.scientific.multiphysics import PortRef
from engcore.scientific.units.quantity import Quantity

#: The run stops here rather than marching past the open-circuit voltage
#: authority's declared interval. It is the authority's own lower bound, not a
#: number chosen for convenience, and a stop leaves a termination receipt the
#: campaign reads as "no prediction beyond this instant".
SOC_FLOOR = OCV_LOWER

CAMPAIGN_COMPONENT = "cell"

#: The named parameters a flagship run needs, in the order the fitter packs them.
PARAMETER_ORDER = (
    "ohmic_resistance_reference",
    "ohmic_activation_energy",
    "polarization_resistance_reference",
    "polarization_activation_energy",
    "polarization_capacitance",
    "thermal_capacitance",
    "thermal_conductance",
)

_PARAMETER_UNITS = {
    "ohmic_resistance_reference": bctx.RESISTANCE_UNIT,
    "ohmic_activation_energy": et.ACTIVATION_ENERGY_UNIT,
    "polarization_resistance_reference": bctx.RESISTANCE_UNIT,
    "polarization_activation_energy": et.ACTIVATION_ENERGY_UNIT,
    "polarization_capacitance": et.CAPACITANCE_UNIT,
    "thermal_capacitance": "joule/kelvin",
    "thermal_conductance": "watt/kelvin",
}

REFERENCE_TEMPERATURE_K = 298.15


def parameter_quantities(values) -> dict[str, Quantity]:
    """Pack a vector in :data:`PARAMETER_ORDER` into named quantities."""
    if len(values) != len(PARAMETER_ORDER):
        raise ValueError(
            f"expected {len(PARAMETER_ORDER)} parameters, got {len(values)}"
        )
    return {
        name: Quantity(float(value), _PARAMETER_UNITS[name])
        for name, value in zip(PARAMETER_ORDER, values)
    }


def build_intent(
    *,
    parameters: dict[str, Quantity],
    ambient_k: float,
    initial_temperature_k: float,
    horizon_s: float,
    initial_state_of_charge: float = 1.0,
    statement: str = "battery electrothermal flagship",
) -> EngineeringIntent:
    facts = (
        IntentFact(F_R0, FactRole.PARAMETER, parameters["ohmic_resistance_reference"]),
        IntentFact(F_EA0, FactRole.PARAMETER, parameters["ohmic_activation_energy"]),
        IntentFact(
            F_R1, FactRole.PARAMETER, parameters["polarization_resistance_reference"]
        ),
        IntentFact(
            F_EA1, FactRole.PARAMETER, parameters["polarization_activation_energy"]
        ),
        IntentFact(F_C1, FactRole.PARAMETER, parameters["polarization_capacitance"]),
        IntentFact(
            F_TREF,
            FactRole.PARAMETER,
            Quantity(REFERENCE_TEMPERATURE_K, bctx.TEMPERATURE_UNIT),
        ),
        IntentFact(
            F_QBASIS,
            FactRole.PARAMETER,
            Quantity(CHARGE_STATE_BASIS_AH, bctx.CAPACITY_UNIT),
        ),
        IntentFact(F_ETA, FactRole.PARAMETER, Quantity(1.0, bctx.DIMENSIONLESS)),
        IntentFact(
            F_Z0,
            FactRole.INITIAL_CONDITION,
            Quantity(initial_state_of_charge, bctx.DIMENSIONLESS),
        ),
        IntentFact(
            F_VP0, FactRole.INITIAL_CONDITION, Quantity(0.0, bctx.VOLTAGE_UNIT)
        ),
        IntentFact(
            F_CURRENT, FactRole.BOUNDARY_CONDITION, Quantity(0.0, bctx.CURRENT_UNIT)
        ),
        IntentFact(F_CTH, FactRole.PARAMETER, parameters["thermal_capacitance"]),
        IntentFact(F_HA, FactRole.PARAMETER, parameters["thermal_conductance"]),
        IntentFact(
            F_TAMB,
            FactRole.BOUNDARY_CONDITION,
            Quantity(ambient_k, bctx.TEMPERATURE_UNIT),
        ),
        IntentFact(
            F_T0,
            FactRole.INITIAL_CONDITION,
            Quantity(initial_temperature_k, bctx.TEMPERATURE_UNIT),
        ),
    )
    return EngineeringIntent(
        statement,
        ContextOfUse("predict", CAMPAIGN_COMPONENT, "error"),
        (EngineeringComponent(CAMPAIGN_COMPONENT, "battery.electrothermal"),),
        (),
        facts,
        (
            IntentQuantityOfInterest(
                "terminal_voltage",
                "terminal_voltage",
                bctx.VOLTAGE_UNIT,
                CAMPAIGN_COMPONENT,
            ),
            IntentQuantityOfInterest(
                "cell_temperature",
                "cell_temperature",
                bctx.TEMPERATURE_UNIT,
                CAMPAIGN_COMPONENT,
            ),
            IntentQuantityOfInterest(
                "state_of_charge",
                "state_of_charge",
                bctx.DIMENSIONLESS,
                CAMPAIGN_COMPONENT,
            ),
        ),
        simulation_horizon=SimulationHorizon(
            Quantity(0.0, "s"), Quantity(horizon_s, "s")
        ),
    )


#: Which authorized output answers each declared observable. The planner does
#: not derive this -- a capability declares what it produces, not which port
#: carries it -- so the campaign states it, and the accompanying test pins each
#: port against the blueprint's own port semantics so the statement cannot drift
#: from the pack.
QUANTITY_PORTS = (
    ("terminal_voltage", CELL_PARTICIPANT, "terminal_voltage"),
    ("cell_temperature", THERMAL_PARTICIPANT, "temperature"),
    ("state_of_charge", CELL_PARTICIPANT, "state_of_charge"),
)


def quantity_bindings() -> tuple[PlannedQuantityBinding, ...]:
    return tuple(
        PlannedQuantityBinding(quantity_id, PortRef(participant, port))
        for quantity_id, participant, port in QUANTITY_PORTS
    )


def plan(intent: EngineeringIntent):
    planned = plan_engineering_intent(
        intent,
        production_planning_registries(),
        PlannerPolicy(
            capability_by_qoi={
                "terminal_voltage": CAPABILITY_ID,
                "cell_temperature": CAPABILITY_ID,
                "state_of_charge": CAPABILITY_ID,
            }
        ),
    )
    if not planned.graph_plans:
        raise RuntimeError(f"planner produced no graph plan: {planned}")
    return planned.graph_plans[0]


def build_scenario(
    graph_plan,
    *,
    times_s,
    currents_a,
    scenario_id: str,
    version: str = "1",
    refinement: int = 1,
) -> ScenarioSpecification:
    """The measured current profile, as a held schedule cut at every sample.

    The schedule interpolation is STEP: a sampled current is the value that was
    drawn until the next sample, and reading a straight line between two samples
    would invent a ramp the instrument never recorded.

    ``refinement`` subdivides every measured interval that many times. The
    schedule is unchanged by it -- a held value is the same held value -- so the
    only thing that moves is the coupling window, which is exactly what a
    time-step study needs to vary.
    """
    if len(times_s) != len(currents_a) or len(times_s) < 2:
        raise ValueError("a scenario needs at least two aligned samples")
    start = Quantity(float(times_s[0]), "s")
    end = Quantity(float(times_s[-1]), "s")
    samples = tuple(
        TimeSample(Quantity(float(t), "s"), Quantity(float(i), bctx.CURRENT_UNIT))
        for t, i in zip(times_s, currents_a)
    )
    series = TimeSeriesInput(F_CURRENT, samples, InterpolationKind.STEP)

    instants: list[float] = []
    for left, right in zip(times_s, times_s[1:]):
        for step in range(refinement):
            value = float(left) + (float(right) - float(left)) * step / refinement
            if value > float(times_s[0]):
                instants.append(value)
    events = tuple(
        ScenarioEvent(f"sample-{index:05d}", Quantity(value, "s"))
        for index, value in enumerate(sorted(set(instants)))
        if value < float(times_s[-1])
    )

    qois = (
        QuantityOfInterest("terminal_voltage", "terminal_voltage", bctx.VOLTAGE_UNIT),
        QuantityOfInterest("cell_temperature", "cell_temperature", bctx.TEMPERATURE_UNIT),
        QuantityOfInterest("state_of_charge", "state_of_charge", bctx.DIMENSIONLESS),
    )
    # A termination condition is evaluated at a window boundary, which is after
    # that window has already advanced. Stopping exactly at the authority's
    # lower bound would therefore let the crossing window run first, and that
    # window is the one the open-circuit voltage curve refuses. So the bound
    # carries one window's worth of charge as a margin, computed from this
    # profile's own largest current and longest interval. It costs the last
    # few thousandths of the charge axis and it is why the stop is a recorded
    # termination rather than a raised refusal that would lose the whole run.
    peak_current = max(abs(float(i)) for i in currents_a)
    longest_step = max(
        float(b) - float(a) for a, b in zip(times_s, times_s[1:])
    ) / max(refinement, 1)
    margin = peak_current * longest_step / 3600.0 / CHARGE_STATE_BASIS_AH
    termination = TerminationCondition(
        "charge_state_below_ocv_authority",
        ConstraintDefinition(
            name="charge_state_below_ocv_authority",
            metric="state_of_charge",
            operator=ConstraintOperator.LESS_EQUAL,
            bound=Quantity(SOC_FLOOR + margin, bctx.DIMENSIONLESS),
            description=(
                "The declared open-circuit voltage authority ends at "
                f"{SOC_FLOOR:.6f}. Marching past it would need a value the curve "
                "refuses to give, so the run stops one window's charge above it "
                "and records why instead of asking."
            ),
        ),
    )
    return ScenarioSpecification(
        scenario_id,
        version,
        start,
        end,
        segments=(
            ScenarioSegment("measured-discharge", start, end, inputs=(series,)),
        ),
        events=events,
        quantities_of_interest=qois,
        termination_conditions=(termination,),
    )


def run_trajectory(
    *,
    parameters: dict[str, Quantity],
    times_s,
    currents_a,
    ambient_k: float,
    initial_temperature_k: float,
    run_id: str,
    scenario_id: str,
    refinement: int = 1,
    initial_state_of_charge: float = 1.0,
):
    """Plan, bind the scenario and execute. Returns the authorized run."""
    intent = build_intent(
        parameters=parameters,
        ambient_k=ambient_k,
        initial_temperature_k=initial_temperature_k,
        horizon_s=float(times_s[-1]) - float(times_s[0]),
        initial_state_of_charge=initial_state_of_charge,
        statement=f"battery electrothermal flagship {scenario_id}",
    )
    graph_plan = plan(intent)
    scenario = build_scenario(
        graph_plan,
        times_s=[float(t) - float(times_s[0]) for t in times_s],
        currents_a=currents_a,
        scenario_id=scenario_id,
        refinement=refinement,
    )
    graph_plan = replace(
        graph_plan, scenario=scenario, quantity_bindings=quantity_bindings()
    )
    store = InMemoryBulkStore()
    return execute_authorized_graph_plan(
        graph_plan,
        run_id=run_id,
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store),
        store=store,
    )


def trajectory_from_run(authorized) -> list[dict[str, Any]]:
    """Per-window predictions, read back from the run's own step diagnostics.

    One row per coupling window, carrying the instant the window ended at and
    what each participant produced there. Nothing is recomputed.
    """
    rows: list[dict[str, Any]] = []
    record = authorized.run
    for window in record.windows:
        steps = {
            item.participant_id: item
            for item in window.iterations[-1].participant_steps
        }
        cell = steps.get(CELL_PARTICIPANT)
        thermal = steps.get(THERMAL_PARTICIPANT)
        if cell is None or thermal is None or cell.diagnostics is None:
            continue
        step = cell.diagnostics["step"]
        rows.append(
            {
                "t": window.end.magnitude_in("second"),
                "terminal_voltage": Quantity.from_dict(
                    step[et.TERMINAL_VOLTAGE]
                ).magnitude_in(bctx.VOLTAGE_UNIT),
                "open_circuit_voltage": Quantity.from_dict(
                    step[et.OPEN_CIRCUIT_VOLTAGE]
                ).magnitude_in(bctx.VOLTAGE_UNIT),
                "ohmic_drop": Quantity.from_dict(
                    step[et.OHMIC_DROP]
                ).magnitude_in(bctx.VOLTAGE_UNIT),
                "polarization_voltage": Quantity.from_dict(
                    step[et.POLARIZATION_VOLTAGE]
                ).magnitude_in(bctx.VOLTAGE_UNIT),
                "state_of_charge": Quantity.from_dict(
                    step["final_state"][bctx.STATE_OF_CHARGE]
                ).magnitude_in(bctx.DIMENSIONLESS),
                "heat_generation": Quantity.from_dict(
                    step[et.HEAT_GENERATION]
                ).magnitude_in(bctx.POWER_UNIT),
                "electrical_loss": Quantity.from_dict(
                    step[et.ELECTRICAL_LOSS]
                ).magnitude_in("joule"),
                "load_current": Quantity.from_dict(
                    cell.diagnostics["load_current"]
                ).magnitude_in(bctx.CURRENT_UNIT),
                "cell_temperature": Quantity.from_dict(
                    thermal.diagnostics["final_temperature"]
                ).magnitude_in(bctx.TEMPERATURE_UNIT),
                "operating_temperature": Quantity.from_dict(
                    cell.diagnostics["operating_temperature"]
                ).magnitude_in(bctx.TEMPERATURE_UNIT),
            }
        )
    return rows


__all__ = [
    "CAMPAIGN_COMPONENT",
    "PARAMETER_ORDER",
    "REFERENCE_TEMPERATURE_K",
    "SOC_FLOOR",
    "QUANTITY_PORTS",
    "build_intent",
    "build_scenario",
    "parameter_quantities",
    "plan",
    "quantity_bindings",
    "run_trajectory",
    "trajectory_from_run",
]
