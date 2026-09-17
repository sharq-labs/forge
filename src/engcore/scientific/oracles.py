"""Domain-neutral external oracle evidence.

An oracle is evidence imported from outside the solve being judged: an
experimental dataset, an independently curated benchmark, or an analytic
reference. The core owns the comparison contract and evidence identity; a
domain owns how observations are obtained.

Two separate trust questions are enforced here:

* **content binding** — ``evidence_digest`` is recomputed from the oracle id,
  version, kind, reference and every observation (including its tolerance). A
  digest-shaped string cannot be attached to arbitrary expected values.
* **authority binding** — a passing comparison earns an evidentiary level only
  when that exact identity is pinned in the repository-owned trusted oracle
  registry below. A caller may compare against an untrusted oracle, but cannot
  promote its own declaration to ``EXPERIMENTALLY_VALIDATED`` merely by naming
  it experimental.

An external solver is deliberately not an oracle kind here. Agreement between
two solvers has an independence problem and belongs in ``consensus``. Treating
one solver as an oracle would bypass exactly the route-independence checks the
platform already requires.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping as RuntimeMapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .errors import ScientificValidationError, UnitCompatibilityError
from .results.immutable import freeze
from .results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from .serialization import require_schema, schema_string
from .units.quantity import Quantity, base_unit, require_spread_unit
from .units.validation import require_same_dimension


#: CORE-009/CORE-014: two statements of one operating point agree to this relative tolerance (class A).
_OPERATING_POINT_RTOL = 1.0e-9


def _same_operating_point(stated: Quantity, other: Any) -> bool:
    """Whether ``other`` is the same quantity as ``stated``: same dimension, equal to 1e-9 relative, or both zero.

    COMPARED IN THE CANONICAL UNIT OF THE DIMENSION, not in ``stated``'s own
    (I-22, R-52). A 1e-9 RELATIVE tolerance is a statement about a ratio, and a
    ratio means nothing on a scale whose zero is a convention: 0.02 degC and
    0.020000001 degC are 273.17 K and 273.170000001 K -- four parts in a
    trillion apart -- and read as DIFFERENT operating points, while the very
    same 1e-9 K difference written in kelvin read as the same one. Comparing in
    ``stated.units`` also made the predicate asymmetric, and "the same
    operating point" is a relation, not a claim one of the two makes about the
    other. The tolerance itself is untouched: what changes is the scale it is
    applied on.
    """
    if not isinstance(other, Quantity):
        return False
    try:
        require_same_dimension(stated, other, context="operating point")
        canonical = base_unit(stated.units)
        a, b = stated.magnitude_in(canonical), other.magnitude_in(canonical)
    except Exception:  # noqa: BLE001 - an incompatible statement is a different operating point
        return False
    return a == b or abs(a - b) <= _OPERATING_POINT_RTOL * max(abs(a), abs(b))

ORACLE_IDENTITY_SCHEMA = schema_string("oracle_identity")
ORACLE_OBSERVATION_SCHEMA = schema_string("oracle_observation")
ORACLE_EVIDENCE_SCHEMA = schema_string("oracle_evidence_set")
_ORACLE_CONTENT_TAG = b"crafty.oracle.evidence/1\x00"


class OracleKind(str, Enum):
    ANALYTIC_REFERENCE = "analytic_reference"
    BENCHMARK_DATASET = "benchmark_dataset"
    EXPERIMENTAL_DATASET = "experimental_dataset"


_LEVEL_BY_KIND = {
    OracleKind.ANALYTIC_REFERENCE: ValidationLevel.ANALYTICALLY_VERIFIED,
    OracleKind.BENCHMARK_DATASET: ValidationLevel.BENCHMARK_VALIDATED,
    OracleKind.EXPERIMENTAL_DATASET: ValidationLevel.EXPERIMENTALLY_VALIDATED,
}

# Repository-owned authority pins. This mapping is intentionally immutable and
# empty until a curated oracle is admitted by source change/review. Tests may
# replace the module attribute with an isolated fixture mapping; production
# callers receive no registration API because the party asking for a level must
# not also be the party that grants itself authority.
#
# Key: (oracle_id, version)
# Value: {"kind": <OracleKind.value>, "evidence_digest": <sha256>,
#         "reference": <stable external reference>, "declared_by": <prose>}
_TRUSTED_ORACLE_DECLARATIONS: Mapping[tuple[str, str], Mapping[str, str]] = (
    MappingProxyType({})
)


def _sha256(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ScientificValidationError(f"{label} must be a SHA-256 hex digest")
    return text


def _identity_text(value: Any, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ScientificValidationError(f"oracle identity requires {label}")
    return text


def _oracle_content_digest(
    *,
    oracle_id: str,
    version: str,
    kind: OracleKind,
    reference: str,
    observations: tuple["OracleObservation", ...],
) -> str:
    """Canonical digest of everything that can change an oracle comparison.

    Observation order is not scientific content, so it is canonicalized by
    metric. Expected values, units, absolute tolerances and notes are content
    and are all hashed. Identity metadata is included so the same numeric table
    cannot be relabelled from benchmark to experimental evidence while keeping
    its digest.
    """
    payload = {
        "oracle_id": str(oracle_id).strip(),
        "version": str(version).strip(),
        "kind": OracleKind(kind).value,
        "reference": str(reference).strip(),
        "observations": [
            observation.to_dict()
            for observation in sorted(observations, key=lambda item: item.metric)
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(_ORACLE_CONTENT_TAG)
    digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True)
class OracleIdentity:
    oracle_id: str
    version: str
    kind: OracleKind
    evidence_digest: str
    reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "oracle_id", _identity_text(self.oracle_id, label="oracle_id"))
        object.__setattr__(self, "version", _identity_text(self.version, label="version"))
        object.__setattr__(self, "reference", _identity_text(self.reference, label="reference"))
        object.__setattr__(self, "kind", OracleKind(self.kind))
        object.__setattr__(
            self, "evidence_digest", _sha256(self.evidence_digest, label="oracle evidence_digest")
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.oracle_id, self.version

    @property
    def establishes(self) -> ValidationLevel:
        return _LEVEL_BY_KIND[self.kind]

    @property
    def authority_gap(self) -> str | None:
        """Why this identity is not a repository-pinned oracle authority."""
        declaration = _TRUSTED_ORACLE_DECLARATIONS.get(self.key)
        if declaration is None:
            return (
                f"oracle {self.oracle_id!r}@{self.version} is not pinned by the "
                "trusted oracle registry"
            )
        if not isinstance(declaration, RuntimeMapping):
            return f"trusted oracle declaration for {self.key!r} is malformed"
        expected = {
            "kind": self.kind.value,
            "evidence_digest": self.evidence_digest,
            "reference": self.reference,
        }
        mismatches = [
            f"{field}={declaration.get(field)!r}, evidence has {value!r}"
            for field, value in expected.items()
            if declaration.get(field) != value
        ]
        if mismatches:
            return (
                f"oracle {self.oracle_id!r}@{self.version} does not match its "
                f"trusted declaration ({'; '.join(mismatches)})"
            )
        return None

    @property
    def is_trusted(self) -> bool:
        return self.authority_gap is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ORACLE_IDENTITY_SCHEMA,
            "oracle_id": self.oracle_id,
            "version": self.version,
            "kind": self.kind.value,
            "evidence_digest": self.evidence_digest,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OracleIdentity":
        require_schema(payload, ORACLE_IDENTITY_SCHEMA)
        return cls(
            oracle_id=payload["oracle_id"],
            version=payload["version"],
            kind=OracleKind(payload["kind"]),
            evidence_digest=payload["evidence_digest"],
            reference=payload["reference"],
        )


@dataclass(frozen=True)
class OracleObservation:
    metric: str
    expected: Quantity
    absolute_tolerance: Quantity
    note: str = ""
    #: CORE-009 (scientific core audit 2026-09-16): the operating point the observation was made at. A comparison is
    #: evidence about the model only there, so ``OracleEvidenceSet.compare`` makes none at any other. Serialized only
    #: when declared, so the content digest of evidence written before it is unchanged.
    conditions: Mapping[str, Quantity] = field(default_factory=dict)

    def __post_init__(self) -> None:
        conditions = dict(self.conditions)
        for key, value in conditions.items():
            if not str(key).strip() or not isinstance(value, Quantity):
                raise ScientificValidationError(
                    f"oracle observation condition {key!r} must be a named Quantity; an operating point without a "
                    f"unit identifies nothing"
                )
        object.__setattr__(self, "conditions", freeze({str(k).strip(): v for k, v in sorted(conditions.items())}))
        metric = str(self.metric).strip()
        if not metric:
            raise ScientificValidationError("oracle observation requires metric")
        if not isinstance(self.expected, Quantity) or not isinstance(
            self.absolute_tolerance, Quantity
        ):
            raise ScientificValidationError(
                "oracle expected and absolute_tolerance must be Quantities"
            )
        require_same_dimension(
            self.expected,
            self.absolute_tolerance,
            context=f"oracle observation {metric!r}",
        )
        # A TOLERANCE IS A DIFFERENCE (I-22, R-48).
        #
        # It was converted with `magnitude_in(self.expected.units)`, the
        # ABSOLUTE conversion, and the sign was then checked on the converted
        # number. Both halves were wrong and each covered for the other:
        # a 0.5 degC band against an expected 300 kelvin read as 273.65 kelvin,
        # so a prediction 273 kelvin wrong PASSED -- and with the identity
        # pinned it earned EXPERIMENTALLY_VALIDATED. Written the other way
        # round, a perfectly good 0.5 kelvin band on an expected value in degC
        # converted to -272.65 and was refused for being NEGATIVE, a message
        # about a sign for a value that is positive. And the physically correct
        # spelling, a delta_degC band on a degC value, raised the backend's own
        # DimensionalityError.
        #
        # `require_spread_unit` is the rule the domains already apply to a
        # coupling tolerance and an excursion span, and on a ratio scale a
        # magnitude's sign does not depend on the unit, so the check belongs on
        # the magnitude AS DECLARED.
        # Re-raised as this record's own contract error: every other refusal
        # in this method is a `ScientificValidationError`, and a caller
        # building an evidence set handles one exception type.
        try:
            require_spread_unit(
                self.absolute_tolerance.units,
                context=f"oracle observation {metric!r} tolerance",
            )
        except UnitCompatibilityError as exc:
            raise ScientificValidationError(str(exc)) from exc
        if self.absolute_tolerance.magnitude < 0.0:
            raise ScientificValidationError(
                f"oracle observation {metric!r} tolerance must be non-negative"
            )
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "note", str(self.note))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ORACLE_OBSERVATION_SCHEMA,
            "metric": self.metric,
            "expected": self.expected.to_dict(),
            "absolute_tolerance": self.absolute_tolerance.to_dict(),
            "note": self.note,
            **({"conditions": {k: v.to_dict() for k, v in self.conditions.items()}} if self.conditions else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OracleObservation":
        require_schema(payload, ORACLE_OBSERVATION_SCHEMA)
        return cls(
            metric=payload["metric"],
            expected=Quantity.from_dict(payload["expected"]),
            absolute_tolerance=Quantity.from_dict(payload["absolute_tolerance"]),
            note=payload.get("note", ""),
            conditions={k: Quantity.from_dict(v) for k, v in (payload.get("conditions") or {}).items()},
        )


@dataclass(frozen=True)
class OracleEvidenceSet:
    identity: OracleIdentity
    observations: tuple[OracleObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, OracleIdentity):
            raise ScientificValidationError("oracle evidence requires OracleIdentity")
        observations = tuple(self.observations)
        if not observations:
            raise ScientificValidationError("oracle evidence requires at least one observation")
        if any(not isinstance(item, OracleObservation) for item in observations):
            raise ScientificValidationError("oracle observations must be OracleObservation records")
        metrics = [item.metric for item in observations]
        if len(set(metrics)) != len(metrics):
            raise ScientificValidationError("oracle evidence metrics must be unique")
        object.__setattr__(self, "observations", observations)

        actual_digest = _oracle_content_digest(
            oracle_id=self.identity.oracle_id,
            version=self.identity.version,
            kind=self.identity.kind,
            reference=self.identity.reference,
            observations=observations,
        )
        if actual_digest != self.identity.evidence_digest:
            raise ScientificValidationError(
                f"oracle evidence digest mismatch for {self.identity.oracle_id!r}@"
                f"{self.identity.version}: identity declares "
                f"{self.identity.evidence_digest}, content hashes to {actual_digest}. "
                "A digest-shaped string is not evidence of content identity"
            )

    @classmethod
    def create(
        cls,
        *,
        oracle_id: str,
        version: str,
        kind: OracleKind,
        reference: str,
        observations: tuple[OracleObservation, ...],
    ) -> "OracleEvidenceSet":
        """Build content-addressed evidence from observations.

        This computes identity; it does not grant authority. The resulting set
        still earns no level unless its exact identity is repository-pinned.
        """
        oracle_id = _identity_text(oracle_id, label="oracle_id")
        version = _identity_text(version, label="version")
        reference = _identity_text(reference, label="reference")
        kind = OracleKind(kind)
        observations = tuple(observations)
        digest = _oracle_content_digest(
            oracle_id=oracle_id,
            version=version,
            kind=kind,
            reference=reference,
            observations=observations,
        )
        return cls(
            identity=OracleIdentity(
                oracle_id=oracle_id,
                version=version,
                kind=kind,
                evidence_digest=digest,
                reference=reference,
            ),
            observations=observations,
        )

    @property
    def content_digest(self) -> str:
        return self.identity.evidence_digest

    @property
    def is_trusted(self) -> bool:
        return self.identity.is_trusted

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ORACLE_EVIDENCE_SCHEMA,
            "identity": self.identity.to_dict(),
            "observations": [item.to_dict() for item in self.observations],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OracleEvidenceSet":
        require_schema(payload, ORACLE_EVIDENCE_SCHEMA)
        return cls(
            identity=OracleIdentity.from_dict(payload["identity"]),
            observations=tuple(
                OracleObservation.from_dict(item)
                for item in payload.get("observations", ())
            ),
        )

    def compare(
        self,
        predicted: Mapping[str, Quantity],
        *,
        name: str = "external_oracle",
        conditions: Mapping[str, Quantity] | None = None,
    ) -> ValidationCheck:
        """Compare every observation; only pinned evidence may award a level.

        CORE-009: an observation that declares its operating point is compared only at that point. If ``conditions``
        omits a declared condition or states another value, no comparison is made: the check is NOT_RUN and awards no
        level. It is not FAIL, because a comparison at other conditions is not evidence against the model.
        """
        stated = dict(conditions or {})
        elsewhere: list[str] = []
        for observation in self.observations:
            for key, value in observation.conditions.items():
                if key not in stated:
                    elsewhere.append(f"{observation.metric}:{key} not stated (observed at {value})")
                elif not _same_operating_point(value, stated[key]):
                    elsewhere.append(f"{observation.metric}:{key} is {stated[key]}, observed at {value}")
        if elsewhere:
            return ValidationCheck(
                name=name,
                outcome=ValidationOutcome.NOT_RUN,
                detail=(f"no comparison made: the prediction is not at the conditions the evidence was observed at "
                        f"{elsewhere}"),
                evidence=(f"oracle:{self.identity.oracle_id}@{self.identity.version}",
                          f"sha256:{self.identity.evidence_digest}"),
            )
        residual_ratio = 0.0
        failures: list[str] = []
        compared: list[str] = []
        for observation in self.observations:
            actual = predicted.get(observation.metric)
            if actual is None:
                failures.append(f"{observation.metric}:missing")
                continue
            if not isinstance(actual, Quantity):
                failures.append(f"{observation.metric}:not_quantity")
                continue
            try:
                require_same_dimension(
                    actual,
                    observation.expected,
                    context=f"oracle prediction {observation.metric!r}",
                )
                # The canonical unit of the dimension, for the reason the
                # consensus comparison gives (I-22, R-52): `residual_ratio`
                # below is a RATIO, and a ratio means nothing on a scale whose
                # zero is a convention. The tolerance is read as a DIFFERENCE
                # (I-22, R-48); its unit is already required to be a ratio
                # scale at declaration, so this conversion is the slope.
                unit = base_unit(observation.expected.units)
                delta = abs(
                    actual.magnitude_in(unit) - observation.expected.magnitude_in(unit)
                )
                tolerance = observation.absolute_tolerance.magnitude_as_spread_in(unit)
            except Exception as exc:
                failures.append(f"{observation.metric}:incompatible({exc})")
                continue
            compared.append(observation.metric)
            if tolerance == 0.0:
                ratio = 0.0 if delta == 0.0 else float("inf")
            else:
                ratio = delta / tolerance
            residual_ratio = max(residual_ratio, ratio)
            if ratio > 1.0:
                failures.append(
                    f"{observation.metric}:residual={delta:g}{unit}>tol={tolerance:g}{unit}"
                )

        passed = not failures and len(compared) == len(self.observations)
        summary_residual = residual_ratio if residual_ratio != float("inf") else 2.0
        authority_gap = self.identity.authority_gap
        trusted_pass = passed and authority_gap is None
        evidence = (
            f"oracle:{self.identity.oracle_id}@{self.identity.version}",
            f"sha256:{self.identity.evidence_digest}",
            f"reference:{self.identity.reference}",
            f"metrics:{','.join(sorted(compared))}",
            (
                "oracle-authority:repository-pinned"
                if authority_gap is None
                else f"oracle-authority:withheld:{authority_gap}"
            ),
        )
        if passed and authority_gap is None:
            detail = (
                f"all {len(compared)} oracle metric(s) within declared tolerance; "
                "content digest verified and oracle identity is repository-pinned"
            )
        elif passed:
            detail = (
                f"all {len(compared)} oracle metric(s) within declared tolerance, "
                f"but no validation level is awarded: {authority_gap}"
            )
        else:
            detail = f"oracle comparison failed: {failures}"
        return ValidationCheck(
            name=name,
            outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
            detail=detail,
            establishes=self.identity.establishes if trusted_pass else None,
            residual=summary_residual,
            tolerance=1.0,
            evidence=evidence,
        )


@runtime_checkable
class OracleProvider(Protocol):
    """A domain adapter that supplies immutable external evidence for a problem."""

    @property
    def identity(self) -> OracleIdentity: ...

    def evidence_for(self, problem: Any) -> OracleEvidenceSet: ...


__all__ = [
    "OracleKind",
    "OracleIdentity",
    "OracleObservation",
    "OracleEvidenceSet",
    "OracleProvider",
]
