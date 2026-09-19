"""Phase 4 -- evidence beyond simulation: benchmark, measurement and literature, ingested conservatively.

SRIA's :class:`~engcore.sria.evidence.Evidence` was always source-agnostic; only
simulation had an ingestion path. This module is the ingestion path for the
other three source classes. It turns an external record into SRIA evidence
*without pretending it is simulation evidence*, and it decides the record's
**standing** from the record's own content and a trust pin -- never from the
caller calling it a "measurement":

``ADMISSIBLE``
    repository-pinned (its digest is in the trusted registry, or -- for a
    benchmark -- its oracle content reproduces the repository pin), bound to
    the claim's QOI in the claim's dimension, applicable at the claim's exact
    stated conditions, and carrying a quantified uncertainty of the right
    source (a benchmark's comparison tolerance stands in for it). Admissible
    external evidence may be compared with the claim's value; it is **not** a
    validation level. Only the credibility report's issuer-gated checks award
    levels.
``WEAK``
    identifiable, but short of admissible: not pinned (a caller's statement),
    conditions not stated, or uncertainty UNKNOWN. Recorded and shown; bears on
    nothing.
``UNUSABLE``
    about another quantity or dimension, at a mismatched operating point, or a
    pin whose content does not reproduce.

The trusted registry has no registration API. Production pins are curated
from evidence already frozen in the repository's model-to-measurement round.
They remain ordinary evidence records: a pin establishes identity and curation,
not a validation level, and a caller still has to present a record whose
operating conditions apply to the claim. A test or an organization may supply
another :class:`TrustedExternalRegistry` explicitly, and the assessment
records which registry (by digest) judged each record.

Literature is held to the same bar as measurement: a citation is not a
validation, and a reported value with no reported uncertainty is WEAK.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.serialization import schema_string
from ..scientific.units.quantity import Quantity, dimensionality
from ..sria.evidence import ClaimBinding, ClaimType, Evidence, SourceClass
from ..sria.uncertainty import (
    CHANNEL_OF_SOURCE,
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyDeclaration,
)
from ._records import (
    require_identifier,
    require_keys,
    require_list,
    require_mapping,
    require_schema_exact,
    require_text,
    tagged_digest,
)
from .errors import ClaimContractError
from .oracles import OracleApplicability, OracleMatch, applicability

MEASUREMENT_SCHEMA = schema_string("claim_measurement_record")
LITERATURE_SCHEMA = schema_string("claim_literature_record")
_MEASUREMENT_TAG = "crafty.claims.measurement/1"
_LITERATURE_TAG = "crafty.claims.literature/1"
_REGISTRY_TAG = "crafty.claims.external_registry/1"


class ExternalStanding(str, Enum):
    ADMISSIBLE = "admissible"
    WEAK = "weak"
    UNUSABLE = "unusable"


def _conditions(raw: Any, field_name: str) -> dict[str, Quantity]:
    out = {}
    for key, value in require_mapping(raw, field=field_name).items():
        if isinstance(value, Mapping):
            value = Quantity.from_dict(value)
        if not isinstance(value, Quantity):
            raise ClaimContractError(f"{field_name}.{key} must be a Quantity")
        out[require_text(key, field=f"{field_name} key")] = value
    return dict(sorted(out.items()))


def _uncertainty(raw: Any) -> Uncertainty:
    if isinstance(raw, Uncertainty):
        return raw
    try:
        return Uncertainty.from_dict(require_mapping(raw, field="uncertainty"))
    except Exception as exc:
        raise ClaimContractError(f"uncertainty is not a readable record: {exc}") from exc


@dataclass(frozen=True)
class MeasurementRecord:
    """A measured value of one quantity, with what a reader needs to judge it."""

    quantity: str
    value: Quantity
    uncertainty: Uncertainty
    calibration_ref: str
    provenance_ref: str
    conditions: Mapping[str, Quantity]
    dataset_version: str
    observed_at: str | None = None
    independence_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", require_identifier(self.quantity, field="measurement.quantity"))
        if not isinstance(self.value, Quantity):
            raise ClaimContractError("measurement.value must be a Quantity")
        object.__setattr__(self, "uncertainty", _uncertainty(self.uncertainty))
        for label in ("calibration_ref", "provenance_ref", "dataset_version"):
            object.__setattr__(self, label, require_text(getattr(self, label), field=f"measurement.{label}"))
        if self.observed_at is not None:
            object.__setattr__(self, "observed_at", require_text(self.observed_at, field="measurement.observed_at"))
        object.__setattr__(self, "conditions", _conditions(self.conditions, "measurement.conditions"))
        object.__setattr__(self, "independence_roots", tuple(sorted({require_text(r, field="measurement.root") for r in self.independence_roots})))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEASUREMENT_SCHEMA,
            "quantity": self.quantity,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "calibration_ref": self.calibration_ref,
            "provenance_ref": self.provenance_ref,
            "conditions": {k: v.to_dict() for k, v in self.conditions.items()},
            "dataset_version": self.dataset_version,
            "observed_at": self.observed_at,
            "independence_roots": list(self.independence_roots),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_MEASUREMENT_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeasurementRecord":
        payload = require_mapping(payload, field="measurement")
        keys = ("schema", "quantity", "value", "uncertainty", "calibration_ref", "provenance_ref", "conditions",
                "dataset_version", "observed_at", "independence_roots")
        require_keys(payload, required=keys, record="measurement")
        require_schema_exact(payload, MEASUREMENT_SCHEMA, record="measurement")
        return cls(
            payload["quantity"], Quantity.from_dict(payload["value"]), _uncertainty(payload["uncertainty"]),
            payload["calibration_ref"], payload["provenance_ref"], payload["conditions"], payload["dataset_version"],
            payload["observed_at"], tuple(require_list(payload["independence_roots"], field="independence_roots")),
        )


@dataclass(frozen=True)
class LiteratureRecord:
    """A claim extracted from a stable reference. Carries its citation; is never a validation by itself."""

    citation_id: str
    extracted_claim: str
    quantity: str
    value: Quantity | None
    uncertainty: Uncertainty
    conditions: Mapping[str, Quantity]
    extracted_by: str
    extraction_method: str

    def __post_init__(self) -> None:
        for label in ("citation_id", "extracted_claim", "extracted_by", "extraction_method"):
            object.__setattr__(self, label, require_text(getattr(self, label), field=f"literature.{label}"))
        object.__setattr__(self, "quantity", require_identifier(self.quantity, field="literature.quantity"))
        if self.value is not None and not isinstance(self.value, Quantity):
            raise ClaimContractError("literature.value must be a Quantity or None")
        object.__setattr__(self, "uncertainty", _uncertainty(self.uncertainty))
        object.__setattr__(self, "conditions", _conditions(self.conditions, "literature.conditions"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LITERATURE_SCHEMA,
            "citation_id": self.citation_id,
            "extracted_claim": self.extracted_claim,
            "quantity": self.quantity,
            "value": None if self.value is None else self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "conditions": {k: v.to_dict() for k, v in self.conditions.items()},
            "extracted_by": self.extracted_by,
            "extraction_method": self.extraction_method,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_LITERATURE_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiteratureRecord":
        payload = require_mapping(payload, field="literature")
        keys = ("schema", "citation_id", "extracted_claim", "quantity", "value", "uncertainty", "conditions",
                "extracted_by", "extraction_method")
        require_keys(payload, required=keys, record="literature")
        require_schema_exact(payload, LITERATURE_SCHEMA, record="literature")
        return cls(
            payload["citation_id"], payload["extracted_claim"], payload["quantity"],
            None if payload["value"] is None else Quantity.from_dict(payload["value"]),
            _uncertainty(payload["uncertainty"]), payload["conditions"], payload["extracted_by"], payload["extraction_method"],
        )


@dataclass(frozen=True)
class TrustedPin:
    record_digest: str
    source_class: SourceClass
    curator: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {"record_digest": self.record_digest, "source_class": self.source_class.value, "curator": self.curator, "rationale": self.rationale}


@dataclass(frozen=True)
class TrustedExternalRegistry:
    """Record digests a curator has reviewed. No registration API: it is constructed whole, and identified by digest."""

    pins: tuple[TrustedPin, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pins", tuple(sorted(self.pins, key=lambda p: p.record_digest)))

    def pin_for(self, digest: str, source_class: SourceClass) -> TrustedPin | None:
        return next((p for p in self.pins if p.record_digest == digest and p.source_class is source_class), None)

    @property
    def digest(self) -> str:
        return tagged_digest(_REGISTRY_TAG, [p.to_dict() for p in self.pins])


def _production_external_catalog() -> tuple[MeasurementRecord | LiteratureRecord, ...]:
    """Small, auditable production catalog backed by frozen repository evidence.

    The battery points are HELD_OUT observations from two different LiFePO4
    cells in S-OCV (DOI 10.21227/651q-8v82).  Their expanded k=2 intervals are
    the preregistered measurement budgets recorded in
    benchmarks/model_measurement_validation/VALIDATION_RESULTS.json.  They are
    deliberately not auto-applied to arbitrary cells: subject identity is
    carried in provenance/independence roots and the caller must explicitly
    offer the exact record it intends to use.

    The literature/reference record is the 100 degC Pt100 table point from the
    SHA-256-pinned DIN 43760 / IEC 751 transcription used by the same evidence
    round.  Its +/-0.005 ohm interval is half the last printed digit.  The
    record says exactly that; it does not claim specimen uncertainty.
    """
    batt_001_soc04 = MeasurementRecord(
        quantity="terminal_voltage",
        value=Quantity(3.299, "volt"),
        uncertainty=Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(3.2968452062743734, "volt"),
            upper=Quantity(3.3011547937256265, "volt"),
            source="S-OCV DOI 10.21227/651q-8v82; BATT_001 charge-conditioned SOC 0.4",
            method="expanded k=2 instrument+SOC+temperature+relaxation budget frozen in VALIDATION_RESULTS.json",
            notes="held-out published measurement; not a calibration row",
            source_kind=UncertaintySource.MEASUREMENT,
        ),
        calibration_ref="model_measurement_validation:S-OCV:uncertainty-budget-v1",
        provenance_ref=(
            "S-OCV:sha256:9b8c541675256c08c24cc6ebeb486a46"
            "d07c533a70bf4dabcca4955dba90e08a:BATT_001:soc=0.4:charge:24h"
        ),
        conditions={
            "load.state_of_charge": Quantity(0.4, "dimensionless"),
            "load.discharge_current": Quantity(0.0, "ampere"),
        },
        dataset_version="DOI:10.21227/651q-8v82:v1",
        independence_roots=(
            "dataset:10.21227/651q-8v82",
            "cell:BATT_001",
            "trace:BATT_001:charge:soc=0.4:24h",
        ),
    )
    batt_002_soc05 = MeasurementRecord(
        quantity="terminal_voltage",
        value=Quantity(3.302, "volt"),
        uncertainty=Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(3.301143766387018, "volt"),
            upper=Quantity(3.302856233612982, "volt"),
            source="S-OCV DOI 10.21227/651q-8v82; BATT_002 charge-conditioned SOC 0.5",
            method="expanded k=2 instrument+SOC+temperature+relaxation budget frozen in VALIDATION_RESULTS.json",
            notes="held-out replicate-cell published measurement",
            source_kind=UncertaintySource.MEASUREMENT,
        ),
        calibration_ref="model_measurement_validation:S-OCV:uncertainty-budget-v1",
        provenance_ref=(
            "S-OCV:sha256:9b8c541675256c08c24cc6ebeb486a46"
            "d07c533a70bf4dabcca4955dba90e08a:BATT_002:soc=0.5:charge:24h"
        ),
        conditions={
            "load.state_of_charge": Quantity(0.5, "dimensionless"),
            "load.discharge_current": Quantity(0.0, "ampere"),
        },
        dataset_version="DOI:10.21227/651q-8v82:v1",
        independence_roots=(
            "dataset:10.21227/651q-8v82",
            "cell:BATT_002",
            "trace:BATT_002:charge:soc=0.5:24h",
        ),
    )
    pt100_100c = LiteratureRecord(
        citation_id=(
            "pt100rtd:d09fc50e9cbe04742273b1b6c023fb23863d72f"
            "de63d4bdbab0ae2757a0be693:DIN43760-IEC751"
        ),
        extracted_claim=(
            "The pinned Pt100 reference table gives 138.51 ohm at 100 degC."
        ),
        quantity="resistance",
        value=Quantity(138.51, "ohm"),
        uncertainty=Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(138.505, "ohm"),
            upper=Quantity(138.515, "ohm"),
            source="DIN 43760 / IEC 751 table transcription",
            method="half of the 0.01 ohm printed table increment",
            notes=(
                "reference-table quantisation only; this is not uncertainty "
                "of an individual platinum thermometer specimen"
            ),
        ),
        conditions={"temperature": Quantity(100.0, "degC")},
        extracted_by="forge:model_measurement_validation",
        extraction_method=(
            "direct indexed read of the SHA-256-pinned 1051-point table; "
            "anchor values and Callendar-Van Dusen consistency were checked "
            "in the frozen evidence round"
        ),
    )
    return (batt_001_soc04, batt_002_soc05, pt100_100c)


PRODUCTION_EXTERNAL_RECORDS = _production_external_catalog()

#: Repository-owned trust pins.  The curated records above are still subject
#: to applicability and uncertainty checks on every claim; a pin never awards
#: a validation level by itself.
PRODUCTION_EXTERNAL_REGISTRY = TrustedExternalRegistry(
    tuple(
        TrustedPin(
            record_digest=record.digest,
            source_class=(
                SourceClass.MEASUREMENT
                if isinstance(record, MeasurementRecord)
                else SourceClass.LITERATURE
            ),
            curator="forge:model_measurement_validation",
            rationale=(
                "record derived from the repository-frozen evidence provenance, "
                "held-out/independent measurement split or pinned reference table, "
                "with the uncertainty statement carried in the record"
            ),
        )
        for record in PRODUCTION_EXTERNAL_RECORDS
    )
)


@dataclass(frozen=True)
class ExternalEvidenceAssessment:
    source_class: SourceClass
    record_digest: str
    record: Mapping[str, Any]
    standing: ExternalStanding
    reasons: tuple[dict[str, str], ...]
    evidence: Evidence | None = field(default=None, compare=False)
    comparison: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class.value,
            "record_digest": self.record_digest,
            "record": dict(self.record),
            "standing": self.standing.value,
            "reasons": [dict(r) for r in self.reasons],
            "evidence_record_hash": None if self.evidence is None else self.evidence.record_hash,
            "comparison": None if self.comparison is None else dict(self.comparison),
            "is_validation_level": False,
        }


def _half_widths(record: Uncertainty, value: Quantity) -> tuple[float, float] | None:
    """An INTERVAL's distances from ``value``; anything else (UNKNOWN, STANDARD without a declared k) is not usable."""
    if record.kind is not UncertaintyKind.INTERVAL:
        return None
    lo = value.magnitude - record.lower.to(value.units).magnitude
    hi = record.upper.to(value.units).magnitude - value.magnitude
    if lo < 0 or hi < 0:
        return None
    return lo, hi


