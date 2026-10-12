"""Electric motor composition on the generic product-template contract.

    motor (system)
    |- stator (assembly) -- core (part), winding (component)
    |- rotor (assembly) -- shaft (part), magnets (component)
    |- housing (part)
    |- bearings (component)
    `- controller (component)          control interface

Electromagnetics has an explicit provider boundary with NO adapter yet; losses
likewise.  Electrical (in-repository DC domain), mechanical torque/inertia
(Chrono), thermal (FEniCSx) and control (OpenModelica) name their providers.
"""

from __future__ import annotations

from ..assembly import InterfaceDeclaration, InterfaceKind, JointDeclaration, JointKind
from .template import AssemblyBuilder, CouplingDeclaration, PhysicsParticipant, ProductTemplate, inputs



def motor_template() -> ProductTemplate:
    b = AssemblyBuilder("motor")
    b.add("motor", "motor", "system")
    b.add("stator", "stator", "assembly", "motor").add("core", "core", "part", "stator").add("winding", "winding", "component", "stator")
    b.add("rotor", "rotor", "assembly", "motor").add("shaft", "shaft", "part", "rotor").add("magnets", "magnets", "component", "rotor")
    b.add("housing", "housing", "part", "motor").add("bearings", "bearings", "component", "motor")
    b.add("controller", "controller", "component", "motor")
    b.point("housing.bore", "housing").point("shaft.journal", "shaft").point("winding.terminals", "winding").point("winding.slot", "winding")
    b.point("core.slot", "core").point("housing.inner", "housing").point("core.outer", "core").point("controller.phases", "controller")
    b.joint(JointDeclaration("rotor_spin", JointKind.REVOLUTE, "housing.bore", "shaft.journal", axis=(0.0, 0.0, 1.0)))
    b.interface(InterfaceDeclaration("phase_leads", InterfaceKind.ELECTRICAL, "controller.phases", "winding.terminals"))
    b.interface(InterfaceDeclaration("slot_heat", InterfaceKind.THERMAL, "winding.slot", "core.slot"))
    b.interface(InterfaceDeclaration("core_to_housing", InterfaceKind.THERMAL, "core.outer", "housing.inner"))
    req = inputs((
        ("phase_resistance", "winding", "ohm", "phase resistance at the reference temperature"),
        ("torque_constant", "motor", "N*m/A", "torque per ampere"),
        ("rotor_inertia", "rotor", "kg*m^2", "rotor polar inertia"),
        ("pole_pairs", "rotor", "dimensionless", "number of pole pairs"),
        ("stack_length", "stator", "m", "active length"),
        ("winding_temperature_limit", "winding", "K", "insulation class limit (component rating record)"),
        ("ambient_temperature", "motor", "K", "scenario ambient (environment record)"),
    ))
    participants = (
        PhysicsParticipant("electrical", "dc_network", ("winding", "controller"), ("forge.electrical_dc",), ("phase_resistance",)),
        PhysicsParticipant("electromagnetics", "electromagnetics", ("stator", "rotor"), (), ("pole_pairs", "stack_length"),
                           "provider boundary declared; no electromagnetic adapter exists in Forge"),
        PhysicsParticipant("mechanical", "rigid_multibody_dynamics", ("rotor",), ("chrono",), ("rotor_inertia", "torque_constant")),
        PhysicsParticipant("losses", "loss_model", ("stator", "rotor"), (), ("phase_resistance",), "no loss-model adapter; copper/iron losses not computed"),
        PhysicsParticipant("thermal", "transient_conduction", ("stator", "housing"), ("fenicsx",), ("ambient_temperature", "winding_temperature_limit")),
        PhysicsParticipant("control", "control_system", ("controller",), ("openmodelica",)),
    )
    couplings = (CouplingDeclaration("electrical", "electromagnetics", "phase_current"), CouplingDeclaration("electromagnetics", "mechanical", "torque"),
                 CouplingDeclaration("losses", "thermal", "heat_sources"), CouplingDeclaration("thermal", "electrical", "winding_temperature"))
    return ProductTemplate("motor", "1", b.build(), participants, req, couplings,
                           ("composition only; burnout/limit statements need the thermal model, the component rating and evidence",))
