"""Drone (multirotor) product composition on the generic product-template contract.

Product structure (generic levels; nothing drone-specific enters Core)::

    drone (system)
    |- airframe (subsystem) -- frame (assembly) -- hub (part), arm_1..N (part)
    |- propulsion (subsystem) -- unit_i (assembly) -- motor_i, propeller_i, esc_i (components)
    |- power (subsystem) -- battery, harness (components)
    `- payload (component)

Physics participants name candidate providers by registry id; the capability
report says which can run here.  Every physical input (mass, rotor diameter,
air density, gravity, motor and battery data) is a RequiredInput that stays
UNKNOWN until declared with a source -- there are no hidden drone defaults.

Bounded executable path: :func:`hover_screening`, the ideal actuator-disk
momentum relation already in ``systems.aerospace.multirotor``.  It is an
idealised LOWER BOUND on induced power (no profile drag, no interference, no
motor/ESC losses), not a performance prediction and not validated.
"""

from __future__ import annotations

import math
from typing import Any

from ...scientific.units.quantity import Quantity
from ...spatial.geometry import Transform
from ..aerospace.multirotor.rotor_hover import disk_loading, ideal_induced_hover_power
from ..assembly import InterfaceDeclaration, InterfaceKind, JointDeclaration, JointKind
from .template import AssemblyBuilder, CouplingDeclaration, PhysicsParticipant, ProductTemplate, TemplateRefusal, inputs