def compare_with_simulation(external_value: Quantity, external_halves: tuple[float, float] | None,
                            simulated: Quantity, simulated_halves: tuple[float, float] | None) -> dict[str, Any]:
    """Whether two values agree within their stated intervals. Undecided when either interval is unknown."""
    if dimensionality(external_value.units) != dimensionality(simulated.units):
        return {"outcome": "not_comparable", "detail": "different dimensions"}
    difference = simulated.magnitude - external_value.to(simulated.units).magnitude
    if external_halves is None or simulated_halves is None:
        return {"outcome": "undecided", "difference": difference,
                "detail": "an unquantified interval is not zero; agreement cannot be decided"}
    # The intervals overlap iff the difference lies within the sum of the facing half-widths.
    allowed = (simulated_halves[0] + external_halves[1]) if difference > 0 else (simulated_halves[1] + external_halves[0])
    outcome = "consistent" if abs(difference) <= allowed else "inconsistent"
    return {"outcome": outcome, "difference": difference, "allowed": allowed,
            "detail": "intervals compared by linear sum of the facing half-widths"}


def _standing(problems_unusable: list[dict[str, str]], problems_weak: list[dict[str, str]]) -> ExternalStanding:
    if problems_unusable:
        return ExternalStanding.UNUSABLE
    if problems_weak:
        return ExternalStanding.WEAK
    return ExternalStanding.ADMISSIBLE


