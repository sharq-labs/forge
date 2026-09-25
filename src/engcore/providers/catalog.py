"""Descriptive provider capability registry and discovery (operational introspection only).

A capability says what a provider CAN compute (physics families, dimensions,
steady/transient, output ranks, mesh needs, restart/checkpoint, parallelism,
library vs process mode).  It is never scientific applicability: "provider
supports CFD" does not make any CFD model applicable to any problem.  The
registry does not rank providers and never selects one; ``require`` returns
exactly the requested provider or raises :class:`ProviderUnavailable` -- there
is no fallback.  Probing never imports a heavy scientific stack at import time
of this module and never lets an ImportError escape.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from ..numerical.core import ProviderUnavailable
from ..scientific.errors import InvalidScientificProblem

CAPABILITY_CLASSIFICATION = "descriptive_capability_not_applicability"

#: Adapter distributions shipped under ``providers/``.  Data, not branching:
#: nothing in Forge chooses a provider from this list.
KNOWN_ADAPTERS: tuple[str, ...] = (
    "forge_fenicsx", "forge_precice", "forge_pybamm", "forge_cantera", "forge_coolprop", "forge_tespy",
    "forge_calculix", "forge_openfoam", "forge_su2", "forge_code_aster", "forge_openmodelica",
)


class ProviderMode(str, Enum):
    LIBRARY = "library"   # in-process Python API
    PROCESS = "process"   # external executable through the process boundary


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    family: str
    mode: ProviderMode
    package: str
    physics: tuple[str, ...]
    dimensions: tuple[int, ...] = ()
    time_modes: tuple[str, ...] = ()
    output_ranks: tuple[str, ...] = ()
    mesh_requirement: str = "none"
    property_forms: tuple[str, ...] = ()
    restart: bool = False
    checkpoint: bool = False
    parallel: str = "serial"
    dependencies: tuple[str, ...] = ()
    license: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ProviderMode(self.mode))
        for label in ("provider_id", "family", "package"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"provider capability requires {label}")

    def to_dict(self) -> dict[str, Any]:
        return {"classification": CAPABILITY_CLASSIFICATION, "provider_id": self.provider_id, "family": self.family,
                "mode": self.mode.value, "package": self.package, "physics": list(self.physics), "dimensions": list(self.dimensions),
                "time_modes": list(self.time_modes), "output_ranks": list(self.output_ranks), "mesh_requirement": self.mesh_requirement,
                "property_forms": list(self.property_forms), "restart": self.restart, "checkpoint": self.checkpoint,
                "parallel": self.parallel, "dependencies": list(self.dependencies), "license": self.license, "notes": self.notes}


@dataclass(frozen=True)
class ProviderStatus:
    capability: ProviderCapability
    availability: Availability
    version: str = ""
    #: sha256 of the executable file or of the Python distribution's RECORD (identity).
    digest: str = ""
    #: operational location (path); NOT identity.
    location: str = ""
    reason: str = ""
    #: result-changing dependencies bound into identity: (name, version, sha256)
    dependencies: tuple[tuple[str, str, str], ...] = ()
    #: sha256 of the executable FILE alone at discovery (process providers); a launch
    #: re-hashes the file against this.  ``digest`` may also bind the environment.
    executable_digest: str = ""

    @property
    def available(self) -> bool:
        return self.availability is Availability.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability.to_dict(), "availability": self.availability.value, "version": self.version,
                "digest": self.digest, "location": self.location, "reason": self.reason,
                "dependencies": [list(d) for d in self.dependencies], "executable_digest": self.executable_digest}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def distribution_digest(dist_name: str) -> str:
    """sha256 over the installed distribution's RECORD (or sorted file list when absent)."""
    dist = importlib.metadata.distribution(dist_name)
    record = dist.read_text("RECORD")
    if record is None:
        files = sorted(str(f) for f in (dist.files or ()))
        record = "\n".join(files) or f"{dist_name}=={dist.version}"
    return hashlib.sha256(record.encode("utf-8")).hexdigest()


