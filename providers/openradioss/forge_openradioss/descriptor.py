"""Descriptive registration of the OpenRadioss provider (process mode: starter, engine, th_to_csv).

The three executables are registered separately so a partial install is visible
as exactly which piece is missing.  OpenRadioss executables are located under
``$OPENRADIOSS_HOME/exec`` (or ``FORGE_PROVIDER_ENVS/openradioss/exec``); the
version argument and its exit code are UNVERIFIED until measured against a
real install, and a probe that does not answer as declared is UNAVAILABLE.
"""

import os
import re

from engcore.providers import ProviderCapability, executable_probe

_COMMON = dict(dimensions=(3,), time_modes=("transient",), output_ranks=("series",),
               mesh_requirement="Forge linear-tetrahedron SpatialMesh -> /TETRA4 deck", restart=False, checkpoint=False,
               parallel="serial (-np 1)", license="AGPL-3.0", notes="bounded explicit impact case; translation unverified until a real run")
STARTER = ProviderCapability("openradioss_starter", "explicit_dynamics", "process", "starter_linux64_gf", ("explicit_impact_preprocessing",), **_COMMON)
ENGINE = ProviderCapability("openradioss", "explicit_dynamics", "process", "engine_linux64_gf", ("explicit_dynamics", "elastic_plastic_impact"), **_COMMON)
TH_TO_CSV = ProviderCapability("openradioss_th_to_csv", "explicit_dynamics", "process", "th_to_csv_linux64_gf", ("time_history_export",), **_COMMON)


def _version(text: str) -> str:
    m = re.search(r"OpenRadioss[^\n]*?(\d{4}(?:\.\d+)*|\d+\.\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    return m.group(1) if m else ""


def _search(provider_envs: str | None) -> str | None:
    home = os.environ.get("OPENRADIOSS_HOME", "")
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    if home:
        return os.path.join(home, "exec")
    return os.path.join(envs, "openradioss", "exec") if envs else None


def register(registry, *, provider_envs: str | None = None, **_):
    search = _search(provider_envs)
    for cap in (STARTER, ENGINE, TH_TO_CSV):
        registry.register(cap, executable_probe(cap, cap.package, ("-version",), _version, search_path=search))
