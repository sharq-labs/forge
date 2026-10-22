"""Shared contract pieces of the world layer: refusals, the one digest rule, typed record references and value codecs.

The digest rule is not new: it is the strict Gen1 encoder (:func:`engcore.mind.repsem.canonical_bytes`: sorted keys,
compact separators, ASCII escapes, NaN refused) followed by SHA-256.  A foreign record's own digest is embedded
verbatim and never recomputed here.

Every unit-bearing value is compared, and enters an identity, at the repository's identity precision
(:func:`~engcore.scientific.units.quantity.canonical_magnitude`, 12 significant digits) in the BASE unit of its
dimension.  The base unit is a ratio scale, so ``2000 mA`` is ``2 A`` and ``10 min`` is ``600 s``, and two spellings of
one point on an offset (affine) scale agree; comparing in the offset scale itself would lose relative precision near
its zero.  Nothing is rounded to a level or clamped.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from engcore.mind.repsem import canonical_bytes
from engcore.scientific import Quantity, ScientificCoreError
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue, decode_value, encode_value
from engcore.scientific.units.quantity import base_unit, canonical_magnitude, normalize_unit

SCHEMA_PREFIX = "forge.mind.world."
SOFTWARE_VERSION = "engcore.mind.world/1.0.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class WorldRefused(ValueError):
    """A world, action space or proposal that is incomplete, inconsistent, inferred or out of contract."""


class StaleProposal(WorldRefused):
    """A proposal checked against a world revision it was not made for: evidence stays bound to its context."""


class ProposalRefused(WorldRefused):
    """An external proposal that carries authority it does not have, or a value that is not a typed scientific value."""


def schema(name: str, version: int = 1) -> str:
    return f"{SCHEMA_PREFIX}{name}/{version}"


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def expect_schema(found: Any, expected: str) -> None:
    if found != expected:
        raise WorldRefused(f"not a {expected} record: {found!r}")


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise WorldRefused(f"{field} must be a non-empty string without surrounding whitespace, got {value!r}")
    return value


def names(values: Iterable[Any], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WorldRefused(f"{field} must be a sequence of names, not one string")
    out = tuple(text(v, field) for v in values)
    if len(set(out)) != len(out):
        raise WorldRefused(f"{field} repeats a name: {sorted(n for n in set(out) if out.count(n) > 1)}")
    return tuple(sorted(out))


def unit(value: Any, field: str) -> str:
    try:
        return normalize_unit(text(value, field))
    except ScientificCoreError as exc:
        raise WorldRefused(f"{field}: {exc}") from None


# ---- typed references to the records a world is a view over ------------------------------------------------------------
class RecordKind(str, Enum):
    """The owner record a reference points at.  Each member names an existing record type; nothing new is minted.

    ``SYNTHETIC_FIXTURE`` marks a contract-test fixture: it is never evidence and never an owner record."""

    MEASUREMENT_OBSERVATION = "measurement_observation"    # scientific.measurements.CalibratedMeasurementObservation
    DATASET_OBSERVATION = "dataset_observation"            # claims.measurement_dataset.DatasetObservation
    EVIDENCE_ITEM = "evidence_item"                        # claims.falsification.EvidenceItem (released observation)
    SYSTEM_STATE = "system_state"                          # system_runtime.SystemState
    TWIN_REVISION = "twin_revision"                        # systems.TwinRevision
    BELIEF_SNAPSHOT = "belief_snapshot"                    # sria.decision.BeliefSnapshot
    PROVIDER_RECORD = "provider_record"                    # providers.records.ProviderExecutionRecord
    SCENARIO = "scenario"                                  # scenarios.ScenarioSpecification (protocol schedule)
    EXPERIMENT_CONTEXT = "experiment_context"              # scientific.measurements.ExperimentContext
    SYSTEM_DEFINITION = "system_definition"                # systems.topology.SystemDefinition / ComponentInstance
    INSTRUMENT = "instrument"                              # scientific.measurements.InstrumentIdentity
    BUDGET_LEDGER = "budget_ledger"                        # sria.campaign.BudgetLedger
    PROBLEM_SPECIFICATION = "problem_specification"        # the declared problem (e.g. a repsem / Gen1 problem digest)
    SYNTHETIC_FIXTURE = "synthetic_fixture"                # contract fixture; never evidence


REFERENCE_SCHEMA = schema("record_ref")


@dataclass(frozen=True, order=True)
class RecordRef:
    """A pointer to an owner record: its kind and its digest (64-hex), embedded verbatim and never recomputed here.

    A synthetic fixture reference may be a readable token instead of a digest, because there is no record."""

    kind: RecordKind
    ref: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", RecordKind(self.kind))
        except ValueError:
            raise WorldRefused(f"unknown record kind {self.kind!r}") from None
        if self.kind is RecordKind.SYNTHETIC_FIXTURE:
            text(self.ref, "synthetic fixture reference")
        elif not isinstance(self.ref, str) or not HEX64.match(self.ref):
            raise WorldRefused(f"a {self.kind.value} reference is the record's 64-hex digest, got {self.ref!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REFERENCE_SCHEMA, "kind": self.kind.value, "ref": self.ref}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RecordRef":
        expect_schema(payload.get("schema"), REFERENCE_SCHEMA)
        return cls(RecordKind(payload["kind"]), payload["ref"])


# ---- typed values ------------------------------------------------------------------------------------------------------
def is_value(value: Any) -> bool:
    return type(value) in (Quantity, IntegerValue, BooleanValue, CategoricalValue)


def require_value(value: Any, field: str) -> Any:
    """A typed scientific value; a bare number, string or bool is never interpreted."""
    if not is_value(value):
        raise WorldRefused(f"{field} must be a typed scientific value (Quantity, IntegerValue, BooleanValue or "
                           f"CategoricalValue), not {type(value).__name__}")
    return value


def require_plain_value(value: Any, field: str) -> Any:
    """A typed value that asserts nothing beyond itself: a proposer cannot attach a vocabulary (a domain claim)."""
    require_value(value, field)
    if isinstance(value, CategoricalValue) and value.vocabulary:
        raise WorldRefused(f"{field}: a proposed category carries no vocabulary (the domain is the world's)")
    if not isinstance(value, Quantity) and getattr(value, "description", ""):
        raise WorldRefused(f"{field}: a proposed value carries no description")
    return value


def value_payload(value: Any) -> dict[str, Any]:
    return encode_value(require_value(value, "value"))


def value_from(payload: Any) -> Any:
    return decode_value(payload)


def magnitude_key(value: Quantity) -> float:
    """The identity magnitude of a quantity: canonical, in the base (ratio-scale) unit of its dimension."""
    return canonical_magnitude(value, base_unit(value.units))


def value_key(value: Any) -> Any:
    """The identity of a typed value: a canonical base-unit magnitude for a quantity, the token otherwise."""
    if isinstance(value, Quantity):
        return {"magnitude": magnitude_key(value), "units": base_unit(value.units)}
    if isinstance(value, IntegerValue):
        return {"integer": value.value}
    if isinstance(value, BooleanValue):
        return {"boolean": value.value}
    if isinstance(value, CategoricalValue):
        return {"category": value.value}
    raise WorldRefused(f"not a typed scientific value: {type(value).__name__}")


def same_value(a: Any, b: Any) -> bool:
    """Equality at identity precision; dimensionally incompatible quantities are simply not equal."""
    if type(a) is not type(b):
        return False
    if isinstance(a, Quantity) and not a.is_compatible_with(b.units):
        return False
    return value_key(a) == value_key(b)


__all__ = [
    "HEX64", "ProposalRefused", "RecordKind", "RecordRef", "SCHEMA_PREFIX", "SOFTWARE_VERSION", "StaleProposal",
    "WorldRefused", "digest", "expect_schema", "is_value", "magnitude_key", "names", "require_plain_value",
    "require_value", "same_value", "schema", "text", "unit", "value_from", "value_key", "value_payload",
]