def _evidence(source_class: SourceClass, *, evidence_id: str, quantity: str, value: Quantity, payload: Mapping[str, Any],
              channels: Mapping[Any, Uncertainty], provenance_ref: str, pack: str, context_ref: str, roots: Iterable[str]) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_class=source_class,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref=quantity),
        claim_payload={"value": value.magnitude, "units": str(value.units), **payload},
        uncertainty=UncertaintyDeclaration(
            subject_model=SubjectModel.OBSERVATION_MODEL,
            discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.UNKNOWN, rationale="an external observation carries no model-form declaration"),
            channels=dict(channels),
            notes=f"ingested {source_class.value} evidence; undeclared channels remain UNKNOWN",
        ),
        provenance_ref=provenance_ref,
        domain_pack_ref=pack,
        context_ref=context_ref,
        source_refs=tuple(roots),
        source_closure_complete=bool(tuple(roots)),
    )


def _common_problems(quantity: str, value: Quantity | None, conditions: Mapping[str, Quantity], claim: Any) -> tuple[list, list]:
    unusable, weak = [], []
    if quantity != claim.qoi.name:
        unusable.append({"reason": f"about {quantity!r}, not the claim's QOI {claim.qoi.name!r}", "source": "/record/quantity"})
    if value is not None and dimensionality(value.units) != claim.qoi.dimension:
        unusable.append({"reason": f"value is [{dimensionality(value.units)}], the QOI is [{claim.qoi.dimension}]", "source": "/record/value"})
    state, mismatched, unstated = applicability(conditions, dict(claim.supplied_inputs))
    if state is OracleApplicability.MISMATCH:
        unusable.append({"reason": f"observed at another operating point: {list(mismatched)}", "source": "/record/conditions"})
    elif state is OracleApplicability.UNKNOWN:
        weak.append({"reason": f"the claim does not state {list(unstated)}; applicability is unknown", "source": "/claim/operating_context"})
    if not conditions:
        weak.append({"reason": "the record states no operating conditions; applicability cannot be judged", "source": "/record/conditions"})
    return unusable, weak


