"""Descriptive registration of the Project Chrono provider (library mode).

Project Chrono's Python bindings are distributed by conda-forge as the conda
package ``pychrono``.  That package installs NO Python distribution metadata
(no ``*.dist-info``), so the generic :func:`python_package_probe` cannot bind
it.  Identity is therefore bound to the CONDA PACKAGE RECORD instead:

* the record ``conda-meta/pychrono-*.json`` of the running interpreter's
  prefix gives the version, build and package sha256;
* the imported module file must be one of that record's files (a shadowing
  checkout or a same-named package elsewhere is refused);
* the whole conda environment digest is bound as a dependency, because
  ``_core.so`` loads ``libChrono*`` from the separate ``chrono`` package.

With no conda record the generic pip probe is used, and API identity is
checked: the PyPI package named ``pychrono`` is an unrelated timing library,
so "importable" proves nothing about which code would run.

Chrono 10 exposes no version function to Python; the version comes from the
package record, never from the module.
"""

from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import os
import sys

from engcore.providers import Availability, ProviderCapability, ProviderStatus, python_package_probe
from engcore.providers.catalog import conda_environment_digest

CAPABILITY = ProviderCapability(
    "chrono", "multibody", "library", "pychrono", ("rigid_multibody_dynamics",), dimensions=(3,),
    time_modes=("transient",), output_ranks=("series",), mesh_requirement="none (rigid bodies with declared mass properties)",
    property_forms=("mass, centre of mass and inertia per body from declared sources",), restart=False, checkpoint=False,
    parallel="serial", dependencies=("pychrono (conda-forge)",), license="BSD-3-Clause",
    notes="supported API major version 10; fixed, revolute, prismatic and spherical joints; direct sparse solvers")

#: Project Chrono API symbols whose presence identifies the library (not a same-named package).
IDENTITY_SYMBOLS = ("ChSystemNSC", "ChBody", "ChLinkLockRevolute", "ChFramed", "ChVector3d", "ChQuaterniond", "ChSolver")
SUPPORTED_MAJOR = "10"
CONDA_PACKAGE = "pychrono"
CONDA_ENVIRONMENT = "conda-environment"


def identity_problem(module, version: str) -> str:
    """'' when ``module`` looks like Project Chrono's PyChrono at a supported major ``version``; else why not."""
    missing = [s for s in IDENTITY_SYMBOLS if not hasattr(module, s)]
    if missing:
        return f"the installed 'pychrono' lacks {missing}: it is not Project Chrono (a different package with the same name)"
    if str(version).split(".")[0] != SUPPORTED_MAJOR:
        return f"Project Chrono {version} is outside the supported API major version {SUPPORTED_MAJOR}"
    return ""


def conda_record(prefix: str | None = None) -> dict | None:
    """The conda package record of ``pychrono`` in ``prefix`` (default: the running interpreter's), or None."""
    prefix = prefix or sys.prefix
    found = sorted(glob.glob(os.path.join(prefix, "conda-meta", f"{CONDA_PACKAGE}-*.json")))
    for path in found:
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("name") == CONDA_PACKAGE:
            return rec
    return None


def _record_digest(rec: dict) -> str:
    row = [rec.get("name"), rec.get("version"), rec.get("build"), rec.get("sha256") or rec.get("md5") or "", sorted(rec.get("files", ()))]
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def _record_files(rec: dict, prefix: str) -> frozenset[str]:
    return frozenset(os.path.realpath(os.path.join(prefix, f)) for f in rec.get("files", ()))


def _unavailable(reason: str, location: str = "") -> ProviderStatus:
    return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, location=location, reason=f"could not establish the identity of pychrono: {reason}")


def _conda_probe(rec: dict, prefix: str) -> ProviderStatus:
    spec = importlib.util.find_spec("pychrono")
    if spec is None or not spec.origin:
        return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="python module 'pychrono' is not installed")
    origin = os.path.realpath(spec.origin)
    if origin not in _record_files(rec, prefix):
        return _unavailable(f"{origin} is not a file of the conda package {CONDA_PACKAGE} {rec.get('version')}", os.path.dirname(origin))
    try:
        import pychrono
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"import failed ({type(exc).__name__}: {exc})", os.path.dirname(origin))
    problem = identity_problem(pychrono, str(rec.get("version", "")))
    if problem:
        return _unavailable(problem, os.path.dirname(origin))
    env_digest, count = conda_environment_digest(prefix)
    main = _record_digest(rec)
    digest = hashlib.sha256(f"{main}\n{env_digest}".encode()).hexdigest()
    return ProviderStatus(CAPABILITY, Availability.AVAILABLE, str(rec["version"]), digest, os.path.dirname(origin),
                          dependencies=((CONDA_ENVIRONMENT, f"{count} packages", env_digest),))


def probe() -> ProviderStatus:
    try:
        rec = conda_record()
        if rec is not None:
            return _conda_probe(rec, sys.prefix)
    except Exception as exc:  # noqa: BLE001 - discovery never crashes a scientific API
        return _unavailable(f"conda package record unreadable ({type(exc).__name__}: {exc})")
    base = python_package_probe(CAPABILITY, "pychrono", "pychrono")()
    if not base.available:
        return base
    try:
        import pychrono
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"import failed ({type(exc).__name__}: {exc})", base.location)
    problem = identity_problem(pychrono, base.version)
    if problem:
        return _unavailable(problem, base.location)
    return base


#: (version, digest) under which pychrono was first executed in this process.  A module stays in
#: memory after its files change, so a later discovery must not describe the code that still runs.
_EXECUTED_UNDER: list[tuple[str, str]] = []


def require_unchanged(status: ProviderStatus) -> None:
    """Execution-time identity check: rediscover now and require the status's version and digest,
    the loaded module to come from the discovered location, and no earlier execution in this process
    under another identity.  The status is not trusted to say which route bound it."""
    from engcore.providers import ProviderRefusal

    if not status.available or status.capability.provider_id != "chrono":
        raise ProviderRefusal("Project Chrono is not an available provider in this status")
    now = probe()
    if not now.available or (now.version, now.digest) != (status.version, status.digest):
        raise ProviderRefusal(f"Project Chrono changed since discovery (discovered {status.version} {status.digest[:12]}, "
                              f"now {now.version or 'unavailable'} {now.digest[:12]}: {now.reason})")
    loaded = sys.modules.get("pychrono")
    if loaded is not None and os.path.dirname(os.path.realpath(getattr(loaded, "__file__", "") or "")) != os.path.realpath(now.location):
        raise ProviderRefusal("the pychrono module in memory was not loaded from the discovered location")
    if _EXECUTED_UNDER and _EXECUTED_UNDER[0] != (now.version, now.digest):
        raise ProviderRefusal("pychrono already ran in this process under another identity; a new process is required")
    if not _EXECUTED_UNDER:
        _EXECUTED_UNDER.append((now.version, now.digest))


def register(registry, **_):
    registry.register(CAPABILITY, probe)
