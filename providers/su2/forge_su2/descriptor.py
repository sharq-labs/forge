"""Descriptive registration of the SU2 provider (process mode, bounded case family)."""

import os
import re

from engcore.providers import ProviderCapability, executable_probe

CAPABILITY = ProviderCapability(
    "su2", "cfd", "process", "SU2_CFD", ("incompressible_laminar_navier_stokes",), dimensions=(2,),
    time_modes=("steady",), output_ranks=("vector", "scalar"), mesh_requirement="Forge-generated native .su2 quad mesh (cavity family only)",
    property_forms=("density and dynamic viscosity with provenance",), restart=True, checkpoint=False, parallel="MPI (not used)",
    dependencies=("SU2_CFD executable",), license="GPL-2.0-or-later (conda-forge su2 8.5.0 metadata; upstream SU2 source is LGPL-2.1)", notes="bounded to the 2-D lid-driven cavity; separate process")


def _version(text: str) -> str:
    m = re.search(r"SU2 v(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else ""


def register(registry, *, provider_envs: str | None = None, **_):
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    search = os.path.join(envs, "su2", "bin") if envs else None
    registry.register(CAPABILITY, executable_probe(CAPABILITY, "SU2_CFD", ("--help",), _version, search_path=search,
                                                     environment_prefix=os.path.join(envs, "su2") if envs else None))
