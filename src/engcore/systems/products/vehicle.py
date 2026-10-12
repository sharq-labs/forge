"""Road vehicle composition, built from the SAME generic contracts as every other product.

    vehicle (system)
    |- body (subsystem) -- body_structure (assembly), closures (component)
    |- chassis (subsystem) -- corner_fl/fr/rl/rr (assembly) -- spring, damper, wheel (components)
    |- powertrain (subsystem) -- drive_motor, inverter (components), battery_pack (assembly)
    `- thermal_system (subsystem) -- coolant_loop, radiator (components)

The first pass composes the system and exposes capability honestly: crash
(OpenRadioss), suspension multibody (Chrono), aerodynamics (SU2/OpenFOAM),
structure (CalculiX/Code_Aster/FEniCSx), battery (PyBaMM), thermal
(FEniCSx/TESPy) and energy use (OpenModelica) each name their providers;
electromagnetic motor physics has NO adapter yet and says so.  No executable
vehicle-level path is claimed.
"""

from __future__ import annotations

from ..assembly import InterfaceDeclaration, InterfaceKind, JointDeclaration, JointKind
from .template import AssemblyBuilder, CouplingDeclaration, PhysicsParticipant, ProductTemplate, inputs

CORNERS = ("fl", "fr", "rl", "rr")


def vehicle_template() -> ProductTemplate:
    b = AssemblyBuilder("vehicle")
    b.add("vehicle", "vehicle", "system")
    b.add("body", "body", "subsystem", "vehicle").add("body_structure", "body_structure", "assembly", "body")
    b.add("closures", "closures", "component", "body")
    b.add("chassis", "chassis", "subsystem", "vehicle")
    b.point("body_structure.battery_mount", "body_structure")
    for c in CORNERS:
        b.add(f"corner_{c}", "corner", "assembly", "chassis")
        for part in ("knuckle", "spring", "damper", "wheel"):
            b.add(f"{part}_{c}", part, "component", f"corner_{c}")
        b.point(f"body_structure.strut_{c}", "body_structure").point(f"knuckle_{c}.strut", f"knuckle_{c}")
        b.point(f"knuckle_{c}.spindle", f"knuckle_{c}").point(f"wheel_{c}.hub", f"wheel_{c}")
        b.point(f"spring_{c}.top", f"spring_{c}").point(f"damper_{c}.top", f"damper_{c}")
        b.joint(JointDeclaration(f"strut_{c}", JointKind.PRISMATIC, f"body_structure.strut_{c}", f"knuckle_{c}.strut", axis=(0.0, 0.0, 1.0)))
        b.joint(JointDeclaration(f"spindle_{c}", JointKind.REVOLUTE, f"knuckle_{c}.spindle", f"wheel_{c}.hub", axis=(0.0, 1.0, 0.0)))
        b.interface(InterfaceDeclaration(f"spring_load_{c}", InterfaceKind.MECHANICAL, f"spring_{c}.top", f"body_structure.strut_{c}"))
        b.interface(InterfaceDeclaration(f"damper_load_{c}", InterfaceKind.MECHANICAL, f"damper_{c}.top", f"body_structure.strut_{c}"))
    b.add("powertrain", "powertrain", "subsystem", "vehicle")
    b.add("drive_motor", "drive_motor", "component", "powertrain").add("inverter", "inverter", "component", "powertrain")
    b.add("battery_pack", "battery_pack", "assembly", "powertrain")
    b.add("thermal_system", "thermal_system", "subsystem", "vehicle")
    b.add("coolant_loop", "coolant_loop", "component", "thermal_system").add("radiator", "radiator", "component", "thermal_system")
    b.point("battery_pack.terminals", "battery_pack").point("battery_pack.mount", "battery_pack").point("inverter.dc", "inverter")
    b.point("inverter.ac", "inverter").point("drive_motor.phases", "drive_motor").point("coolant_loop.pack", "coolant_loop")
    b.interface(InterfaceDeclaration("hv_dc", InterfaceKind.ELECTRICAL, "battery_pack.terminals", "inverter.dc"))
    b.interface(InterfaceDeclaration("motor_ac", InterfaceKind.ELECTRICAL, "inverter.ac", "drive_motor.phases"))
    b.interface(InterfaceDeclaration("pack_cooling", InterfaceKind.THERMAL, "battery_pack.mount", "coolant_loop.pack"))
    b.interface(InterfaceDeclaration("pack_mount", InterfaceKind.MECHANICAL, "battery_pack.mount", "body_structure.battery_mount"))
    req = inputs((
        ("curb_mass", "vehicle", "kg", "vehicle mass in the load case"),
        ("frontal_area", "body", "m^2", "projected frontal area"),
        ("wheelbase", "chassis", "m", "axle spacing"),
        ("track_width", "chassis", "m", "wheel centre spacing"),
        ("spring_rate", "chassis", "N/m", "corner spring rate (identical corners)"),
        ("damping_coefficient", "chassis", "N*s/m", "corner damper coefficient (linearised)"),
        ("impact_speed", "vehicle", "m/s", "crash load-case speed"),
        ("pack_capacity", "battery_pack", "A*h", "rated pack capacity"),
        ("pack_voltage", "battery_pack", "V", "nominal pack voltage"),
        ("ambient_temperature", "vehicle", "K", "scenario ambient (environment record)"),
    ))
    corners = tuple(f"corner_{c}" for c in CORNERS)
    participants = (
        PhysicsParticipant("body_meshing", "mesh_generation", ("body_structure",), ("gmsh",)),
        PhysicsParticipant("aerodynamics", "external_cfd", ("body",), ("su2", "openfoam"), ("frontal_area",)),
        PhysicsParticipant("body_stiffness", "linear_elasticity", ("body_structure",), ("calculix", "code_aster", "fenicsx")),
        PhysicsParticipant("crash", "explicit_impact", ("body_structure",), ("openradioss",), ("curb_mass", "impact_speed")),
        PhysicsParticipant("suspension", "rigid_multibody_dynamics", corners, ("chrono",),
                           ("curb_mass", "wheelbase", "track_width", "spring_rate", "damping_coefficient"),
                           "springs and dampers need force elements the Chrono adapter does not translate yet"),
        PhysicsParticipant("drive_motor_em", "electromagnetics", ("drive_motor",), (), (), "no electromagnetic adapter exists in Forge"),
        PhysicsParticipant("battery", "lithium_ion_electrochemistry", ("battery_pack",), ("pybamm",), ("pack_capacity", "pack_voltage")),
        PhysicsParticipant("thermal", "cooling_network", ("thermal_system", "battery_pack"), ("tespy", "fenicsx"), ("ambient_temperature",)),
        PhysicsParticipant("energy_use", "system_dynamics", ("vehicle",), ("openmodelica",), ("curb_mass", "frontal_area")),
    )
    couplings = (CouplingDeclaration("aerodynamics", "energy_use", "drag_force"), CouplingDeclaration("battery", "thermal", "heat_generation"),
                 CouplingDeclaration("suspension", "body_stiffness", "strut_loads"), CouplingDeclaration("drive_motor_em", "energy_use", "torque_map"))
    return ProductTemplate("vehicle", "1", b.build(), participants, req, couplings,
                           ("first-pass composition: capability gaps are reported, no coupled vehicle run is claimed",))
