"""Descriptive registration of the OpenVSP provider (library mode, the ``openvsp`` Python API)."""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "openvsp", "geometry", "library", "openvsp", ("parametric_aerospace_geometry",), dimensions=(3,),
    time_modes=(), output_ranks=("geometry",), mesh_requirement="none (exports STEP for the Gmsh adapter)",
    property_forms=(), restart=False, checkpoint=False, parallel="serial", dependencies=("openvsp Python API",),
    license="NOSA-1.3", notes="fuselage/pod (POD), wing/tail (WING) by canonical parameters; translation unverified until a real run")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "openvsp", ("openvsp", "OpenVSP")))
