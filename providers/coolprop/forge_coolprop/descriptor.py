"""Descriptive registration of the CoolProp provider (capability, not applicability)."""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "coolprop", "thermophysical", "library", "CoolProp",
    ("fluid_equation_of_state", "fluid_transport_properties"), time_modes=("steady",), output_ranks=("scalar",),
    property_forms=("fluid_state(two independent intensive variables)",), dependencies=("CoolProp",),
    license="MIT (CoolProp); fluid EOS references per fluid",
    notes="computed properties from reference equations of state; not measurement evidence")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "CoolProp", ("CoolProp", "coolprop")))
