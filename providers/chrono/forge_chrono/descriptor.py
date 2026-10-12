"""Descriptive registration of the Project Chrono provider (library mode).

Project Chrono's Python bindings are distributed by conda-forge as the conda
package ``pychrono``.  That package installs NO Python distribution metadata
(no ``*.dist-info``), so the generic :func:`python_package_probe` cannot bind
it.  Identity is therefore bound to the CONDA PACKAGE RECORDS instead:

* exactly one ``conda-meta/pychrono-*.json`` record in the interpreter's
  prefix gives the version, build and package sha256;
* the module found ON DISK (not the one in memory) must be one of that
  record's files;
* the BYTES of the code that loads -- pychrono's ``.py`` / ``.so`` files and
  the ``chrono`` package's shared libraries -- must match the sha256 the
  records list (an in-place change or an overwrite is refused);
* the whole conda environment digest is bound as a dependency.

The build is PINNED when this process first imports pychrono, which happens
in discovery.  A module stays in memory after its files change, so a later
discovery of another build in the same process is refused (a new process is
required), and a pychrono imported before any discovery is refused because
nothing establishes which build that is.

With no conda record the generic pip probe is used, and API identity is
checked: the PyPI package named ``pychrono`` is an unrelated timing library,
so "importable" proves nothing about which code would run.  Chrono 10
exposes no version function to Python; the version comes from the record.
"""

from __future__ import annotations

import glob
import hashlib
import importlib.machinery
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
    notes="supported API major version 10; fixed, revolute, prismatic and spherical joints; Euler implicit linearized + direct sparse solvers")

#: Project Chrono API symbols whose presence identifies the library (not a same-named package).
IDENTITY_SYMBOLS = ("ChSystemNSC", "ChBody", "ChLinkLockRevolute", "ChFramed", "ChVector3d", "ChQuaterniond", "ChSolver")
SUPPORTED_MAJOR = "10"
CONDA_PACKAGE = "pychrono"
LIBRARY_PACKAGE = "chrono"
CONDA_ENVIRONMENT = "conda-environment"


def identity_problem(module, version: str) -> str:
    """'' when ``module`` looks like Project Chrono's PyChrono at a supported major ``version``; else why not."""
    missing = [s for s in IDENTITY_SYMBOLS if not hasattr(module, s)]
    if missing:
        return f"the installed 'pychrono' lacks {missing}: it is not Project Chrono (a different package with the same name)"
    if str(version).split(".")[0] != SUPPORTED_MAJOR:
        return f"Project Chrono {version} is outside the supported API major version {SUPPORTED_MAJOR}"
    return ""


class _Refused(Exception):
    pass