def assess_measurement(record: MeasurementRecord, claim: Any, *, context_ref: str, trust: TrustedExternalRegistry,
                       simulated: tuple[Quantity, tuple[float, float] | None] | None = None) -> ExternalEvidenceAssessment:
    unusable, weak = _common_problems(record.quantity, record.value, record.conditions, claim)
    pin = trust.pin_for(record.digest, SourceClass.MEASUREMENT)
    if pin is None:
        weak.append({"reason": "not a curated, pinned measurement: a caller's statement is not evidence", "source": "/trust/pins"})
    u = record.uncertainty
    channels = {}
    if not u.is_quantified:
        weak.append({"reason": "measurement uncertainty is UNKNOWN; it is not zero", "source": "/record/uncertainty"})
    elif UncertaintySource(u.source_kind) is not UncertaintySource.MEASUREMENT:
        unusable.append({"reason": f"a measurement's uncertainty must be attributed to MEASUREMENT, not {UncertaintySource(u.source_kind).value}", "source": "/record/uncertainty/source_kind"})
    else:
        channels[CHANNEL_OF_SOURCE[UncertaintySource.MEASUREMENT]] = u
    standing = _standing(unusable, weak)
    evidence = None
    if standing is not ExternalStanding.UNUSABLE:
        evidence = _evidence(
            SourceClass.MEASUREMENT, evidence_id=f"measurement:{record.digest[:16]}", quantity=record.quantity, value=record.value,
            payload={"conditions": {k: v.to_dict() for k, v in record.conditions.items()}, "calibration_ref": record.calibration_ref,
                     "dataset_version": record.dataset_version, "observed_at": record.observed_at, "record_digest": record.digest},
            channels=channels, provenance_ref=record.provenance_ref, pack=f"measurement:{record.calibration_ref}",
            context_ref=context_ref, roots=record.independence_roots,
        )
    comparison = None
    if standing is ExternalStanding.ADMISSIBLE and simulated is not None:
        comparison = compare_with_simulation(record.value, _half_widths(u, record.value), *simulated)
    return ExternalEvidenceAssessment(SourceClass.MEASUREMENT, record.digest, record.to_dict(), standing, tuple(unusable + weak), evidence, comparison)


