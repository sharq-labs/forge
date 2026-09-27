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

    @property
    def found_but_refused(self) -> bool:
        """UNAVAILABLE although the provider is present: its adapter failed to import or register, its
        version probe failed, or its version could not be read. A defect to report, not an absent stack
        to skip (BIG 14 review F3). Read from the reason discovery wrote; not part of the record."""
        return not self.available and self.reason.startswith(("adapter ", "version probe of ", "could not establish the "))

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
    return _record_digest_of(importlib.metadata.distribution(dist_name), dist_name)


def _record_digest_of(dist: Any, dist_name: str) -> str:
    record = dist.read_text("RECORD")
    if record is None:
        files = sorted(str(f) for f in (dist.files or ()))
        record = "\n".join(files) or f"{dist_name}=={dist.version}"
    return hashlib.sha256(record.encode("utf-8")).hexdigest()


#: Distributions located for the execution-time library check, by name. Locating scans sys.path
#: (tens of milliseconds on a network or WSL mount); the files are re-read on every check, so a
#: changed RECORD or METADATA is seen, and an upgrade -- which replaces the dist-info directory --
#: reads as missing. Cleared by ``ProviderRegistry.status(refresh=True)``.
_LOCATED: dict[str, Any] = {}


def _footprint(dist: Any) -> tuple[frozenset[str], str]:
    """What a distribution's own files are: (real paths of the MODULE files it lists, its install root).

    A pip RECORD lists module files; a conda-installed distribution often lists none (no RECORD, or only
    its dist-info) -- it is bound by the conda package record inside the python-environment digest, and
    the only location fact available is its install root.
    """
    listed = frozenset(os.path.realpath(dist.locate_file(f)) for f in (dist.files or ())
                       if not str(f).split("/")[0].endswith((".dist-info", ".egg-info")))
    return listed, os.path.realpath(str(dist.locate_file("")))


_MODULES: dict[str, tuple[str, ...]] = {}


def _modules_of(dist: Any, name: str) -> tuple[str, ...]:
    """Top-level modules a distribution provides: ``top_level.txt`` when present, else its own name (once per process)."""
    if name not in _MODULES:
        listed = dist.read_text("top_level.txt") if dist is not None else None
        names = tuple(line.strip() for line in (listed or "").splitlines() if line.strip() and not line.strip().startswith("_"))
        _MODULES[name] = names or (name,)
    return _MODULES[name]


def _outside(path: str, footprint: tuple[frozenset[str], str]) -> bool:
    files, root = footprint
    real = os.path.realpath(path)
    if files:
        return real not in files
    return os.path.commonpath([real, root]) != root  # no module files listed: at least its own install root


#: Where a not-yet-imported module would be loaded from, resolved once per process (``find_spec`` scans
#: sys.path: tens of milliseconds on a WSL mount). Consistent with the operating rule: a path change
#: takes effect in a new process. Cleared by ``ProviderRegistry.status(refresh=True)``.
_SPEC_ORIGIN: dict[str, str] = {}
_FOOTPRINTS: dict[str, tuple[frozenset[str], str]] = {}


def _origin_outside(module: str, footprint: tuple[frozenset[str], str]) -> str:
    """'' when ``module`` (loaded, or as it would be imported) comes from the footprint; else where it comes from."""
    import sys

    loaded = sys.modules.get(module)
    if loaded is not None:
        where = getattr(loaded, "__file__", None)
        return "" if where and not _outside(where, footprint) else (where or "<no file>")
    if module not in _SPEC_ORIGIN:
        try:
            spec = importlib.util.find_spec(module)
            _SPEC_ORIGIN[module] = (spec.origin or "") if spec is not None else ""
        except (ImportError, ValueError) as exc:
            return f"<unresolvable: {type(exc).__name__}>"
    origin = _SPEC_ORIGIN[module]
    return "" if not origin or not _outside(origin, footprint) else origin