def _records(prefix: str, name: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(prefix, "conda-meta", f"{name}-*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("name") == name:
            out.append(rec)
    return out


def conda_record(prefix: str | None = None, name: str = CONDA_PACKAGE) -> dict | None:
    """The single conda package record of ``name`` in ``prefix`` (default: the interpreter's); None when absent.
    More than one record is refused: which one describes the installed files would be a guess."""
    found = _records(prefix or sys.prefix, name)
    if len(found) > 1:
        raise _Refused(f"{len(found)} conda records name {name!r}; which build is installed would be a guess")
    return found[0] if found else None


def _record_digest(rec: dict) -> str:
    row = [rec.get("name"), rec.get("version"), rec.get("build"), rec.get("sha256") or rec.get("md5") or "", sorted(rec.get("files", ()))]
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def _loaded_code(path: str) -> bool:
    base = os.path.basename(path)
    return base.endswith(".py") or base.endswith(".so") or ".so." in base


def _verify_bytes(rec: dict, prefix: str, select) -> None:
    """Every selected file of the record must exist with the sha256 the record lists (prefix-replaced value when given)."""
    paths = (rec.get("paths_data") or {}).get("paths") or []
    chosen = [p for p in paths if select(p["_path"])]
    if not chosen:
        raise _Refused(f"the conda record of {rec.get('name')!r} lists no file hashes for its loaded code")
    for p in chosen:
        expected = p.get("sha256_in_prefix") or p.get("sha256")
        full = os.path.join(prefix, p["_path"])
        h = hashlib.sha256()
        try:
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
        except OSError as exc:
            raise _Refused(f"{p['_path']} of {rec.get('name')} is unreadable ({exc})") from exc
        if h.hexdigest() != expected:
            raise _Refused(f"{p['_path']} does not have the bytes the conda record of {rec.get('name')} {rec.get('version')} lists")


def _unavailable(reason: str, location: str = "") -> ProviderStatus:
    return ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, location=location, reason=f"could not establish the identity of pychrono: {reason}")


#: (version, digest) of the build this process loaded.  Never cleared (a module stays in memory).
_LOADED_UNDER: list[tuple[str, str]] = []


def _conda_identity(rec: dict, prefix: str) -> tuple[str, str, str, tuple]:
    """(version, digest, location, dependencies) of the on-disk build; raises _Refused."""
    spec = importlib.machinery.PathFinder.find_spec("pychrono")  # what is ON DISK, not the module already in memory
    if spec is None or not spec.origin:
        raise _Refused("python module 'pychrono' is not on the path although its conda record exists")
    origin = os.path.realpath(spec.origin)
    if origin not in {os.path.realpath(os.path.join(prefix, f)) for f in rec.get("files", ())}:
        raise _Refused(f"{origin} is not a file of the conda package {CONDA_PACKAGE} {rec.get('version')}")
    _verify_bytes(rec, prefix, lambda p: "/pychrono/" in p and _loaded_code(p))
    lib = conda_record(prefix, LIBRARY_PACKAGE)
    if lib is None:
        raise _Refused(f"no conda record of {LIBRARY_PACKAGE!r}, whose shared libraries pychrono loads")
    _verify_bytes(lib, prefix, lambda p: p.startswith("lib/") and _loaded_code(p))
    env_digest, count = conda_environment_digest(prefix)
    digest = hashlib.sha256(f"{_record_digest(rec)}\n{_record_digest(lib)}\n{env_digest}".encode()).hexdigest()
    return str(rec["version"]), digest, os.path.dirname(origin), ((CONDA_ENVIRONMENT, f"{count} packages", env_digest),)


def _conda_probe(rec: dict, prefix: str) -> ProviderStatus:
    try:
        version, digest, location, deps = _conda_identity(rec, prefix)
    except _Refused as exc:
        return _unavailable(str(exc))
    if not _LOADED_UNDER and "pychrono" in sys.modules:
        return _unavailable("pychrono was imported before discovery; which build is in memory is not established (use a new process)", location)
    if _LOADED_UNDER and _LOADED_UNDER[0] != (version, digest):
        return _unavailable(f"this process loaded pychrono {_LOADED_UNDER[0][0]} {_LOADED_UNDER[0][1][:12]}; the build on disk is now "
                            f"{version} {digest[:12]} and only a new process runs it", location)
    try:
        import pychrono
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"import failed ({type(exc).__name__}: {exc})", location)
    if not _LOADED_UNDER:
        _LOADED_UNDER.append((version, digest))
    loaded = os.path.dirname(os.path.realpath(getattr(pychrono, "__file__", "") or ""))
    if loaded != location:
        return _unavailable(f"the pychrono in memory was loaded from {loaded}, not {location}", location)
    problem = identity_problem(pychrono, version)
    if problem:
        return _unavailable(problem, location)
    return ProviderStatus(CAPABILITY, Availability.AVAILABLE, version, digest, location, dependencies=deps)


def probe() -> ProviderStatus:
    try:
        rec = conda_record()
    except _Refused as exc:
        return _unavailable(str(exc))
    except Exception as exc:  # noqa: BLE001 - discovery never crashes a scientific API
        return _unavailable(f"conda package record unreadable ({type(exc).__name__}: {exc})")
    if rec is not None:
        return _conda_probe(rec, sys.prefix)
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


def require_unchanged(status: ProviderStatus) -> None:
    """Execution-time identity check: rediscover now and require the status's version and digest.  Discovery
    itself refuses a build other than the one this process loaded.  The status is not trusted to say which
    route bound it."""
    from engcore.providers import ProviderRefusal

    if not status.available or status.capability.provider_id != "chrono":
        raise ProviderRefusal("Project Chrono is not an available provider in this status")
    now = probe()
    if not now.available or (now.version, now.digest) != (status.version, status.digest):
        raise ProviderRefusal(f"Project Chrono changed since discovery (discovered {status.version} {status.digest[:12]}, "
                              f"now {now.version or 'unavailable'} {now.digest[:12]}: {now.reason})")


def register(registry, **_):
    registry.register(CAPABILITY, probe)
