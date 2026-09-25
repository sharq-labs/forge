"""Descriptive registration of the TESPy provider (capability, not applicability)."""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "tespy", "thermal_system", "library", "tespy", ("steady_thermal_fluid_networks",), dimensions=(0,),
    time_modes=("steady",), output_ranks=("scalar",), property_forms=("fluid via CoolProp inside TESPy",),
    dependencies=("tespy", "CoolProp"), license="MIT",
    notes="network topology is provider-specific; mapped to Forge ComponentConnection records; not independent of CoolProp")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "tespy", ("tespy", "TESPy"), dependencies=("CoolProp",)))
