"""Structure × environment signatures and versioned calibration keys.

Cost, failure probability and fidelity are properties of *what is being
computed* and *where it runs* — not of the scientific domain that happens to
be asking. A stiff 40-state ODE integrated in float64 on a laptop CPU behaves
the same whether the states are chemical concentrations or bus voltages.

So calibration is keyed by:

    StructureSignature  ×  EnvironmentSignature  ×  key_version

and a :class:`SemanticGuard` refuses to build a key that has been contaminated
with domain vocabulary. That refusal is the whole point: keying by domain name
would silently fragment the learned models and destroy transfer between
domains that share a computational shape.

Both signatures are versioned so a future change of what "structure" means
does not silently invalidate stored calibration data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..scientific.serialization import require_schema, schema_string
from .errors import CalibrationKeyContamination, SignatureError

STRUCTURE_SCHEMA = schema_string("sria_structure_signature")
ENVIRONMENT_SCHEMA = schema_string("sria_environment_signature")
CALIBRATION_KEY_SCHEMA = schema_string("sria_calibration_key")

STRUCTURE_SIGNATURE_VERSION = 1
ENVIRONMENT_SIGNATURE_VERSION = 1
CALIBRATION_KEY_VERSION = 1


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _clean_str_map(values: Mapping[str, Any], label: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        key = str(key).strip()
        if not key:
            raise SignatureError(f"{label} has an empty key")
        out[key] = str(value)
    return out


@dataclass(frozen=True)
class StructureComponent:
    """One computational element of a structure.

    ``kind`` describes computational shape (``"linear_system"``,
    ``"ode_block"``), never physics. ``multiplicity`` lets a structure say
    "twelve of these" without enumerating them.
    """

    kind: str
    multiplicity: int = 1
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = str(self.kind).strip()
        if not kind:
            raise SignatureError("structure component requires a kind")
        if int(self.multiplicity) < 1:
            raise SignatureError(
                f"structure component {kind!r} needs multiplicity >= 1"
            )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "multiplicity", int(self.multiplicity))
        object.__setattr__(
            self,
            "attributes",
            _clean_str_map(self.attributes, f"component {kind!r} attributes"),
        )

    def canonical(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "multiplicity": self.multiplicity,
            "attributes": dict(sorted(self.attributes.items())),
        }


@dataclass(frozen=True)
class StructureSignature:
    """Computational shape of a problem, independent of its physics."""

    structure_kind: str
    components: tuple[StructureComponent, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)
    signature_version: int = STRUCTURE_SIGNATURE_VERSION

    def __post_init__(self) -> None:
        kind = str(self.structure_kind).strip()
        if not kind:
            raise SignatureError("structure signature requires a structure_kind")
        object.__setattr__(self, "structure_kind", kind)
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(
            self,
            "attributes",
            _clean_str_map(self.attributes, "structure attributes"),
        )
        object.__setattr__(self, "signature_version", int(self.signature_version))

    def canonical(self) -> dict[str, Any]:
        # Components are sorted so declaration order cannot change identity,
        # exactly as circuit fingerprints already do in the electrical domain.
        return {
            "signature_version": self.signature_version,
            "structure_kind": self.structure_kind,
            "components": sorted(
                (c.canonical() for c in self.components),
                key=lambda c: json.dumps(c, sort_keys=True),
            ),
            "attributes": dict(sorted(self.attributes.items())),
        }

    @property
    def digest(self) -> str:
        return _digest(self.canonical())

    def compose(self, other: "StructureSignature", *, structure_kind: str) -> "StructureSignature":
        """Combine two structures into a composite one.

        M1 needs no composite structures yet; the operation exists so that a
        coupled multi-physics problem later does not require a new signature
        format. Composition is commutative because components are sorted.
        """
        if self.signature_version != other.signature_version:
            raise SignatureError(
                "cannot compose structure signatures of different versions"
            )
        merged = dict(self.attributes)
        for key, value in other.attributes.items():
            if key in merged and merged[key] != value:
                raise SignatureError(
                    f"conflicting structure attribute {key!r} during composition"
                )
            merged[key] = value
        return StructureSignature(
            structure_kind=structure_kind,
            components=self.components + other.components,
            attributes=merged,
            signature_version=self.signature_version,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical()
        payload["schema"] = STRUCTURE_SCHEMA
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StructureSignature":
        require_schema(payload, STRUCTURE_SCHEMA)
        return cls(
            structure_kind=payload["structure_kind"],
            components=tuple(
                StructureComponent(
                    kind=c["kind"],
                    multiplicity=c.get("multiplicity", 1),
                    attributes=c.get("attributes", {}),
                )
                for c in payload.get("components", ())
            ),
            attributes=payload.get("attributes", {}),
            signature_version=payload.get(
                "signature_version", STRUCTURE_SIGNATURE_VERSION
            ),
        )


@dataclass(frozen=True)
class EnvironmentSignature:
    """Where a computation ran, at the granularity that changes its behaviour."""

    hardware_class: str
    precision: str
    solver_build: tuple[str, str] = ("", "")   # (solver_id, build/version)
    runtime: Mapping[str, str] = field(default_factory=dict)
    signature_version: int = ENVIRONMENT_SIGNATURE_VERSION

    def __post_init__(self) -> None:
        for label in ("hardware_class", "precision"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise SignatureError(f"environment signature requires {label}")
            object.__setattr__(self, label, value)
        build = tuple(str(x) for x in self.solver_build)
        if len(build) != 2:
            raise SignatureError("solver_build must be (solver_id, build)")
        object.__setattr__(self, "solver_build", build)
        object.__setattr__(
            self, "runtime", _clean_str_map(self.runtime, "environment runtime")
        )
        object.__setattr__(self, "signature_version", int(self.signature_version))

    def canonical(self) -> dict[str, Any]:
        return {
            "signature_version": self.signature_version,
            "hardware_class": self.hardware_class,
            "precision": self.precision,
            "solver_build": list(self.solver_build),
            "runtime": dict(sorted(self.runtime.items())),
        }

    @property
    def digest(self) -> str:
        return _digest(self.canonical())

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical()
        payload["schema"] = ENVIRONMENT_SCHEMA
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvironmentSignature":
        require_schema(payload, ENVIRONMENT_SCHEMA)
        return cls(
            hardware_class=payload["hardware_class"],
            precision=payload["precision"],
            solver_build=tuple(payload.get("solver_build", ("", ""))),
            runtime=payload.get("runtime", {}),
            signature_version=payload.get(
                "signature_version", ENVIRONMENT_SIGNATURE_VERSION
            ),
        )


@runtime_checkable
class SemanticVocabulary(Protocol):
    """Anything that can declare the scientific words it owns."""

    def semantic_terms(self) -> tuple[str, ...]:
        ...


class SemanticGuard:
    """Refuses domain vocabulary inside computational calibration keys.

    The guard is explicit and passed in, never a global registry: a hidden
    global would make the boundary depend on import order.
    """

    def __init__(self, terms: Iterable[str] = ()) -> None:
        self._terms = frozenset(
            t.strip().lower() for t in terms if str(t).strip()
        )

    @property
    def terms(self) -> frozenset[str]:
        return self._terms

    def extend(self, terms: Iterable[str]) -> "SemanticGuard":
        return SemanticGuard(set(self._terms) | {str(t) for t in terms})

    def _offending(self, text: str) -> str | None:
        lowered = str(text).lower()
        for term in sorted(self._terms):
            # Substring match on purpose: "electrical.dc.voltage" must be
            # caught even though it is not an exact term.
            if term and term in lowered:
                return term
        return None

    def check(self, values: Iterable[str], *, context: str) -> None:
        for value in values:
            offender = self._offending(value)
            if offender is not None:
                raise CalibrationKeyContamination(
                    f"{context} contains domain semantic term {offender!r}; "
                    f"computational calibration must be keyed by structure and "
                    f"environment, never by scientific domain"
                )


def _structure_tokens(structure: StructureSignature) -> list[str]:
    tokens = [structure.structure_kind]
    tokens.extend(structure.attributes.keys())
    tokens.extend(structure.attributes.values())
    for component in structure.components:
        tokens.append(component.kind)
        tokens.extend(component.attributes.keys())
        tokens.extend(component.attributes.values())
    return tokens


@dataclass(frozen=True)
class CalibrationKey:
    """A versioned structure × environment key for computational calibration."""

    structure_digest: str
    environment_digest: str
    key_version: int = CALIBRATION_KEY_VERSION

    def __post_init__(self) -> None:
        for label in ("structure_digest", "environment_digest"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise SignatureError(f"calibration key requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "key_version", int(self.key_version))

    @property
    def key(self) -> str:
        return (
            f"calib/v{self.key_version}/"
            f"{self.structure_digest[:16]}/{self.environment_digest[:16]}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_KEY_SCHEMA,
            "key_version": self.key_version,
            "structure_digest": self.structure_digest,
            "environment_digest": self.environment_digest,
            "key": self.key,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationKey":
        require_schema(payload, CALIBRATION_KEY_SCHEMA)
        return cls(
            structure_digest=payload["structure_digest"],
            environment_digest=payload["environment_digest"],
            key_version=payload.get("key_version", CALIBRATION_KEY_VERSION),
        )


def build_calibration_key(
    structure: StructureSignature,
    environment: EnvironmentSignature,
    *,
    guard: SemanticGuard | None = None,
    key_version: int = CALIBRATION_KEY_VERSION,
) -> CalibrationKey:
    """Build a calibration key, refusing domain-contaminated structures."""
    if guard is not None:
        guard.check(_structure_tokens(structure), context="structure signature")
        guard.check(
            [environment.hardware_class, environment.precision]
            + list(environment.runtime.keys())
            + list(environment.runtime.values()),
            context="environment signature",
        )
    return CalibrationKey(
        structure_digest=structure.digest,
        environment_digest=environment.digest,
        key_version=key_version,
    )
