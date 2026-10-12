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
from ...scientific.errors import InvalidScientificProblem
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
    "ambient_temperature", "motor_thermal_resistance", "winding_temperature_limit",
)

#: Kv must be declared in a unit that NAMES its angle: in pint the radian is dimensionless, so "Hz/V" (rev/s per V)
#: would otherwise be read 1:1 as rad/s/V -- a silent factor of 2*pi.
_ANGLE_TOKENS = ("revolutions_per_minute", "revolutions_per_second", "radian", "turn", "revolution", "degree")

#: Runtime participants carry the TEMPLATE participant ids, so the template's coupling declarations name graph edges.
PARTICIPANTS = ("propeller_static", "motor_esc", "battery_ecm", "winding_thermal")
#: (template coupling source, target, quantity) -> the executed graph edge id
EDGE_OF_COUPLING = {("propeller_static", "motor_esc", "shaft_torque_and_speed"): ("shaft_power", "speed"),
                    ("motor_esc", "battery_ecm", "bus_current"): ("bus_current",),
                    ("battery_ecm", "motor_esc", "bus_voltage"): ("bus_voltage",),
                    ("motor_esc", "winding_thermal", "motor_heat"): ("motor_heat",),
                    ("winding_thermal", "motor_esc", "winding_temperature"): ("winding_temperature",)}

