"""Descriptive registration of the Code_Aster provider (process mode)."""

import os
import re

from engcore.providers import ProviderCapability, executable_probe

CAPABILITY = ProviderCapability(
    "code_aster", "structural", "process", "run_aster", ("linear_elasticity", "static_structural"), dimensions=(2, 3),
    time_modes=("steady",), output_ranks=("vector",), mesh_requirement="Forge triangle mesh -> ASTER-format TRIA3 mesh",
    property_forms=("isotropic elastic per region from BIG 5 resolved properties",), dependencies=("run_aster (code_aster)",),
    license="GPL-3.0-only AND CECILL-C AND Apache-2.0 AND LGPL-3.0-only (conda-forge code-aster 18.1.7 metadata)", notes="separate process; displacement only in this adapter")


def _version(text: str) -> str:
    m = re.search(r"code_aster\s+(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else ""


def register(registry, *, provider_envs: str | None = None, **_):
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    search = os.path.join(envs, "code_aster", "bin") if envs else None
    registry.register(CAPABILITY, executable_probe(CAPABILITY, "run_aster", ("--version",), _version, search_path=search,
                                                     environment_prefix=os.path.join(envs, "code_aster") if envs else None))
