"""Descriptive registration of the OpenFOAM provider (process mode, bounded case family)."""

import os
import re
import subprocess

from engcore.providers import Availability, ProviderCapability, ProviderStatus
from engcore.providers.catalog import _sha256_file

CAPABILITY = ProviderCapability(
    "openfoam", "cfd", "process", "icoFoam", ("incompressible_laminar_navier_stokes",), dimensions=(2,),
    time_modes=("transient",), output_ranks=("vector", "scalar"), mesh_requirement="Forge-generated blockMesh (cavity family only)",
    property_forms=("kinematic viscosity with provenance",), restart=True, checkpoint=False, parallel="MPI (not used)",
    dependencies=("OpenFOAM (openfoam.com) executables",), license="GPL-3.0-only (conda-forge openfoam 2412 metadata)",
    notes="bounded to the 2-D lid-driven cavity; separate process; not arbitrary CFD support")


def register(registry, *, provider_envs: str | None = None, **_):
    envs = provider_envs or os.environ.get("FORGE_PROVIDER_ENVS", "")
    prefix = os.path.join(envs, "openfoam") if envs else ""

    def probe() -> ProviderStatus:
        exe = os.path.join(prefix, "bin", "icoFoam")
        if not prefix or not os.path.isfile(exe):
            return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="OpenFOAM icoFoam not found under the provider prefix")
        from . import openfoam_environment
        try:
            out = subprocess.run([os.path.realpath(exe), "-help"], capture_output=True, text=True, timeout=60,
                                 env=openfoam_environment(prefix))
            m = re.search(r"OpenFOAM-(v?\d+)", out.stdout + out.stderr)
        except Exception as exc:
            return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason=f"{type(exc).__name__}: {exc}")
        if not m:
            return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="could not establish the OpenFOAM version")
        from engcore.providers.catalog import _combine, conda_environment_digest
        env_digest, count = conda_environment_digest(prefix)
        file_digest = _sha256_file(os.path.realpath(exe))
        return ProviderStatus(CAPABILITY, Availability.AVAILABLE, m.group(1), _combine(file_digest, env_digest),
                              os.path.realpath(exe), dependencies=(("conda-environment", f"{count} packages", env_digest),),
                              executable_digest=file_digest)

    registry.register(CAPABILITY, probe)
