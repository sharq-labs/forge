"""Frozen, replayable Domain Pack registrations.

A live provider is consulted exactly once at registration.  The resulting
provider exposes immutable tuples thereafter, so validation and later product
assembly see the same models, realizations, solver factories and auxiliary
artifacts.

Implementation fingerprints are deliberately stronger than version strings:
source-backed callables are hashed from their source/module bytes.  If Forge
cannot establish a stable implementation fingerprint, registration fails
closed rather than pretending that an id/version pair proves executable
identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import InvalidDomainPackProvider
from .manifest import ArtifactRef, DomainPackManifest
from .provider import ProvidedArtifact


def _json_digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _implementation_digest(value: Any) -> tuple[str, str]:
    """Return (digest, basis) for executable Python-backed artifacts."""

    module = inspect.getmodule(value)
    module_name = getattr(value, "__module__", None) or (
        None if module is None else module.__name__
    )
    qualname = getattr(value, "__qualname__", None) or getattr(
        value, "__name__", None
    )
    if not module_name or not qualname:
        raise InvalidDomainPackProvider(
            f"cannot establish implementation identity for {value!r}"
        )

    pieces: list[bytes] = [
        f"module={module_name}\nqualname={qualname}\n".encode("utf-8")
    ]
    basis: list[str] = [f"python:{module_name}.{qualname}"]

    try:
        source = inspect.getsource(value)
    except (OSError, TypeError):
        source = ""
    if source:
        pieces.append(source.encode("utf-8"))
        basis.append("source")

    module_file = getattr(module, "__file__", None)
    if module_file:
        path = Path(module_file)
        try:
            pieces.append(path.read_bytes())
            basis.append(f"module_file:{path.name}")
        except OSError:
            pass

    code = getattr(value, "__code__", None)
    if code is not None:
        pieces.append(code.co_code)
        pieces.append(repr(code.co_consts).encode("utf-8"))
        basis.append("bytecode")

    if len(pieces) == 1:
        raise InvalidDomainPackProvider(
            f"implementation {module_name}.{qualname} has no stable "
            "source/module/bytecode material to fingerprint"
        )

    digest = hashlib.sha256(b"\x00".join(pieces)).hexdigest()
    return digest, "+".join(basis)


@dataclass(frozen=True, order=True)
class ArtifactImplementationFingerprint:
    kind: str
    artifact_id: str
    version: str
    digest: str
    basis: str

    def __post_init__(self) -> None:
        for label in ("kind", "artifact_id", "version", "basis"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidDomainPackProvider(
                    f"artifact implementation fingerprint requires {label}"
                )
            object.__setattr__(self, label, value)
        digest = str(self.digest).strip().lower()
        if (
            len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise InvalidDomainPackProvider(
                "artifact implementation fingerprint digest must be sha256 hex"
            )
        object.__setattr__(self, "digest", digest)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "digest": self.digest,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class FrozenDomainPackProvider:
    """One immutable read of a DomainPackProvider."""

    manifest: DomainPackManifest
    _models: tuple[Any, ...]
    _realizations: tuple[Any, ...]
    _solver_factories: tuple[Callable[[], Any], ...]
    _calibration_protocols: tuple[ProvidedArtifact, ...]
    _validation_protocols: tuple[ProvidedArtifact, ...]
    _uq_producers: tuple[ProvidedArtifact, ...]
    _measurement_adapters: tuple[ProvidedArtifact, ...]
    _transformations: tuple[ProvidedArtifact, ...]
    _benchmarks: tuple[ProvidedArtifact, ...]
    source_provider_type: str

    def models(self):
        return self._models

    def realizations(self):
        return self._realizations

    def solver_factories(self):
        return self._solver_factories

    def calibration_protocols(self):
        return self._calibration_protocols

    def validation_protocols(self):
        return self._validation_protocols

    def uq_producers(self):
        return self._uq_producers

    def measurement_adapters(self):
        return self._measurement_adapters

    def transformations(self):
        return self._transformations

    def benchmarks(self):
        return self._benchmarks


@dataclass(frozen=True)
class FrozenDomainPack:
    provider: FrozenDomainPackProvider
    implementation_fingerprints: tuple[
        ArtifactImplementationFingerprint, ...
    ]

    @property
    def manifest(self) -> DomainPackManifest:
        return self.provider.manifest

    @property
    def implementation_digest(self) -> str:
        return _json_digest(
            {
                "manifest_digest": self.manifest.digest,
                "artifacts": [
                    item.to_dict()
                    for item in self.implementation_fingerprints
                ],
            }
        )


def _records(provider: Any, name: str) -> tuple[Any, ...]:
    getter = getattr(provider, name, None)
    if not callable(getter):
        raise InvalidDomainPackProvider(
            f"provider must expose callable {name}()"
        )
    try:
        return tuple(getter())
    except Exception as exc:
        raise InvalidDomainPackProvider(
            f"provider.{name}() failed while freezing registration"
        ) from exc


def freeze_domain_pack_provider(
    provider: Any,
    *,
    manifest: DomainPackManifest | None = None,
) -> FrozenDomainPack:
    if manifest is None:
        manifest = getattr(provider, "manifest", None)
    if not isinstance(manifest, DomainPackManifest):
        raise InvalidDomainPackProvider(
            "provider manifest must be DomainPackManifest before freezing"
        )

    frozen = FrozenDomainPackProvider(
        manifest=manifest,
        _models=_records(provider, "models"),
        _realizations=_records(provider, "realizations"),
        _solver_factories=_records(provider, "solver_factories"),
        _calibration_protocols=_records(provider, "calibration_protocols"),
        _validation_protocols=_records(provider, "validation_protocols"),
        _uq_producers=_records(provider, "uq_producers"),
        _measurement_adapters=_records(provider, "measurement_adapters"),
        _transformations=_records(provider, "transformations"),
        _benchmarks=_records(provider, "benchmarks"),
        source_provider_type=(
            f"{type(provider).__module__}.{type(provider).__qualname__}"
        ),
    )

    fingerprints: list[ArtifactImplementationFingerprint] = []

    for model in frozen.models():
        payload = model.to_dict()
        fingerprints.append(
            ArtifactImplementationFingerprint(
                "model_contract",
                model.model_id,
                model.version,
                _json_digest(payload),
                "serialized_model_definition",
            )
        )

    for realization in frozen.realizations():
        payload = realization.to_dict()
        fingerprints.append(
            ArtifactImplementationFingerprint(
                "realization_contract",
                realization.realization_id,
                realization.version,
                _json_digest(payload),
                "serialized_realization_definition",
            )
        )

    for factory in frozen.solver_factories():
        try:
            probe = factory()
        except Exception as exc:
            raise InvalidDomainPackProvider(
                "solver factory failed while establishing frozen identity"
            ) from exc
        identity = getattr(probe, "identity", None)
        if identity is None:
            raise InvalidDomainPackProvider(
                "solver factory produced object with no identity"
            )
        digest, basis = _implementation_digest(factory)
        fingerprints.append(
            ArtifactImplementationFingerprint(
                "solver_implementation",
                identity.solver_id,
                identity.version,
                digest,
                basis,
            )
        )

    aux_groups = (
        ("calibration_protocol", frozen.calibration_protocols()),
        ("validation_protocol", frozen.validation_protocols()),
        ("uq_producer", frozen.uq_producers()),
        ("measurement_adapter", frozen.measurement_adapters()),
        ("transformation", frozen.transformations()),
        ("benchmark", frozen.benchmarks()),
    )
    for kind, records in aux_groups:
        for item in records:
            if not isinstance(item, ProvidedArtifact):
                continue
            digest, basis = _implementation_digest(item.implementation)
            fingerprints.append(
                ArtifactImplementationFingerprint(
                    kind,
                    item.ref.artifact_id,
                    item.ref.version,
                    digest,
                    basis,
                )
            )

    return FrozenDomainPack(
        frozen,
        tuple(sorted(fingerprints)),
    )


__all__ = [
    "ArtifactImplementationFingerprint",
    "FrozenDomainPack",
    "FrozenDomainPackProvider",
    "freeze_domain_pack_provider",
]
