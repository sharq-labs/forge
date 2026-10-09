"""Coupled hover screening for the drone template: propeller -> motor/ESC -> battery -> winding thermal.

An EXECUTABLE coupling on the generic multiphysics runtime
(:class:`~engcore.execution.multiphysics.MultiphysicsRuntime`), not a
hand-written loop.  Four steady participants, one implicit window, Gauss-Seidel
in the declared order, convergence decided by the runtime on declared edges::

    propeller --shaft power, speed--> electrical --bus current--> battery
                                  ^   |  ^                    |
               winding temp ------+   |  +---- bus voltage ---+   (electrical -> battery: bus current)
                                      v
                                   thermal  (motor heat)

Models (every coefficient is a DECLARED template input with a source; there is
no default anywhere in this module):

* propeller -- static coefficients: ``T = C_T rho n^2 D^4``, ``P = C_P rho n^3 D^5``
  per rotor at the hover thrust ``m g / N``;
* electrical -- DC-equivalent motor: ``K_t = 1 / K_v`` (SI), ``I = Q / K_t + I_0``,
  ``V = omega / K_v + I R(T_w)``, ``R(T) = R_ref (1 + alpha (T - T_ref))``; ESC as a
  declared efficiency; bus power ``N V I / eta_esc``; motor heat ``I^2 R + E I_0``;
* battery -- open-circuit voltage + internal resistance: ``V_b = V_oc - R_int I_bus`` with
  ``I_bus = P_bus / V_b`` from the electrical side; the fixed point is the high-voltage root of
  ``V_oc I - R_int I^2 = P_bus`` and does not exist above ``V_oc^2 / 4 R_int`` (then refused);
* thermal -- lumped steady winding temperature ``T_w = T_amb + R_th Q_motor``.

What this is: a coupled steady screening of ONE hover operating point at the
declared inputs.  What it is not: a performance prediction, a validated
model, or a thermal-safety statement.  Every output uncertainty is UNKNOWN
(not zero); the record lists what the models omit.  A run that does not
converge is refused, never reported as a result.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Callable, Mapping

from ...data import BulkDataResolver, InMemoryBulkStore
from ...execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from ...execution.multiphysics.participant import RuntimeCheckpoint
from ...execution.multiphysics.runtime import MultiphysicsExecutionError
from ...scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from ...scientific.multiphysics.state import CheckpointRecord
from ...scientific.results.uncertainty import Uncertainty
from ...scenarios.timeline import canonical_digest
from ...scientific.composition.conversion import EnergyConversion
from ...scientific.units.quantity import Quantity
from .template import ProductTemplate, TemplateRefusal

ADAPTER_ID = "forge.drone_coupled_hover"
ADAPTER_VERSION = "1"
CLASSIFICATION = "coupled_steady_hover_screening_not_validated"

#: Template inputs the coupled screening reads (all must be declared with a source).
COUPLED_INPUTS = (
    "takeoff_mass", "gravity", "air_density", "rotor_count", "rotor_diameter",
    "prop_thrust_coefficient", "prop_power_coefficient",
    "motor_kv", "motor_resistance", "motor_no_load_current", "motor_resistance_reference_temperature",
    "winding_temperature_coefficient", "esc_efficiency",
    "battery_open_circuit_voltage", "battery_internal_resistance", "battery_capacity",
    "ambient_temperature", "motor_thermal_resistance",
)

OMITTED = ("propeller coefficients' dependence on speed and inflow (static values used)", "rotor interference",
           "ESC losses' dependence on duty and current", "motor iron loss beyond the no-load current", "battery voltage sag over discharge",
           "battery and ESC temperature", "transient warm-up (steady winding temperature)", "manufacturing scatter")

#: Convergence tolerances of the coupled fixed point (numerical settings, part of the plan's identity).
TEMPERATURE_TOLERANCE = Quantity(1e-6, "K")
VOLTAGE_TOLERANCE = Quantity(1e-9, "V")
CURRENT_TOLERANCE = Quantity(1e-9, "A")
MAX_ITERATIONS = 200

#: Declared energy crossings (the graph refuses an undeclared one; an undeclared efficiency is UNKNOWN, not 1).
SHAFT = EnergyConversion("rigid_shaft", "mechanical", "mechanical", "W", 1.0, description=(
    "the shaft transmits the propeller's absorbed power whole; bearing and windage losses are carried by the motor's no-load current"))
LOSS_TO_HEAT = EnergyConversion("motor_loss_to_winding_node", "motor_loss", "heat", "W", 1.0, description=(
    "by the lumped model's definition: motor_thermal_resistance is declared per watt of TOTAL motor loss, so all of it enters the node"))

_UNKNOWN = Uncertainty.unknown("coupled hover screening: output uncertainty not quantified (declared inputs carry none)")


def _port(port_id: str, direction: str, quantity: str, unit: str) -> PortDefinition:
    return PortDefinition(port_id, PortDirection(direction), PortKind.SCALAR, quantity, unit)


def _spec(participant_id: str, model: str, ports: tuple[PortDefinition, ...]) -> ParticipantSpec:
    return ParticipantSpec(participant_id, model, "1", model, "1", "forge.closed_form", "1", ADAPTER_ID, ADAPTER_VERSION, ports,
                           transient=True, checkpointable=True, deterministic_restore=True,
                           description="steady algebraic participant; the window is a coupling window, not time marching")


def _stateless(spec: ParticipantSpec, fn: Callable[[Mapping[str, Quantity]], dict[str, Quantity]],
               initial: dict[str, Quantity]) -> CallbackParticipant:
    digest = hashlib.sha256(f"stateless:{spec.participant_id}".encode()).hexdigest()

    def initialize(_t, _inputs, _uq):
        return InitializationResult(dict(initial), {k: _UNKNOWN for k in initial})

    def advance(request):
        out = fn(dict(request.inputs))
        return AdvanceResult(request.end, out, {k: _UNKNOWN for k in out}, 1, True)

    return CallbackParticipant(spec, initialize=initialize, advance=advance,
                               checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, digest, True), None),
                               restore=lambda cp: None)


def _declared(template: ProductTemplate) -> dict[str, float]:
    """The declared inputs in the units the closed forms use; refuses UNKNOWN and non-physical values."""
    v = template.values(*COUPLED_INPUTS)
    units = {"takeoff_mass": "kg", "gravity": "m/s^2", "air_density": "kg/m^3", "rotor_count": "dimensionless", "rotor_diameter": "m",
             "prop_thrust_coefficient": "dimensionless", "prop_power_coefficient": "dimensionless", "motor_kv": "rad/s/V",
             "motor_resistance": "ohm", "motor_no_load_current": "A", "motor_resistance_reference_temperature": "K",
             "winding_temperature_coefficient": "1/K", "esc_efficiency": "dimensionless", "battery_open_circuit_voltage": "V",
             "battery_internal_resistance": "ohm", "battery_capacity": "A*h", "ambient_temperature": "K", "motor_thermal_resistance": "K/W"}
    x = {k: v[k].magnitude_in(u) for k, u in units.items()}
    positive = ("takeoff_mass", "gravity", "air_density", "rotor_diameter", "prop_thrust_coefficient", "prop_power_coefficient", "motor_kv",
                "motor_resistance", "battery_open_circuit_voltage", "battery_internal_resistance", "battery_capacity",
                "motor_resistance_reference_temperature", "ambient_temperature", "motor_thermal_resistance")
    for name in positive:
        if not (math.isfinite(x[name]) and x[name] > 0):
            raise TemplateRefusal(f"{name} must be finite and > 0 in {units[name]}")
    for name in ("motor_no_load_current", "winding_temperature_coefficient"):
        if not (math.isfinite(x[name]) and x[name] >= 0):
            raise TemplateRefusal(f"{name} must be finite and >= 0 in {units[name]}")
    if not 0 < x["esc_efficiency"] <= 1:
        raise TemplateRefusal("esc_efficiency must be in (0, 1]")
    n = x["rotor_count"]
    if n != int(n) or n < 3:
        raise TemplateRefusal("rotor_count must be an integer >= 3")
    units_bound = [i for i in template.assembly.system.instances if i.definition_id == "propulsion_unit"]
    if len(units_bound) != int(n):
        raise TemplateRefusal(f"declared rotor_count {int(n)} disagrees with the {len(units_bound)} propulsion units of the bound structure")
    return x


def build_runtime(template: ProductTemplate) -> tuple[MultiphysicsRuntime, dict[str, Quantity], dict[str, float]]:
    """The physics graph, implicit plan and participants for ``template``; also the seeds and the declared values."""
    x = _declared(template)
    n_rot = int(x["rotor_count"])
    thrust = x["takeoff_mass"] * x["gravity"] / n_rot
    rho, D = x["air_density"], x["rotor_diameter"]

    def propeller(_inputs):
        n = math.sqrt(thrust / (x["prop_thrust_coefficient"] * rho * D ** 4))  # rev/s
        power = x["prop_power_coefficient"] * rho * n ** 3 * D ** 5
        return {"shaft_power": Quantity(power, "W"), "shaft_speed": Quantity(2 * math.pi * n, "rad/s")}

    kv = x["motor_kv"]  # rad/s/V
    kt = 1.0 / kv       # N*m/A (SI motor constant equality)

    def electrical(i):
        w = i["shaft_speed"].magnitude_in("rad/s")
        q = i["shaft_power"].magnitude_in("W") / w
        tw, vb = i["winding_temperature"].magnitude_in("K"), i["bus_voltage"].magnitude_in("V")
        r = x["motor_resistance"] * (1 + x["winding_temperature_coefficient"] * (tw - x["motor_resistance_reference_temperature"]))
        if not r > 0:
            raise TemplateRefusal("the winding resistance model gave R <= 0 at the iterated temperature")
        current = q / kt + x["motor_no_load_current"]
        emf = w / kv
        volts = emf + current * r
        heat = current * current * r + emf * x["motor_no_load_current"]
        if not vb > 0:
            raise TemplateRefusal("the iterated bus voltage is not positive: the battery cannot deliver the demanded power")
        bus = n_rot * volts * current / x["esc_efficiency"]
        return {"bus_current": Quantity(bus / vb, "A"), "bus_power": Quantity(bus, "W"), "motor_heat": Quantity(heat, "W"),
                "motor_current": Quantity(current, "A"),
                "motor_voltage": Quantity(volts, "V"), "duty": Quantity(volts / vb, "dimensionless")}

    voc, rint = x["battery_open_circuit_voltage"], x["battery_internal_resistance"]

    def battery(i):
        current = i["bus_current"].magnitude_in("A")
        volts = voc - current * rint
        if not volts > 0:
            raise TemplateRefusal(f"the battery cannot deliver the demanded current: V_oc - I R_int = {volts:.6g} V "
                                  f"(maximum deliverable power V_oc^2 / 4 R_int = {voc * voc / (4 * rint):.6g} W)")
        return {"bus_voltage": Quantity(volts, "V"), "pack_current": Quantity(current, "A"),
                "battery_heat": Quantity(current * current * rint, "W")}

    def thermal(i):
        return {"winding_temperature": Quantity(x["ambient_temperature"] + x["motor_thermal_resistance"] * i["motor_heat"].magnitude_in("W"), "K")}

    specs = {
        "propeller": _spec("propeller", "forge.propeller_static_coefficients",
                           (_port("shaft_power", "output", "power", "W"), _port("shaft_speed", "output", "angular_velocity", "rad/s"))),
        "electrical": _spec("electrical", "forge.dc_equivalent_motor_esc", (
            _port("shaft_power", "input", "power", "W"), _port("shaft_speed", "input", "angular_velocity", "rad/s"),
            _port("winding_temperature", "input", "temperature", "K"), _port("bus_voltage", "input", "voltage", "V"),
            _port("bus_current", "output", "current", "A"), _port("bus_power", "output", "power", "W"), _port("motor_heat", "output", "power", "W"),
            _port("motor_current", "output", "current", "A"), _port("motor_voltage", "output", "voltage", "V"),
            _port("duty", "output", "ratio", "dimensionless"))),
        "battery": _spec("battery", "forge.battery_ocv_internal_resistance", (
            _port("bus_current", "input", "current", "A"), _port("bus_voltage", "output", "voltage", "V"),
            _port("pack_current", "output", "current", "A"), _port("battery_heat", "output", "power", "W"))),
        "thermal": _spec("thermal", "forge.lumped_steady_winding", (
            _port("motor_heat", "input", "power", "W"), _port("winding_temperature", "output", "temperature", "K"))),
    }
    seeds = {"winding_temperature": Quantity(x["ambient_temperature"], "K"), "bus_voltage": Quantity(voc, "V")}
    zero = {"bus_current": Quantity(0, "A"), "bus_power": Quantity(0, "W"), "motor_heat": Quantity(0, "W"), "motor_current": Quantity(0, "A"),
            "motor_voltage": Quantity(0, "V"), "duty": Quantity(0, "dimensionless")}
    participants = {
        "propeller": _stateless(specs["propeller"], propeller, propeller({})),
        "electrical": _stateless(specs["electrical"], electrical, zero),
        "battery": _stateless(specs["battery"], battery, {"bus_voltage": seeds["bus_voltage"], "pack_current": Quantity(0, "A"),
                                                          "battery_heat": Quantity(0, "W")}),
        "thermal": _stateless(specs["thermal"], thermal, {"winding_temperature": seeds["winding_temperature"]}),
    }
    edges = (
        CouplingEdge("shaft_power", PortRef("propeller", "shaft_power"), PortRef("electrical", "shaft_power"), conversion=SHAFT,
                     description="shaft power per rotor"),
        CouplingEdge("speed", PortRef("propeller", "shaft_speed"), PortRef("electrical", "shaft_speed"), description="shaft speed"),
        CouplingEdge("bus_current", PortRef("electrical", "bus_current"), PortRef("battery", "bus_current"), description="DC bus current of all units"),
        CouplingEdge("bus_voltage", PortRef("battery", "bus_voltage"), PortRef("electrical", "bus_voltage"), description="battery terminal voltage"),
        CouplingEdge("motor_heat", PortRef("electrical", "motor_heat"), PortRef("thermal", "motor_heat"), conversion=LOSS_TO_HEAT,
                     description="per-motor heat"),
        CouplingEdge("winding_temperature", PortRef("thermal", "winding_temperature"), PortRef("electrical", "winding_temperature"),
                     description="winding temperature feeding R(T)"),
    )
    plan = CouplingPlan("drone-coupled-hover", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        ("propeller", "electrical", "battery", "thermal"),
                        (ConvergenceCriterion("winding_temperature", 0.0, TEMPERATURE_TOLERANCE),
                         ConvergenceCriterion("bus_voltage", 0.0, VOLTAGE_TOLERANCE),
                         ConvergenceCriterion("bus_current", 0.0, CURRENT_TOLERANCE)),
                        max_iterations=MAX_ITERATIONS, fail_on_nonconvergence=True)
    store = InMemoryBulkStore()
    graph = PhysicsGraph("drone-coupled-hover", tuple(specs.values()), edges,
                         description="propeller -> electrical -> battery -> thermal hover chain (steady, declared inputs)")
    return MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store), seeds, x


def coupled_hover_screening(template: ProductTemplate) -> dict[str, Any]:
    """Run the coupled hover chain on the multiphysics runtime from DECLARED inputs.

    Refused (TemplateRefusal) while any needed input is UNKNOWN, when the battery cannot deliver the
    demanded power, or when the coupled fixed point is not reached within the declared iteration budget.
    """
    runtime, seeds, x = build_runtime(template)
    initial = {"bus_voltage": seeds["bus_voltage"], "winding_temperature": seeds["winding_temperature"],
               "bus_current": Quantity(0, "A"), "motor_heat": Quantity(0, "W")}
    try:
        run = runtime.run("drone-coupled-hover", external_inputs={}, initial_coupling_values=initial,
                          initial_coupling_uncertainty={k: _UNKNOWN for k in initial})
    except MultiphysicsExecutionError as exc:
        cause = exc.__cause__ if isinstance(exc.__cause__, TemplateRefusal) else None
        raise TemplateRefusal(f"coupled hover refused: {cause or exc}") from exc
    except TemplateRefusal as exc:
        raise TemplateRefusal(f"coupled hover refused: {exc}") from exc
    window = run.windows[0]
    if window.outcome.value != "converged":
        raise TemplateRefusal(f"the coupled fixed point was not reached ({window.outcome.value}); no hover state is reported")
    out = run.final_outputs

    def q(key: str, unit: str) -> Quantity:
        return Quantity(out[key]["magnitude"], unit)

    n_rot = int(x["rotor_count"])
    shaft, speed = q("propeller.shaft_power", "W"), q("propeller.shaft_speed", "rad/s")
    bus, pack = q("electrical.bus_power", "W"), q("battery.pack_current", "A")
    shaft_total = n_rot * shaft.magnitude_in("W")
    heat = q("electrical.motor_heat", "W").magnitude_in("W")
    esc_loss = bus.magnitude_in("W") * (1 - x["esc_efficiency"])
    balance = bus.magnitude_in("W") - (shaft_total + n_rot * heat + esc_loss)
    duty = q("electrical.duty", "dimensionless").magnitude_in("dimensionless")
    return {
        "classification": CLASSIFICATION, "model": f"{ADAPTER_ID} v{ADAPTER_VERSION} on MultiphysicsRuntime (implicit, serial)",
        "run_id": run.run_id, "run_digest": canonical_digest(run.to_dict()), "graph_fingerprint": run.graph_fingerprint,
        "plan_fingerprint": run.plan_fingerprint, "iterations": len(window.iterations),
        "shaft_speed": speed, "shaft_torque": Quantity(shaft.magnitude_in("W") / speed.magnitude_in("rad/s"), "N*m"), "shaft_power_total": Quantity(shaft_total, "W"),
        "motor_current": q("electrical.motor_current", "A"), "motor_voltage": q("electrical.motor_voltage", "V"),
        "duty": Quantity(duty, "dimensionless"), "bus_power": bus, "pack_current": pack, "bus_voltage": q("battery.bus_voltage", "V"),
        "winding_temperature": q("thermal.winding_temperature", "K"), "motor_heat": Quantity(heat, "W"),
        "battery_heat": q("battery.battery_heat", "W"),
        "rated_capacity_over_current": Quantity(x["battery_capacity"] / pack.magnitude_in("A"), "h"),
        "energy_balance_residual": Quantity(balance, "W"),
        "motor_voltage_within_bus": duty <= 1.0,
        "uncertainty": "UNKNOWN",
        "omitted": OMITTED,
        "notes": ("rated_capacity_over_current is NOT an endurance prediction (no usable-capacity fraction, sag or temperature)",
                  "motor_voltage_within_bus is a necessary condition at point values only; ESC maximum duty is not modelled",
                  "energy_balance_residual checks the coupled solution's arithmetic (verification), not the physics"),
        "inputs": {k: template.input(k).source_ref for k in COUPLED_INPUTS},
    }


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CLASSIFICATION", "COUPLED_INPUTS", "build_runtime", "coupled_hover_screening"]