OMITTED = ("propeller coefficients' dependence on speed and inflow (static values used)", "rotor interference",
           "ESC losses' dependence on duty and current", "motor iron loss beyond the no-load current", "battery voltage sag over discharge",
           "battery and ESC temperature", "transient warm-up (steady winding temperature)", "manufacturing scatter",
           "a split of motor loss between winding, iron and bearings (motor_thermal_resistance must be per watt of TOTAL loss; a "
           "datasheet value per watt of copper loss is a different quantity and would be misused here)",
           "linear R(T) beyond the declared winding_temperature_limit (such states are refused)")

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
                           description=("steady algebraic participant run in the runtime's transient interface: the one 1 s "
                                        "window is a coupling window, not a time interval, and no state advances"))


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
             "battery_internal_resistance": "ohm", "battery_capacity": "A*h", "ambient_temperature": "K", "motor_thermal_resistance": "K/W",
             "winding_temperature_limit": "K"}
    kv_unit = str(v["motor_kv"].units)
    if not any(tok in kv_unit for tok in _ANGLE_TOKENS):
        raise TemplateRefusal(f"motor_kv is declared in {kv_unit!r}, which names no angle (rpm/V, rad/s/V, turn/s/V ...): "
                              "rev/s and rad/s are both 1/s in the unit system, and guessing which one is meant is a factor of 2*pi")
    x = {k: v[k].magnitude_in(u) for k, u in units.items()}
    positive = ("takeoff_mass", "gravity", "air_density", "rotor_diameter", "prop_thrust_coefficient", "prop_power_coefficient", "motor_kv",
                "motor_resistance", "battery_open_circuit_voltage", "battery_internal_resistance", "battery_capacity",
                "motor_resistance_reference_temperature", "ambient_temperature", "motor_thermal_resistance", "winding_temperature_limit")
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
    if x["winding_temperature_limit"] <= x["ambient_temperature"]:
        raise TemplateRefusal("winding_temperature_limit must exceed ambient_temperature")
    # the motor current does not depend on temperature, so a steady winding temperature exists iff
    # R_th * I^2 * R_ref * alpha < 1 -- decided here, before any iteration, with the reason named
    shaft = propeller({})
    current0 = shaft["shaft_power"].magnitude_in("W") / shaft["shaft_speed"].magnitude_in("rad/s") / kt + x["motor_no_load_current"]
    gain = x["motor_thermal_resistance"] * current0 ** 2 * x["motor_resistance"] * x["winding_temperature_coefficient"]
    if gain >= 1:
        raise TemplateRefusal(f"thermal runaway: R_th I^2 R_ref alpha = {gain:.4g} >= 1, so no steady winding temperature exists "
                              "at this operating point")

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
        "propeller_static": _spec("propeller_static", "forge.propeller_static_coefficients",
                           (_port("shaft_power", "output", "power", "W"), _port("shaft_speed", "output", "angular_velocity", "rad/s"))),
        "motor_esc": _spec("motor_esc", "forge.dc_equivalent_motor_esc", (
            _port("shaft_power", "input", "power", "W"), _port("shaft_speed", "input", "angular_velocity", "rad/s"),
            _port("winding_temperature", "input", "temperature", "K"), _port("bus_voltage", "input", "voltage", "V"),
            _port("bus_current", "output", "current", "A"), _port("bus_power", "output", "power", "W"), _port("motor_heat", "output", "power", "W"),
            _port("motor_current", "output", "current", "A"), _port("motor_voltage", "output", "voltage", "V"),
            _port("duty", "output", "ratio", "dimensionless"))),
        "battery_ecm": _spec("battery_ecm", "forge.battery_ocv_internal_resistance", (
            _port("bus_current", "input", "current", "A"), _port("bus_voltage", "output", "voltage", "V"),
            _port("pack_current", "output", "current", "A"), _port("battery_heat", "output", "power", "W"))),
        "winding_thermal": _spec("winding_thermal", "forge.lumped_steady_winding", (
            _port("motor_heat", "input", "power", "W"), _port("winding_temperature", "output", "temperature", "K"))),
    }
    seeds = {"winding_temperature": Quantity(x["ambient_temperature"], "K"), "bus_voltage": Quantity(voc, "V")}
    zero = {"bus_current": Quantity(0, "A"), "bus_power": Quantity(0, "W"), "motor_heat": Quantity(0, "W"), "motor_current": Quantity(0, "A"),
            "motor_voltage": Quantity(0, "V"), "duty": Quantity(0, "dimensionless")}
    participants = {
        "propeller_static": _stateless(specs["propeller_static"], propeller, propeller({})),
        "motor_esc": _stateless(specs["motor_esc"], electrical, zero),
        "battery_ecm": _stateless(specs["battery_ecm"], battery, {"bus_voltage": seeds["bus_voltage"], "pack_current": Quantity(0, "A"),
                                                          "battery_heat": Quantity(0, "W")}),
        "winding_thermal": _stateless(specs["winding_thermal"], thermal, {"winding_temperature": seeds["winding_temperature"]}),
    }
    edges = (
        CouplingEdge("shaft_power", PortRef("propeller_static", "shaft_power"), PortRef("motor_esc", "shaft_power"), conversion=SHAFT,
                     description="shaft power per rotor"),
        CouplingEdge("speed", PortRef("propeller_static", "shaft_speed"), PortRef("motor_esc", "shaft_speed"), description="shaft speed"),
        CouplingEdge("bus_current", PortRef("motor_esc", "bus_current"), PortRef("battery_ecm", "bus_current"), description="DC bus current of all units"),
        CouplingEdge("bus_voltage", PortRef("battery_ecm", "bus_voltage"), PortRef("motor_esc", "bus_voltage"), description="battery terminal voltage"),
        CouplingEdge("motor_heat", PortRef("motor_esc", "motor_heat"), PortRef("winding_thermal", "motor_heat"), conversion=LOSS_TO_HEAT,
                     description="per-motor heat"),
        CouplingEdge("winding_temperature", PortRef("winding_thermal", "winding_temperature"), PortRef("motor_esc", "winding_temperature"),
                     description="winding temperature feeding R(T)"),
    )
    plan = CouplingPlan("drone-coupled-hover", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        PARTICIPANTS,
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
    except TemplateRefusal as exc:  # raised by a participant (the runtime does not wrap it)
        raise TemplateRefusal(f"coupled hover refused: {exc}") from exc
    except (MultiphysicsExecutionError, InvalidScientificProblem) as exc:
        raise TemplateRefusal(f"coupled hover refused: the coupled fixed point was not reached or not admitted ({exc})") from exc
    window = run.windows[0]
    if window.outcome.value != "converged":
        raise TemplateRefusal(f"the coupled fixed point was not reached ({window.outcome.value}); no hover state is reported")
    out = run.final_outputs

    def q(key: str, unit: str) -> Quantity:
        return Quantity(out[key]["magnitude"], unit)

    balances = coupling_balances(out, x)
    duty = q("motor_esc.duty", "dimensionless").magnitude_in("dimensionless")
    if not duty < 1.0:
        raise TemplateRefusal(f"infeasible: the motor needs {q('motor_esc.motor_voltage', 'V').magnitude_in('V'):.4g} V but the bus "
                              f"supplies {q('battery_ecm.bus_voltage', 'V').magnitude_in('V'):.4g} V (duty {duty:.4g} >= 1); "
                              "the declared drone cannot reach hover speed on this pack")
    tw = q("winding_thermal.winding_temperature", "K")
    if tw.magnitude_in("K") > x["winding_temperature_limit"]:
        raise TemplateRefusal(f"the converged winding temperature {tw.magnitude_in('K'):.5g} K exceeds the declared winding_temperature_limit "
                              f"{x['winding_temperature_limit']:.5g} K: outside the linear R(T) model, so no hover state is reported")
    voc, rint = x["battery_open_circuit_voltage"], x["battery_internal_resistance"]
    if voc * voc - 4 * rint * q("motor_esc.bus_power", "W").magnitude_in("W") <= 0:
        raise TemplateRefusal("the converged bus power is at or above the battery's maximum deliverable power; no fixed point exists")
    n_rot = int(x["rotor_count"])
    shaft, speed = q("propeller_static.shaft_power", "W"), q("propeller_static.shaft_speed", "rad/s")
    bus, pack = q("motor_esc.bus_power", "W"), q("battery_ecm.pack_current", "A")
    return {
        "classification": CLASSIFICATION, "model": f"{ADAPTER_ID} v{ADAPTER_VERSION} on MultiphysicsRuntime (implicit, serial)",
        "run_id": run.run_id, "run_digest": canonical_digest(run.to_dict()), "graph_fingerprint": run.graph_fingerprint,
        "plan_fingerprint": run.plan_fingerprint, "iterations": len(window.iterations),
        "shaft_speed": speed, "shaft_torque": Quantity(shaft.magnitude_in("W") / speed.magnitude_in("rad/s"), "N*m"),
        "shaft_power_total": Quantity(n_rot * shaft.magnitude_in("W"), "W"),
        "motor_current": q("motor_esc.motor_current", "A"), "motor_voltage": q("motor_esc.motor_voltage", "V"),
        "duty": Quantity(duty, "dimensionless"), "bus_power": bus, "pack_current": pack, "bus_voltage": q("battery_ecm.bus_voltage", "V"),
        "winding_temperature": tw, "motor_heat": q("motor_esc.motor_heat", "W"), "battery_heat": q("battery_ecm.battery_heat", "W"),
        "rated_capacity_over_current": Quantity(x["battery_capacity"] / pack.magnitude_in("A"), "h"),
        "bus_power_balance_residual": balances["bus_power_balance_residual"],
        "winding_heat_balance_residual": balances["winding_heat_balance_residual"],
        "uncertainty": "UNKNOWN",
        "omitted": OMITTED,
        "notes": ("rated_capacity_over_current is NOT an endurance prediction (no usable-capacity fraction, sag or temperature)",
                  "duty < 1 is a necessary condition at point values only; ESC maximum duty and timing are not modelled",
                  "the balance residuals are diagnostics, not checks and not evidence: the bus residual is the last bus-voltage "
                  "update times the pack current (already bounded by the convergence criterion); the winding residual re-evaluates "
                  "the thermal node's own law and is zero by construction. Neither says whether the models are right"),
        "inputs": {k: template.input(k).source_ref for k in COUPLED_INPUTS},
    }


def coupling_balances(out: Mapping[str, Any], x: Mapping[str, float]) -> dict[str, Quantity]:
    """Cross-participant residuals at the reported state. Diagnostics only: no tolerance, no check, no evidence.

    * bus power: what the battery delivers at its terminals (V_b I_pack) minus what the motors/ESCs draw.
      The motor participant draws ``P_bus / V_b`` with the bus voltage of the previous sweep, so this is
      ``I_pack (V_b,k - V_b,k-1)``: the last bus-voltage update times the current. The coupling's own
      convergence criterion on the bus voltage already bounds it; it adds no independent information.
    * winding heat: the thermal node's temperature minus T_amb + R_th x (the heat the motor produced).
      The thermal participant runs after the motor in the same Gauss-Seidel sweep and computes exactly
      this expression from that heat, so on runtime output it is zero by construction, converged or
      not. It is not an energy balance (its unit is K); only hand-built inputs make it non-zero.

    A balance that could fail independently (shaft power + motor heat + ESC loss = bus power; V_oc I =
    bus power + battery heat) holds algebraically in these participants and is not evaluated; turning
    any of these into a check needs a declared, justified tolerance (an open scientific decision).
    """
    def m(key: str, unit: str) -> float:
        return Quantity(out[key]["magnitude"], unit).magnitude_in(unit)

    bus = m("battery_ecm.bus_voltage", "V") * m("battery_ecm.pack_current", "A") - m("motor_esc.bus_power", "W")
    heat = m("winding_thermal.winding_temperature", "K") - (x["ambient_temperature"] + x["motor_thermal_resistance"] * m("motor_esc.motor_heat", "W"))
    return {"bus_power_balance_residual": Quantity(bus, "W"), "winding_heat_balance_residual": Quantity(heat, "K")}


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CLASSIFICATION", "COUPLED_INPUTS", "build_runtime", "coupled_hover_screening", "coupling_balances"]