def assess_literature(record: LiteratureRecord, claim: Any, *, context_ref: str, trust: TrustedExternalRegistry,
                      simulated: tuple[Quantity, tuple[float, float] | None] | None = None) -> ExternalEvidenceAssessment:
    unusable, weak = _common_problems(record.quantity, record.value, record.conditions, claim)
    if record.value is None:
        weak.append({"reason": "the reference reports no value for the QOI; a qualitative statement decides nothing here", "source": "/record/value"})
    if trust.pin_for(record.digest, SourceClass.LITERATURE) is None:
        weak.append({"reason": "not a curated, pinned literature extraction", "source": "/trust/pins"})
    u = record.uncertainty
    if not u.is_quantified:
        weak.append({"reason": "the reference reports no quantified uncertainty; it is not zero", "source": "/record/uncertainty"})
    standing = _standing(unusable, weak)
    evidence = None
    if standing is not ExternalStanding.UNUSABLE and record.value is not None:
        channel = CHANNEL_OF_SOURCE.get(UncertaintySource(u.source_kind)) if u.is_quantified else None
        evidence = _evidence(
            SourceClass.LITERATURE, evidence_id=f"literature:{record.digest[:16]}", quantity=record.quantity, value=record.value,
            payload={"conditions": {k: v.to_dict() for k, v in record.conditions.items()}, "citation_id": record.citation_id,
                     "extracted_claim": record.extracted_claim, "record_digest": record.digest},
            channels={channel: u} if channel is not None else {}, provenance_ref=record.citation_id,
            pack=f"literature:{record.citation_id}", context_ref=context_ref, roots=(f"citation:{record.citation_id}",),
        )
    comparison = None
    if standing is ExternalStanding.ADMISSIBLE and simulated is not None:
        comparison = compare_with_simulation(record.value, _half_widths(u, record.value), *simulated)
    return ExternalEvidenceAssessment(SourceClass.LITERATURE, record.digest, record.to_dict(), standing, tuple(unusable + weak), evidence, comparison)