def _has_distribution(name: str) -> bool:
    try:
        importlib.metadata.distribution(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def conda_environment_digest(prefix: str) -> tuple[str, int]:
    """sha256 over every package record of a conda environment (name, version, build, package sha256/md5).

    Binds everything an external executable loads from its environment (shared
    libraries, data, launch scripts) by the exact package set, without hashing
    gigabytes of files.
    """
    import json

    meta = os.path.join(prefix, "conda-meta")
    rows = []
    for name in sorted(os.listdir(meta)):
        if name.endswith(".json"):
            with open(os.path.join(meta, name), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            rows.append([d.get("name"), d.get("version"), d.get("build"), d.get("sha256") or d.get("md5") or ""])
    if not rows:
        raise FileNotFoundError(f"no conda package records under {meta}")
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(), len(rows)


_PY_ENV: list = []


def python_environment_digest() -> tuple[str, int]:
    """sha256 over THIS interpreter's installed distribution set (name, version), plus the conda package
    records when the interpreter lives in a conda environment.  Cached per process."""
    if not _PY_ENV:
        import json
        import sys

        rows = sorted({((d.metadata["Name"] or "").lower(), d.version) for d in importlib.metadata.distributions()})
        parts = [hashlib.sha256(json.dumps(rows).encode()).hexdigest()]
        if os.path.isdir(os.path.join(sys.prefix, "conda-meta")):
            try:
                parts.append(conda_environment_digest(sys.prefix)[0])
            except FileNotFoundError:
                pass
        _PY_ENV.append((_combine(*parts), len(rows)))
    return _PY_ENV[0]


def _combine(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def python_package_probe(capability: ProviderCapability, module: str, dist_name: str | tuple[str, ...],
                         dependencies: tuple[str, ...] = ()) -> Callable[[], ProviderStatus]:
    """Probe a library provider; every declared DEPENDENCY distribution is version- and digest-bound too
    (a missing dependency makes the provider unavailable)."""
    names = (dist_name,) if isinstance(dist_name, str) else tuple(dist_name)

    def probe() -> ProviderStatus:
        try:
            if importlib.util.find_spec(module) is None:
                return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"python module {module!r} is not installed")
            found = [n for n in names if _has_distribution(n)]
            if not found:
                return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"no installed distribution metadata among {names}")
            dist_name = found[0]
            version = importlib.metadata.version(dist_name)
            deps = []
            for dep in dependencies:
                if not _has_distribution(dep):
                    return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"declared dependency distribution {dep!r} is not installed")
                deps.append((dep, importlib.metadata.version(dep), distribution_digest(dep)))
            main = distribution_digest(dist_name)
            combined = _combine(main, *(d[2] for d in deps))
            env_digest, count = python_environment_digest()  # shared numerics (numpy, ...) are not independent
            deps.append(("python-environment", f"{count} distributions", env_digest))
            return ProviderStatus(capability, Availability.AVAILABLE, version, combined,
                                  os.path.dirname(importlib.util.find_spec(module).origin or ""), dependencies=tuple(deps))
        except Exception as exc:  # discovery never crashes a scientific API
            return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"{type(exc).__name__}: {exc}")
    return probe


