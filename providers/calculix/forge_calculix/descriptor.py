"""Descriptive registration of the CalculiX provider (process mode)."""

import os
import re

from engcore.providers import ProviderCapability, executable_probe

CAPABILITY = ProviderCapability(
    "calculix", "structural", "process", "ccx", ("linear_elasticity", "static_structural"), dimensions=(2, 3),
    time_modes=("steady",), output_ranks=("vector", "tensor"), mesh_requirement="Forge triangle mesh -> CPS3 deck",
    property_forms=("isotropic elastic per region from BIG 5 resolved properties",), restart=False, checkpoint=False,
    parallel="shared-memory threads (not used)", dependencies=("ccx executable",), license="GPL-2.0-or-later (conda-forge calculix 2.23 metadata)",
    notes="run as a separate process; Forge does not link CalculiX")


def _version(text: str) -> str:
    m = re.search(r"Version\s+(\d+\.\d+)", text)
    return m.group(1) if m else ""


def register(registry, *, provider_envs: str | None = None, **_):
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    search = os.path.join(envs, "calculix", "bin") if envs else None
    registry.register(CAPABILITY, executable_probe(CAPABILITY, "ccx", ("-v",), _version, search_path=search,
                                                     environment_prefix=os.path.join(envs, "calculix") if envs else None))
