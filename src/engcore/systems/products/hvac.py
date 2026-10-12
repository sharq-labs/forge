"""HVAC composition on the generic product-template contract.

    hvac (system)
    |- refrigerant_circuit (subsystem) -- compressor, condenser, expansion_valve, evaporator (components)
    |- air_side (subsystem) -- fan, duct (components)
    `- controls (component)

Thermodynamic state (CoolProp), the cycle/fluid network and heat exchangers
(TESPy), airflow (OpenFOAM/SU2) and controls (OpenModelica) name their
providers; the building/environment load has no adapter and is an input.
"""

from __future__ import annotations

from ..assembly import InterfaceDeclaration, InterfaceKind
from .template import AssemblyBuilder, CouplingDeclaration, PhysicsParticipant, ProductTemplate, inputs


def hvac_template() -> ProductTemplate:
    b = AssemblyBuilder("hvac")
    b.add("hvac", "hvac", "system")
    b.add("refrigerant_circuit", "refrigerant_circuit", "subsystem", "hvac")
    for c in ("compressor", "condenser", "expansion_valve", "evaporator"):
        b.add(c, c, "component", "refrigerant_circuit").point(f"{c}.inlet", c).point(f"{c}.outlet", c)
    b.add("air_side", "air_side", "subsystem", "hvac").add("fan", "fan", "component", "air_side").add("duct", "duct", "component", "air_side")
    b.add("controls", "controls", "component", "hvac")
    for a, c in (("compressor", "condenser"), ("condenser", "expansion_valve"), ("expansion_valve", "evaporator"), ("evaporator", "compressor")):
        b.interface(InterfaceDeclaration(f"{a}_to_{c}", InterfaceKind.FLUID, f"{a}.outlet", f"{c}.inlet"))
    b.point("fan.outlet", "fan").point("duct.inlet", "duct").point("duct.coil", "duct").point("controls.signals", "controls")
    b.interface(InterfaceDeclaration("fan_to_duct", InterfaceKind.FLUID, "fan.outlet", "duct.inlet"))
    b.interface(InterfaceDeclaration("coil_air", InterfaceKind.THERMAL, "duct.coil", "evaporator.outlet"))
    b.interface(InterfaceDeclaration("compressor_control", InterfaceKind.SIGNAL, "controls.signals", "compressor.inlet"))
    req = inputs((
        ("cooling_load", "hvac", "W", "required cooling capacity (building/environment load record)"),
        ("ambient_temperature", "hvac", "K", "outdoor dry-bulb (environment record)"),
        ("room_setpoint", "controls", "K", "indoor setpoint"),
        ("compressor_displacement", "compressor", "m^3", "swept volume per revolution"),
        ("compressor_speed", "compressor", "rpm", "operating speed"),
        ("air_flow_rate", "fan", "m^3/s", "air-side volume flow"),
        ("condenser_ua", "condenser", "W/K", "overall conductance"),
        ("evaporator_ua", "evaporator", "W/K", "overall conductance"),
    ))
    participants = (
        PhysicsParticipant("fluid_properties", "thermophysical_properties", ("refrigerant_circuit",), ("coolprop",)),
        PhysicsParticipant("cycle", "thermodynamic_cycle_network", ("refrigerant_circuit",), ("tespy",),
                           ("cooling_load", "ambient_temperature", "compressor_displacement", "compressor_speed", "condenser_ua", "evaporator_ua")),
        PhysicsParticipant("airflow", "internal_cfd", ("air_side",), ("openfoam", "su2"), ("air_flow_rate",)),
        PhysicsParticipant("controls", "control_system", ("controls",), ("openmodelica",), ("room_setpoint",)),
        PhysicsParticipant("building_load", "building_energy", ("hvac",), (), ("ambient_temperature",), "no building-energy adapter; the load is an input"),
    )
    couplings = (CouplingDeclaration("fluid_properties", "cycle", "refrigerant_state"),
                 CouplingDeclaration("airflow", "cycle", "evaporator_air_state"), CouplingDeclaration("controls", "cycle", "compressor_speed"))
    return ProductTemplate("hvac", "1", b.build(), participants, req, couplings, ("composition only; no coupled HVAC run is claimed",))
