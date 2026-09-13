"""Domain-neutral external oracle evidence.

An oracle is evidence imported from outside the solve being judged: an
experimental dataset, an independently curated benchmark, or an analytic
reference.  The core owns the comparison contract and evidence identity; a
domain owns how observations are obtained.

An *external solver* is deliberately not an oracle kind here. Agreement between
two solvers has an independence problem and belongs in ``consensus``. Treating
one solver as an oracle would bypass exactly the route-independence checks the
platform already requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from .errors import ScientificValidationError
from .results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from .serialization import require_schema, schema_string
from .units.quantity import Quantity
from .units.validation import require_same_dimension

ORACLE_IDENTITY_SCHEMA = schema_string("oracle_identity")
ORACLE_OBSERVATION_SCHEMA = schema_string("oracle_observation")
ORACLE_EVIDENCE_SCHEMA = schema_string("oracle_evidence_set")


def _sha256(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ScientificValidationError(f"{label} must be a SHA-256 hex digest")
    return text


class OracleKind(str, Enum):
    ANALYTIC_REFERENCE = "analytic_reference"
    BENCHMARK_DATASET = "benchmark_dataset"
    EXPERIMENTAL_DATASET = "experimental_dataset"


_LEVEL_BY_KIND = {
    OracleKind.ANALYTIC_REFERENCE: ValidationLevel.ANALYTICALLY_VERIFIED,
    OracleKind.BENCHMARK_DATASET: ValidationLevel.BENCHMARK_VALIDATED,
    OracleKind.EXPERIMENTAL_DATASET: ValidationLevel.EXPERIMENTALLY_VALIDATED,
}


@dataclass(frozen=True)
class OracleIdentity:
    oracle_id: str
    version: str
    kind: OracleKind
    evidence_digest: str
    reference: str

    def __post_init__(self) -> None:
        for label in ("oracle_id", "version", "reference"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ScientificValidationError(f"oracle identity requires {label}")
            object.__setattr__(self, label, value)
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

    def __post_init__(self) -> None:
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
        if self.absolute_tolerance.magnitude_in(self.expected.units) < 0.0:
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
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OracleObservation":
        require_schema(payload, ORACLE_OBSERVATION_SCHEMA)
        return cls(
            metric=payload["metric"],
            expected=Quantity.from_dict(payload["expected"]),
            absolute_tolerance=Quantity.from_dict(payload["absolute_tolerance"]),
            note=payload.get("note", ""),
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

    def compare(self, predicted: Mapping[str, Quantity], *, name: str = "external_oracle") -> ValidationCheck:
        """Compare every oracle observation; missing/wrong-unit outputs fail closed."""
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
                unit = observation.expected.units
                delta = abs(
                    actual.magnitude_in(unit) - observation.expected.magnitude_in(unit)
                )
                tolerance = observation.absolute_tolerance.magnitude_in(unit)
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
        # ValidationCheck refuses non-finite residuals even on a claimed PASS;
        # a failing check may carry finite summary only.  Use a finite sentinel
        # >1 for any infinite miss so the failure remains serializable.
        summary_residual = residual_ratio if residual_ratio != float("inf") else 2.0
        evidence = (
            f"oracle:{self.identity.oracle_id}@{self.identity.version}",
            f"sha256:{self.identity.evidence_digest}",
            f"reference:{self.identity.reference}",
            f"metrics:{','.join(sorted(compared))}",
        )
        detail = (
            f"all {len(compared)} oracle metric(s) within declared tolerance"
            if passed
            else f"oracle comparison failed: {failures}"
        )
        return ValidationCheck(
            name=name,
            outcome=ValidationOutcome.PASS if passed else ValidationOutcome.FAIL,
            detail=detail,
            establishes=self.identity.establishes if passed else None,
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
