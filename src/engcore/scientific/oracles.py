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

# Repository-owned authority pins. This mapping is intentionally immutable.
# Admission requires a source change/review: production callers receive no
# registration API because the party asking for a validation level must not
# also be the party that grants itself authority.
#
# Key: (oracle_id, version)
# Value: {"kind": <OracleKind.value>, "evidence_digest": <sha256>,
#         "reference": <stable external reference>, "declared_by": <prose>}
_TRUSTED_ORACLE_DECLARATIONS: Mapping[tuple[str, str], Mapping[str, str]] = (
    MappingProxyType(
        {
            ("nafems.p18.t3.transient_heat_1d", "1"): MappingProxyType(
                {
                    "kind": OracleKind.BENCHMARK_DATASET.value,
                    "evidence_digest": "eb6e2daf9a6ad6a957576fc9d3462175edf0525ebeea68bcd74778868d875328",
                    "reference": (
                        "NAFEMS P18.T3, The Standard NAFEMS Benchmarks, Rev. 3 (1990); "
                        "public reproductions: Altair SimSolid SS-V:3070 and MOOSE nafems_t3_verif"
                    ),
                    "declared_by": (
                        "Forge Sprint 2 external-evidence review: target and case "
                        "conditions cross-checked against public NAFEMS T3 reproductions; "
                        "the 0.05 K comparison envelope is recording precision, not a "
                        "claimed NAFEMS acceptance threshold"
                    ),
                }
            )
        }
    )
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
        # R-53 (I-26): the identity of an observation is its metric AT ITS
        # OPERATING POINT. Requiring the metric alone to be unique meant one
        # reading at two points was a duplicate, so an evidence set could not
        # hold the shape its own name describes -- a set of readings taken at
        # operating points -- and every comparison against such a dataset was
        # lost. A metric at two points is two observations, which is what the
        # observation record already says about itself.
        keys = [
            (item.metric, tuple(sorted((k, v.units, v.magnitude) for k, v in item.conditions.items())))
            for item in observations
        ]
        if len(set(keys)) != len(keys):
            raise ScientificValidationError(
                "oracle evidence must not repeat one metric at one operating point: two readings of the "
                "same metric at the same declared conditions are either a duplicate or a disagreement, "
                "and nothing here can say which"
            )
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

    def _binding_gap(
        self,
        predicted: Mapping[str, Quantity],
        stated: Mapping[str, Quantity],
        predicted_from: Any,
    ) -> tuple[str | None, str | None]:
        """R-49: ``(gap, contradiction)`` -- why no level may be awarded, and why nothing was compared.

        A MISSING binding is a weaker comparison: it happened, and no level may rest on it. A binding
        that CONTRADICTS the stated point is not a comparison at that point at all, so it is the second
        member and the check is NOT_RUN.

        The audited state: `predicted` is a plain mapping of numbers and the operating point is the
        `conditions=` ARGUMENT, so a prediction computed at 400 K passed -- and earned a level -- at a
        stated 300 K. Nothing tied either the numbers or the point to the record that produced them.

        A record cannot be forced into the existing signature without breaking every caller, so the
        binding is an added keyword and the LEVEL is what depends on it: the same shape this file already
        uses for oracle authority, and the shape batch 46 used at the inference boundary.
        """
        if predicted_from is None:
            return (
                "the prediction does not name the record it was computed from, so the operating point is "
                "an assertion about a mapping of numbers"
            ), None
        values = dict(getattr(predicted_from, "values", {}) or {})
        record_id = getattr(predicted_from, "result_id", None)
        for metric, value in predicted.items():
            stated_value = values.get(metric)
            if stated_value is None:
                return None, (
                    f"record {record_id!r} does not carry {metric!r}, so the compared number is not the "
                    f"one that record computed"
                )
            if not _same_operating_point(stated_value, value):
                return None, (
                    f"the compared {metric!r} is {value} and record {record_id!r} states {stated_value}"
                )
        provenance = getattr(predicted_from, "provenance", None)
        declared = dict(getattr(provenance, "inputs", {}) or {}) if provenance is not None else {}
        for key, value in stated.items():
            given = declared.get(key)
            if not isinstance(given, Quantity):
                return None, (
                    f"the operating point states {key!r} and record {record_id!r} does not declare it as "
                    f"an input, so nothing says the prediction was computed there"
                )
            if not _same_operating_point(given, value):
                return None, (
                    f"the operating point states {key} = {value} and record {record_id!r} was computed at "
                    f"{given}"
                )
        return None, None

    def compare(
        self,
        predicted: Mapping[str, Quantity],
        *,
        name: str = "external_oracle",
        conditions: Mapping[str, Quantity] | None = None,
        predicted_from: Any = None,
    ) -> ValidationCheck:
        """Compare every observation; only pinned evidence may award a level.

        CORE-009: an observation that declares its operating point is compared only at that point. If ``conditions``
        omits a declared condition or states another value, no comparison is made: the check is NOT_RUN and awards no
        level. It is not FAIL, because a comparison at other conditions is not evidence against the model.
        """
        stated = dict(conditions or {})
        # R-53 (I-26): POINT BY POINT. The rule used to be that one stated
        # point had to match EVERY observation, so a two-point dataset was
        # always NOT_RUN. An observation is comparable when the stated point
        # states each condition it declares, at that value; the others are
        # recorded as observed elsewhere, which is what they are.
        #
        # R-49: and a stated condition the observation does NOT declare stops
        # that comparison too. The audited case is an observation declared at T
        # only, compared against a prediction stated at P = 50 bar: the
        # evidence says nothing about 50 bar, so a comparison there is a claim
        # about a point the evidence does not describe.
        elsewhere: list[str] = []
        comparable: list[OracleObservation] = []
        undeclared_point = False
        for observation in self.observations:
            reasons: list[str] = []
            for key, value in observation.conditions.items():
                if key not in stated:
                    reasons.append(f"{observation.metric}:{key} not stated (observed at {value})")
                elif not _same_operating_point(value, stated[key]):
                    reasons.append(f"{observation.metric}:{key} is {stated[key]}, observed at {value}")
            if observation.conditions:
                for key, value in stated.items():
                    if key not in observation.conditions:
                        reasons.append(
                            f"{observation.metric}:{key} is stated as {value} and the evidence declares "
                            f"no {key}, so it says nothing about that point"
                        )
            else:
                # R-49: every record written before the conditions field
                # existed compares anywhere, including at a point it says
                # nothing about. The comparison stands -- refusing it would
                # delete evidence -- and no LEVEL may rest on it, because a
                # level is a claim that the model was validated SOMEWHERE and
                # this record does not say where. That is also why the
                # stated-but-undeclared rule above is skipped here: with NO
                # declared point there is nothing to contradict, and applying
                # it would turn every legacy record into a refusal.
                undeclared_point = True
            if reasons:
                elsewhere.extend(reasons)
                continue
            comparable.append(observation)
        if not comparable:
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
        # Only a metric the PREDICTION does not carry makes the comparison
        # incomplete. An observation at another operating point is the ordinary
        # multi-point case and is reported, not counted as a gap: a dataset is
        # a set of readings at points, and comparing at one of them is exactly
        # what this record is for.
        not_compared: list[str] = []
        compared: list[str] = []
        for observation in comparable:
            actual = predicted.get(observation.metric)
            if actual is None:
                # R-53 (I-26): an absence is not a disagreement. This used to
                # be recorded as a failure, so the check was FAIL and
                # `derive_verdict` read NOT_SUPPORTED -- evidence AGAINST the
                # model built out of a comparison nobody made. The same reading
                # CORE-009 and CORE-013 already moved to NOT_RUN, twice.
                not_compared.append(f"{observation.metric}:not predicted")
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

        passed = not failures and bool(compared)
        # R-53: a comparison that was MADE and disagreed is a failure; anything
        # not compared leaves the check NOT_RUN once nothing failed, and awards
        # no level either way.
        incomplete = bool(not_compared)
        other_points = list(elsewhere)
        summary_residual = residual_ratio if residual_ratio != float("inf") else 2.0
        authority_gap = self.identity.authority_gap
        # R-49: what the prediction is bound to, and what the evidence says
        # about where it was observed, both gate the LEVEL -- the same way this
        # record already gates it on oracle authority.
        binding_gap, binding_contradiction = self._binding_gap(predicted, stated, predicted_from)
        if binding_gap is None and undeclared_point:
            binding_gap = (
                "at least one observation declares no operating point, so the comparison is not tied to a "
                "point the model was validated at"
            )
        gaps = [gap for gap in (authority_gap, binding_gap) if gap is not None]
        if binding_contradiction is not None:
            # A NAMED record that was computed somewhere else, or does not
            # carry these numbers, is not a weaker comparison: it is not a
            # comparison at the stated point at all.
            return ValidationCheck(
                name=name,
                outcome=ValidationOutcome.NOT_RUN,
                detail=f"no comparison made: {binding_contradiction}",
                evidence=(f"oracle:{self.identity.oracle_id}@{self.identity.version}",
                          f"sha256:{self.identity.evidence_digest}"),
            )
        trusted_pass = passed and not incomplete and not gaps
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
            (
                "oracle-binding:the prediction names the record it came from"
                if binding_gap is None
                else f"oracle-binding:withheld:{binding_gap}"
            ),
        )
        if passed and not incomplete and not gaps:
            detail = (
                f"all {len(compared)} oracle metric(s) within declared tolerance; "
                "content digest verified and oracle identity is repository-pinned"
                + (f"; observations at other points: {other_points}" if other_points else "")
            )
        elif passed and not incomplete:
            detail = (
                f"all {len(compared)} oracle metric(s) within declared tolerance, "
                f"but no validation level is awarded: {'; '.join(gaps)}"
            )
        elif passed:
            detail = (
                f"{len(compared)} oracle metric(s) within declared tolerance and "
                f"{len(not_compared)} not compared, so the comparison is incomplete and awards no level: "
                f"{not_compared}"
                + (f"; observations at other points: {other_points}" if other_points else "")
                + (f"; also {'; '.join(gaps)}" if gaps else "")
            )
        else:
            detail = f"oracle comparison failed: {failures}"
        if failures:
            outcome = ValidationOutcome.FAIL
        elif incomplete:
            outcome = ValidationOutcome.NOT_RUN
        else:
            outcome = ValidationOutcome.PASS
        return ValidationCheck(
            name=name,
            outcome=outcome,
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
