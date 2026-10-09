"""Product compositions (drone, vehicle, motor, HVAC) on ONE generic product-template contract.

Products are compositions, not Core: each module here builds a
:class:`~.template.ProductTemplate` from generic assembly, participant and
input records.  Nothing in Scientific Core or the generic layers knows these
product names.
"""

from .template import (
    AssemblyBuilder, CouplingDeclaration, CouplingStatus, ParticipantCapability, ParticipantReadiness, PhysicsParticipant,
    ProductTemplate, RequiredInput, TemplateRefusal, capability_report,
)
from .drone import drone_template, hover_screening
from .vehicle import vehicle_template
from .motor import motor_template
from .hvac import hvac_template

#: Provider ids implemented inside Forge (not registry adapters), by product template.
IN_REPOSITORY = {
    "gmsh": "engcore.spatial.gmsh_adapter",
    "forge.hover_momentum": "engcore.systems.aerospace.multirotor.rotor_hover",
    "forge.electrical_dc": "engcore.domains.electrical (DC network domain)",
}

TEMPLATES = {"drone": drone_template, "vehicle": vehicle_template, "motor": motor_template, "hvac": hvac_template}

__all__ = [
    "AssemblyBuilder", "CouplingDeclaration", "CouplingStatus", "IN_REPOSITORY", "ParticipantCapability", "ParticipantReadiness",
    "PhysicsParticipant", "ProductTemplate", "RequiredInput", "TEMPLATES", "TemplateRefusal", "capability_report", "drone_template",
    "hover_screening", "hvac_template", "motor_template", "vehicle_template",
]