def drone_template(rotor_count: int = 4, arm_length: Quantity | None = None) -> ProductTemplate:
    """Structure for ``rotor_count`` propulsion units.  Arm placements exist only if ``arm_length`` is declared."""
    if isinstance(rotor_count, bool) or not isinstance(rotor_count, int) or rotor_count < 3:
        raise TemplateRefusal("a multirotor template needs an integer rotor count >= 3")
    b = AssemblyBuilder("drone")
    b.add("drone", "drone", "system")
    # by DEFINITION the product frame is the hub frame: these identity placements are the frame convention, not a measurement
    origin = Transform() if arm_length is not None else None
    b.add("airframe", "airframe", "subsystem", "drone", origin).add("frame", "frame", "assembly", "airframe", origin)
    b.add("hub", "hub", "part", "frame", origin)
    b.add("propulsion", "propulsion", "subsystem", "drone")
    b.add("power", "power", "subsystem", "drone").add("battery", "battery", "component", "power").add("harness", "harness", "component", "power")
    b.add("payload", "payload", "component", "drone")
    b.point("hub.center", "hub").point("battery.terminals", "battery")
    for i in range(1, rotor_count + 1):
        angle = 2 * math.pi * (i - 1) / rotor_count
        arm_place = None
        if arm_length is not None:
            arm_place = Transform.from_quantities(axis=(0, 0, 1), angle=Quantity(math.degrees(angle), "degree"))
        b.add(f"arm_{i}", "arm", "part", "frame", arm_place)
        b.add(f"unit_{i}", "propulsion_unit", "assembly", "propulsion")
        for part in ("motor", "propeller", "esc"):
            b.add(f"{part}_{i}", part, "component", f"unit_{i}")
        b.point(f"arm_{i}.root", f"arm_{i}").point(f"arm_{i}.tip", f"arm_{i}", Transform.from_quantities((arm_length, Quantity(0, "m"), Quantity(0, "m")))
                                                    if arm_length is not None else None)
        b.point(f"motor_{i}.mount", f"motor_{i}").point(f"motor_{i}.shaft", f"motor_{i}").point(f"propeller_{i}.hub", f"propeller_{i}")
        b.point(f"esc_{i}.dc", f"esc_{i}").point(f"esc_{i}.phase", f"esc_{i}")
        b.joint(JointDeclaration(f"arm_{i}_root", JointKind.FIXED, "hub.center", f"arm_{i}.root"))
        b.joint(JointDeclaration(f"motor_{i}_mount", JointKind.FIXED, f"arm_{i}.tip", f"motor_{i}.mount"))
        b.joint(JointDeclaration(f"rotor_{i}", JointKind.REVOLUTE, f"motor_{i}.shaft", f"propeller_{i}.hub", axis=(0.0, 0.0, 1.0)))
        b.interface(InterfaceDeclaration(f"dc_{i}", InterfaceKind.ELECTRICAL, "battery.terminals", f"esc_{i}.dc"))
        b.interface(InterfaceDeclaration(f"phase_{i}", InterfaceKind.ELECTRICAL, f"esc_{i}.phase", f"motor_{i}.mount"))
        b.interface(InterfaceDeclaration(f"motor_heat_{i}", InterfaceKind.THERMAL, f"motor_{i}.mount", f"arm_{i}.tip"))
    units = tuple(f"unit_{i}" for i in range(1, rotor_count + 1))
    req = inputs((
        ("takeoff_mass", "drone", "kg", "all-up mass in the hover case"),
        ("rotor_diameter", "propulsion", "m", "propeller diameter (all units identical)"),
        ("rotor_count", "propulsion", "dimensionless", "number of propulsion units"),
        ("air_density", "drone", "kg/m^3", "ambient air density of the scenario (environment record)"),
        ("gravity", "drone", "m/s^2", "gravitational acceleration of the scenario (environment record)"),
        ("arm_length", "frame", "m", "hub centre to motor axis"),
        ("battery_capacity", "battery", "A*h", "rated capacity"),
        ("battery_voltage", "battery", "V", "nominal pack voltage"),
        ("motor_kv", "propulsion", "rpm/V", "motor velocity constant"),
        ("motor_resistance", "propulsion", "ohm", "phase-to-phase winding resistance"),
    ))
    participants = (
        PhysicsParticipant("geometry", "parametric_aerospace_geometry", ("airframe",), ("openvsp",), ("arm_length",)),
        PhysicsParticipant("meshing", "mesh_generation", ("airframe",), ("gmsh",), ()),
        PhysicsParticipant("hover_screening", "actuator_disk_hover", ("propulsion",), ("forge.hover_momentum",),
                           ("takeoff_mass", "rotor_diameter", "rotor_count", "air_density", "gravity"),
                           "ideal momentum theory: an induced-power lower bound"),
        PhysicsParticipant("rotor_aerodynamics", "rotor_cfd", units, ("su2", "openfoam")),
        PhysicsParticipant("frame_structure", "linear_elasticity", ("frame",), ("calculix", "code_aster", "fenicsx"), ("arm_length",)),
        PhysicsParticipant("battery", "lithium_ion_electrochemistry", ("battery",), ("pybamm",), ("battery_capacity", "battery_voltage")),
        PhysicsParticipant("electrical", "dc_network", ("power", "propulsion"), ("forge.electrical_dc",), ("battery_voltage", "motor_resistance")),
        PhysicsParticipant("thermal", "transient_conduction", units, ("fenicsx",)),
        PhysicsParticipant("multibody", "rigid_multibody_dynamics", ("drone",), ("chrono",), ("takeoff_mass",)),
    )
    couplings = (CouplingDeclaration("hover_screening", "electrical", "shaft_power"),
                 CouplingDeclaration("electrical", "battery", "pack_current"),
                 CouplingDeclaration("electrical", "thermal", "winding_losses"),
                 CouplingDeclaration("rotor_aerodynamics", "frame_structure", "rotor_loads"))
    return ProductTemplate("drone", "1", b.build(), participants, req, couplings,
                           ("composition and bounded hover screening only; coupled execution is not claimed",))


def hover_screening(template: ProductTemplate) -> dict[str, Any]:
    """Ideal induced hover power from DECLARED inputs.  Refuses while any of them is UNKNOWN."""
    v = template.values("takeoff_mass", "rotor_diameter", "rotor_count", "air_density", "gravity")
    count = v["rotor_count"].magnitude_in("dimensionless")
    if count != int(count) or count < 3:
        raise TemplateRefusal("rotor_count must be an integer >= 3")
    thrust = Quantity(v["takeoff_mass"].magnitude_in("kg") * v["gravity"].magnitude_in("m/s^2"), "N")
    area = Quantity(count * math.pi * (v["rotor_diameter"].magnitude_in("m") / 2) ** 2, "m^2")
    power = ideal_induced_hover_power(thrust=thrust, disk_area=area, air_density=v["air_density"])
    return {"classification": "ideal_momentum_theory_lower_bound_not_validated", "model": "forge.hover_momentum (actuator disk)",
            "thrust": thrust, "disk_area": area, "disk_loading": disk_loading(thrust=thrust, disk_area=area), "ideal_induced_power": power,
            "uncertainty": "UNKNOWN", "omitted": ("profile power", "rotor interference", "motor and ESC losses", "non-uniform inflow"),
            "inputs": {k: template.input(k).source_ref for k in v}}