def _located(name: str) -> Any:
    if name not in _LOCATED:
        try:
            _LOCATED[name] = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            return None
    return _LOCATED[name]


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
                dep_dist = importlib.metadata.distribution(dep)
                for dep_module in _modules_of(dep_dist, dep):
                    elsewhere = _origin_outside(dep_module, _footprint(dep_dist))
                    if elsewhere:  # a shadowing checkout or an editable install of a DEPENDENCY: its RECORD would not describe it
                        return ProviderStatus(capability, Availability.UNAVAILABLE,
                                              reason=f"could not establish the distribution of dependency module {dep_module!r}: "
                                                     f"{elsewhere} is not a file of the installed {dep}")
                deps.append((dep, importlib.metadata.version(dep), distribution_digest(dep)))
            origin = os.path.realpath(importlib.util.find_spec(module).origin or "")
            dist = importlib.metadata.distribution(dist_name)
            if _outside(origin, _footprint(dist)):
                # a shadowing checkout or an editable install: the RECORD digest would not describe the code
                return ProviderStatus(capability, Availability.UNAVAILABLE, location=os.path.dirname(origin),
                                      reason=f"could not establish the distribution of module {module!r}: {origin} is not a file "
                                             f"of the installed {dist_name} {version}")
            main = distribution_digest(dist_name)
            combined = _combine(main, *(d[2] for d in deps))
            env_digest, count = python_environment_digest()  # shared numerics (numpy, ...) are not independent
            deps.append(("python-environment", f"{count} distributions", env_digest))
            return ProviderStatus(capability, Availability.AVAILABLE, version, combined,
                                  os.path.dirname(importlib.util.find_spec(module).origin or ""), dependencies=tuple(deps))
        except Exception as exc:  # discovery never crashes a scientific API
            return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"{type(exc).__name__}: {exc}")
    return probe


#: Per DISTRIBUTION (the provider's package and each declared dependency): the (version, RECORD digest)
#: under which it was first checked in this process. A module stays in memory after its files change;
#: a refresh must not make a newer discovery describe the older code that still runs, so this is never
#: cleared. Operating rule: a change to a provider environment takes effect in a NEW process; a
#: same-version rebuild of a module already in memory cannot be seen from inside the process.
_IMPORTED_UNDER: dict[str, tuple[str, str]] = {}


def require_library_unchanged(status: ProviderStatus, package: str) -> None:
    """Execution-time counterpart of :func:`python_package_probe` (BIG 14 reviews N1, M2).

    A library adapter calls this where it imports its library, naming the
    package it expects (the status is not trusted to say which one). Refused:

    * on disk: the provider's distribution or a declared dependency no longer
      has the version and RECORD digest discovery bound;
    * in memory: the imported module was loaded from another location than
      discovery found, carries another ``__version__``, or was first imported
      under another discovery in this process.

    Per execution it reads RECORD / METADATA files only; the shared
    python-environment digest is re-read by ``ProviderRegistry.status(refresh=True)``.
    """
    import sys

    from .records import ProviderRefusal

    if not status.available or status.capability.mode is not ProviderMode.LIBRARY:
        raise ProviderRefusal(f"{status.capability.provider_id!r} is not an available library provider")
    if status.capability.package != package:
        raise ProviderRefusal(f"the status describes {status.capability.package!r}, not the library {package!r} about to run")

    def now(name: str) -> tuple[str, str]:
        try:
            dist = _located(name)
            version = dist.version if dist is not None else None
            if not version:  # absent, or its dist-info was replaced (an upgrade) since it was located
                return "", ""
            return version, _record_digest_of(dist, name)
        except Exception:  # unreadable metadata is not a library that can be identified
            return "", ""

    found = [n for n in dict.fromkeys((package, package.lower())) if now(n)[0]]
    if not found:
        raise ProviderRefusal(f"library {package!r} changed since discovery: it is no longer installed as located "
                              f"(discovered {status.version})")
    declared = tuple(d for d in status.dependencies if d[0] != "python-environment")
    current = tuple((n, *now(n)) for n, _, _ in declared)
    version, main = now(found[0])
    combined = _combine(main, *(d[2] for d in current))  # `main` is re-used for the in-memory pins below
    if version != status.version or combined != status.digest or current != declared:
        raise ProviderRefusal(f"library {package!r} changed since discovery (now {version}, discovered {status.version}); "
                              "the execution identity no longer describes what would run")
    main_dist = found[0]
    bound = ((main_dist, package, status.version, main),) + tuple((n, n, v, d) for n, v, d in declared)
    for dist_name, module_name, want_version, want_digest in bound:
        # every module the distribution provides is loaded (or would be) from its own files (review N-1)
        dist = _located(dist_name)
        if dist_name not in _FOOTPRINTS:
            _FOOTPRINTS[dist_name] = _footprint(dist)
        for provided in dict.fromkeys((module_name,) + _modules_of(dist, dist_name)):
            elsewhere = _origin_outside(provided, _FOOTPRINTS[dist_name])
            if elsewhere:
                raise ProviderRefusal(f"{provided!r} would be (or was) loaded from {elsewhere}, which is not a file of the "
                                      f"discovered {dist_name} {want_version}")
        loaded = sys.modules.get(module_name)
        if loaded is None:
            if module_name == package:  # about to be imported: from where discovery found it (a later path shadow would not be)
                if package not in _SPEC_ORIGIN:
                    try:
                        spec = importlib.util.find_spec(package)
                        _SPEC_ORIGIN[package] = (spec.origin or "") if spec is not None else ""
                    except (ImportError, ValueError):
                        _SPEC_ORIGIN[package] = ""
                origin = os.path.realpath(os.path.dirname(_SPEC_ORIGIN[package])) if _SPEC_ORIGIN[package] else ""
                if origin != os.path.realpath(status.location):
                    raise ProviderRefusal(f"library {package!r} would now be imported from {origin or 'nowhere'}, "
                                          f"not from the discovered {status.location}")
        else:
            in_memory = str(getattr(loaded, "__version__", "") or "").split(" ")[0]
            if in_memory and in_memory != want_version:
                raise ProviderRefusal(f"{module_name!r} in memory is version {in_memory}; discovery bound {want_version}")
            if module_name == package:
                where = os.path.realpath(os.path.dirname(getattr(loaded, "__file__", None) or ""))
                if where != os.path.realpath(status.location):
                    raise ProviderRefusal(f"library {package!r} in memory was loaded from {where}, "
                                          f"not from the discovered {status.location}")
        pinned = _IMPORTED_UNDER.setdefault(dist_name, (want_version, want_digest))
        if pinned != (want_version, want_digest):
            raise ProviderRefusal(f"{dist_name!r} was first used in this process as {pinned[0]}; a refreshed status "
                                  f"({want_version}) does not describe the code in memory -- restart after changing the environment")


