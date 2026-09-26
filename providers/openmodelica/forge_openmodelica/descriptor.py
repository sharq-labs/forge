"""Descriptive registration of the OpenModelica provider (process mode, bounded model family)."""

import os
import re

from engcore.providers import ProviderCapability, executable_probe

CAPABILITY = ProviderCapability(
    "openmodelica", "system_dynamics", "process", "omc", ("lumped_ode_dae_systems",), dimensions=(0,), time_modes=("transient",),
    output_ranks=("series",), dependencies=("omc + a C toolchain (compiles each model)",),
    license="LicenseRef-OSMC-PL (conda-forge openmodelica 1.27.1 metadata)", notes="bounded to a lumped thermal-capacitance family; separate process")


def _version(text: str) -> str:
    m = re.search(r"(?:OpenModelica )?v(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else ""


def register(registry, *, provider_envs: str | None = None, **_):
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    search = os.path.join(envs, "openmodelica", "bin") if envs else None
    registry.register(CAPABILITY, executable_probe(CAPABILITY, "omc", ("--version",), _version, search_path=search,
                                                     environment_prefix=os.path.join(envs, "openmodelica") if envs else None))
