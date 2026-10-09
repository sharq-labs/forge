"""Descriptive registration of the Project Chrono provider (library mode).

The probe binds the installed distribution like every library provider AND
checks API identity: a module importable as ``pychrono`` that does not expose
Project Chrono's system and version API is refused as BROKEN.  This is not
hypothetical -- the PyPI package named ``pychrono`` is an unrelated timing
library, so "importable" proves nothing about which code would run.
"""

from engcore.providers import Availability, ProviderCapability, ProviderStatus, python_package_probe

CAPABILITY = ProviderCapability(
    "chrono", "multibody", "library", "pychrono", ("rigid_multibody_dynamics",), dimensions=(3,),
    time_modes=("transient",), output_ranks=("series",), mesh_requirement="none (rigid bodies with declared mass properties)",
    property_forms=("mass, centre of mass and inertia per body from declared sources",), restart=False, checkpoint=False,
    parallel="serial", dependencies=("pychrono (conda-forge projectchrono)",), license="BSD-3-Clause",
    notes="supported API major version 9; fixed, revolute, prismatic and spherical joints; translation unverified until a real run")

#: Project Chrono API symbols whose presence identifies the library (not a same-named package).
IDENTITY_SYMBOLS = ("ChSystemNSC", "ChBody", "ChLinkLockRevolute", "GetChronoVersion")
SUPPORTED_MAJOR = "9"


def identity_problem(module) -> str:
    """'' when ``module`` looks like Project Chrono's PyChrono at a supported major version; else why not."""
    missing = [s for s in IDENTITY_SYMBOLS if not hasattr(module, s)]
    if missing:
        return f"the installed 'pychrono' lacks {missing}: it is not Project Chrono (a different package with the same name)"
    try:
        version = str(module.GetChronoVersion())
    except Exception as exc:  # noqa: BLE001 - a version API that raises is a broken install
        return f"GetChronoVersion() raised {type(exc).__name__}"
    if version.split(".")[0] != SUPPORTED_MAJOR:
        return f"Project Chrono {version} is outside the supported API major version {SUPPORTED_MAJOR}"
    return ""


def probe() -> ProviderStatus:
    base = python_package_probe(CAPABILITY, "pychrono", "pychrono")()
    if not base.available:
        return base
    try:
        import pychrono
    except Exception as exc:  # noqa: BLE001
        return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, location=base.location,
                              reason=f"could not establish the identity of pychrono: import failed ({type(exc).__name__}: {exc})")
    problem = identity_problem(pychrono)
    if problem:
        return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, location=base.location,
                              reason=f"could not establish the identity of pychrono: {problem}")
    return base


def register(registry, **_):
    registry.register(CAPABILITY, probe)