def executable_probe(capability: ProviderCapability, executable: str, version_argv: tuple[str, ...],
                     parse_version: Callable[[str], str], *, search_path: str | None = None, timeout: float = 30.0,
                     environment_prefix: str | None = None, accepted_exit_codes: tuple[int, ...] = (0,)) -> Callable[[], ProviderStatus]:
    """Probe an external executable: exact resolved path, file digest, parsed version.

    ``search_path`` is an explicit PATH to search (e.g. a provider environment's
    ``bin``); the process environment's PATH is used only when it is None.

    The probe must exit with one of ``accepted_exit_codes`` (default: 0). A
    failed or timed-out probe is UNAVAILABLE and yields no digest, so no
    execution identity can be formed from it -- text that merely parses as a
    version is not enough. A tool whose version flag exits non-zero by design
    declares the measured code in its descriptor.
    """
    codes = tuple(accepted_exit_codes)
    if not codes or any(isinstance(c, bool) or not isinstance(c, int) or c < 0 for c in codes):
        raise InvalidScientificProblem(f"accepted_exit_codes must be a non-empty tuple of non-negative ints, got {accepted_exit_codes!r}")

    def probe() -> ProviderStatus:
        try:
            path = shutil.which(executable, path=search_path)
            if path is None:
                return ProviderStatus(capability, Availability.UNAVAILABLE, reason=f"executable {executable!r} not found")
            real = os.path.realpath(path)
            out = subprocess.run([real, *version_argv], capture_output=True, text=True, timeout=timeout,
                                 env={"PATH": os.path.dirname(real), "HOME": os.environ.get("HOME", "/tmp")})
            if out.returncode not in codes:
                return ProviderStatus(capability, Availability.UNAVAILABLE, location=real,
                                      reason=f"version probe of {real} exited {out.returncode} (accepted {list(codes)})")
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
        if refresh:
            _PY_ENV.clear()  # a refresh re-reads the installed distributions too, not a digest cached at first probe
            _LOCATED.clear()
            _SPEC_ORIGIN.clear()
            _FOOTPRINTS.clear()
            _MODULES.clear()
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
                f"adapter package {module!r} is not importable here ({type(exc).__name__}: {exc})")
            continue
        try:
            adapter.register(registry, **dict(extra or {}))
        except Exception as exc:
            registry.register_unavailable(
                ProviderCapability(module.removeprefix("forge_"), "unknown", ProviderMode.LIBRARY, module, ()),
                f"adapter {module!r} failed to register: {type(exc).__name__}: {exc}")
    return registry