def executable_probe(capability: ProviderCapability, executable: str, version_argv: tuple[str, ...],
                     parse_version: Callable[[str], str], *, search_path: str | None = None, timeout: float = 30.0,
                     environment_prefix: str | None = None) -> Callable[[], ProviderStatus]:
    """Probe an external executable: exact resolved path, file digest, parsed version.

    ``search_path`` is an explicit PATH to search (e.g. a provider environment's
    ``bin``); the process environment's PATH is used only when it is None.
    """
    def probe() -> ProviderStatus:
        try:
            path = shutil.which(executable, path=search_path)
            if path is None:
                return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"executable {executable!r} not found")
            real = os.path.realpath(path)
            out = subprocess.run([real, *version_argv], capture_output=True, text=True, timeout=timeout,
                                 env={"PATH": os.path.dirname(real), "HOME": os.environ.get("HOME", "/tmp")})
            version = parse_version((out.stdout or "") + (out.stderr or ""))
            if not version:
                return ProviderStatus(capability, Availability.UNAVAILABLE, location=real,
                                      reason=f"could not establish the version of {real}")
            deps: tuple[tuple[str, str, str], ...] = ()
            digest = file_digest = _sha256_file(real)
            if environment_prefix:
                env_digest, count = conda_environment_digest(environment_prefix)
                deps = (("conda-environment", f"{count} packages", env_digest),)
                digest = _combine(digest, env_digest)
            return ProviderStatus(capability, Availability.AVAILABLE, version, digest, real, dependencies=deps,
                                  executable_digest=file_digest)
        except Exception as exc:
            return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"{type(exc).__name__}: {exc}")
    return probe


@dataclass
class ProviderRegistry:
    """Operational registry: descriptive capabilities + availability probes. Never ranks, never selects."""

    _entries: dict[str, tuple[ProviderCapability, Callable[[], ProviderStatus]]] = field(default_factory=dict)
    _cache: dict[str, ProviderStatus] = field(default_factory=dict)

    def register(self, capability: ProviderCapability, probe: Callable[[], ProviderStatus]) -> None:
        if capability.provider_id in self._entries:
            raise InvalidScientificProblem(f"provider {capability.provider_id!r} is already registered")
        self._entries[capability.provider_id] = (capability, probe)

    def register_unavailable(self, capability: ProviderCapability, reason: str) -> None:
        self.register(capability, lambda: ProviderStatus(capability, Availability.UNAVAILABLE, reason=reason))

    def status(self, provider_id: str, *, refresh: bool = False) -> ProviderStatus:
        if provider_id not in self._entries:
            raise ProviderUnavailable(f"provider {provider_id!r} is not registered")
        if refresh or provider_id not in self._cache:
            self._cache[provider_id] = self._entries[provider_id][1]()
        return self._cache[provider_id]

    def discover(self) -> tuple[ProviderStatus, ...]:
        """Every registered provider with its availability, in id order (no ranking)."""
        return tuple(self.status(pid) for pid in sorted(self._entries))

    def require(self, provider_id: str, *, version: str | None = None) -> ProviderStatus:
        """Exactly this provider, or ProviderUnavailable.  No alternative is ever substituted."""
        status = self.status(provider_id)
        if not status.available:
            raise ProviderUnavailable(f"provider {provider_id!r} is unavailable: {status.reason}; "
                                      "no other provider is substituted")
        if version is not None and status.version != version:
            raise ProviderUnavailable(f"provider {provider_id!r} version {status.version!r} does not match the "
                                      f"required {version!r}")
        return status


def default_registry(extra: Mapping[str, Any] | None = None) -> ProviderRegistry:
    """Registry of the adapter distributions that are importable here.

    An adapter package that cannot be imported is registered UNAVAILABLE with the
    reason; nothing raises.  Each adapter exposes ``register(registry, **extra)``.
    """
    registry = ProviderRegistry()
    for module in KNOWN_ADAPTERS:
        try:
            adapter = importlib.import_module(f"{module}.descriptor")
        except Exception as exc:
            registry.register_unavailable(
                ProviderCapability(module.removeprefix("forge_"), "unknown", ProviderMode.LIBRARY, module, ()),
                f"adapter package {module!r} is not importable here ({type(exc).__name__})")
            continue
        try:
            adapter.register(registry, **dict(extra or {}))
        except Exception as exc:
            registry.register_unavailable(
                ProviderCapability(module.removeprefix("forge_"), "unknown", ProviderMode.LIBRARY, module, ()),
                f"adapter {module!r} failed to register: {type(exc).__name__}: {exc}")
    return registry