def assess_benchmark(match: OracleMatch, claim: Any, *, context_ref: str,
                     simulated: tuple[Quantity, tuple[float, float] | None] | None = None) -> ExternalEvidenceAssessment:
    """A trusted oracle's published target as BENCHMARK evidence about the QOI at the oracle's own conditions."""
    record = match.to_dict()
    digest = tagged_digest("crafty.claims.benchmark_observation/1", record)
    unusable, weak = [], []
    if not match.trusted:
        unusable.append({"reason": "the oracle's content does not reproduce the repository pin", "source": "/record/trusted"})
    if match.metric != claim.qoi.name:
        unusable.append({"reason": f"about {match.metric!r}, not {claim.qoi.name!r}", "source": "/record/metric"})
    if match.applicability is OracleApplicability.MISMATCH:
        unusable.append({"reason": f"the benchmark is at another operating point: {list(match.mismatched)}", "source": "/record/mismatched"})
    elif match.applicability is OracleApplicability.UNKNOWN:
        weak.append({"reason": f"the claim does not state {list(match.unstated)}", "source": "/record/unstated"})
    standing = _standing(unusable, weak)
    evidence = None
    if standing is not ExternalStanding.UNUSABLE:
        evidence = _evidence(
            SourceClass.BENCHMARK, evidence_id=f"benchmark:{match.oracle_id}@{match.version}:{match.metric}", quantity=match.metric,
            value=match.expected,
            payload={"conditions": {k: v.to_dict() for k, v in sorted(match.conditions.items())}, "oracle_digest": match.trusted_digest,
                     "acceptance_tolerance": match.tolerance.to_dict(), "reference": match.reference},
            # The acceptance tolerance is the oracle's comparison rule, not a quantified uncertainty of the
            # target: no channel is filed, and every channel stays UNKNOWN.
            channels={}, provenance_ref=f"oracle:{match.oracle_id}@{match.version}",
            pack=f"oracle:{match.oracle_id}@{match.version}", context_ref=context_ref,
            roots=(f"oracle:{match.oracle_id}@{match.trusted_digest}",),
        )
    comparison = None
    if standing is ExternalStanding.ADMISSIBLE and simulated is not None:
        tol = match.tolerance.magnitude_as_spread_in(match.expected.units)
        comparison = compare_with_simulation(match.expected, (tol, tol), *simulated)
        comparison["detail"] += "; the benchmark side uses the oracle's own acceptance tolerance"
    return ExternalEvidenceAssessment(SourceClass.BENCHMARK, digest, record, standing, tuple(unusable + weak), evidence, comparison)


def read_external_record(payload: Mapping[str, Any]) -> MeasurementRecord | LiteratureRecord:
    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema == MEASUREMENT_SCHEMA:
        return MeasurementRecord.from_dict(payload)
    if schema == LITERATURE_SCHEMA:
        return LiteratureRecord.from_dict(payload)
    raise ClaimContractError(f"an external evidence record is a measurement or literature record, not {schema!r}")


__all__ = [
    "PRODUCTION_EXTERNAL_RECORDS",
    "PRODUCTION_EXTERNAL_REGISTRY",
    "ExternalEvidenceAssessment",
    "ExternalStanding",
    "LiteratureRecord",
    "MeasurementRecord",
    "TrustedExternalRegistry",
    "TrustedPin",
    "assess_benchmark",
    "assess_literature",
    "assess_measurement",
    "compare_with_simulation",
    "read_external_record",
]
