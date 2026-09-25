"""Descriptive registration of the Cantera provider (capability, not applicability)."""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "cantera", "chemistry", "library", "cantera",
    ("thermodynamic_equilibrium", "gas_phase_kinetics", "zero_dimensional_reactors"), dimensions=(0,),
    time_modes=("steady", "transient"), output_ranks=("scalar", "series"),
    property_forms=("mechanism file (YAML) bound by sha256",), dependencies=("cantera",), license="BSD-3-Clause",
    notes="a mechanism's validity is its authors' statement, not a Forge claim")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "cantera", ("cantera", "Cantera")))
