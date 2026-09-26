"""Descriptive registration of the PyBaMM provider (capability, not applicability)."""

from engcore.providers import ProviderCapability, python_package_probe

CAPABILITY = ProviderCapability(
    "pybamm", "battery", "library", "pybamm", ("lithium_ion_electrochemistry", "lumped_cell_thermal"), dimensions=(0, 1),
    time_modes=("transient",), output_ranks=("scalar", "series"),
    property_forms=("PyBaMM-bundled literature parameter set chosen by name, content-digested",),
    restart=True, checkpoint=False, parallel="serial", dependencies=("pybamm", "casadi", "pybammsolvers"), license="BSD-3-Clause",
    notes="model families SPM / SPMe / DFN; parameter sets are provider-bundled literature data, not Forge-sourced data")


def register(registry, **_):
    registry.register(CAPABILITY, python_package_probe(CAPABILITY, "pybamm", ("pybamm", "PyBaMM"), dependencies=("casadi", "pybammsolvers")))
