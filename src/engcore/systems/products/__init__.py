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
from .drone_coupled import coupled_hover_screening
from .vehicle import vehicle_template
from .motor import motor_template
from .hvac import hvac_template

def _pure_python(module: str):
    def probe() -> tuple[bool, str]:
        import importlib

        importlib.import_module(module)
        return True, f"{module} (pure Python, imported)"
    return probe


def _gmsh_probe() -> tuple[bool, str]:
    from ...spatial.providers import gmsh_available

    return gmsh_available()


#: Provider ids implemented inside Forge (not registry adapters) -> availability probe.  Runnable only if the probe passes.
IN_REPOSITORY = {
    "gmsh": _gmsh_probe,
    "forge.hover_momentum": _pure_python("engcore.systems.aerospace.multirotor.rotor_hover"),
    "forge.electrical_dc": _pure_python("engcore.domains.electrical"),
    "forge.drone_coupled_hover": _pure_python("engcore.systems.products.drone_coupled"),
}

TEMPLATES = {"drone": drone_template, "vehicle": vehicle_template, "motor": motor_template, "hvac": hvac_template}

__all__ = [
    "AssemblyBuilder", "CouplingDeclaration", "CouplingStatus", "IN_REPOSITORY", "ParticipantCapability", "ParticipantReadiness",
    "PhysicsParticipant", "ProductTemplate", "RequiredInput", "TEMPLATES", "TemplateRefusal", "capability_report", "coupled_hover_screening", "drone_template",
    "hover_screening", "hvac_template", "motor_template", "vehicle_template",
]
