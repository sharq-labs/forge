"""CORE-1 -- the structured scientific claim.

A result says ``final_temperature = 319.3 K``. A claim says *the final
temperature stays below 353.15 K, for this decision, at this evidence bar*.
The Scientific Core validates the first and had no record for the second;
``docs/scientific-core/scientific-claim-and-context-of-use.md`` set out why.
This module adds that record and nothing else.

What a claim is, and what it deliberately is not
------------------------------------------------
A :class:`ScientificClaim` is a **question with an answer condition**: a
quantity of interest, a comparison, a target, the inputs and operating context
it is about, the decision it serves and the evidence that decision requires.

It is not a model, a problem or a result. It carries **no equation, no model
id and no system name**: which capability can answer it is decided later by
routing over declared capabilities (:mod:`engcore.claims.capabilities`), and a
claim that named its own model would be a caller choosing its own evidence.

The comparison semantics are not re-invented. A claim's comparison *is* a
:class:`~engcore.scientific.ir.constraints.ConstraintDefinition` -- the Core's
audited ``metric OP bound [tolerance]`` record, whose offset-temperature and
strict/non-strict tolerance rules were fixed once (I-22, R-48) and are reused
here by construction (:meth:`ScientificClaim.constraint`).

The authority rules this record enforces
----------------------------------------
* **Caller assertions are not evidence.** ``assumptions`` and the
  ``discrepancy`` declaration are carried and bound into identity so the
  assessment can show them; nothing in this layer lets either grant a level.
* **No silent defaults.** Every scientifically meaningful field is required on
  read. The discrepancy declaration must be written even when it is
  ``UNKNOWN``; the uncertainty demand must be written even when it demands
  nothing. A reader that filled either in would be deciding the evidence bar.
* **The statement is not the claim.** ``statement`` keeps the caller's own
  words for the record and is excluded from scientific identity: natural
  language interpretation is not validation, and rewording a sentence must not
  make a different claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.capabilities import ScientificCapability
from ..scientific.errors import ScientificCoreError
from ..scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from ..scientific.results.immutable import freeze
from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import schema_string
from ..scientific.units.quantity import (
    Quantity,
    dimensionality,
    normalize_unit,
    require_spread_unit,
)
from ..sria.charter import TerminalDecision
from ..sria.uncertainty import DiscrepancyKind, ModelDiscrepancy, UncertaintyChannel
from ._records import (
    check_input_value,
    decode_input_value,
    decode_inputs,
    encode_inputs,
    require_bool,
    require_identifier,
    require_keys,
    require_list,
    require_mapping,
    require_path,
    require_schema_exact,
    require_text,
    tagged_digest,
)
from .errors import ClaimContractError
from .parameter_uq import InputUncertainty
from .policy import DecisionContext

CLAIM_SCHEMA = schema_string("scientific_claim")
QOI_SCHEMA = schema_string("claim_quantity_of_interest")
TARGET_SCHEMA = schema_string("claim_target")
DECISION_SCHEMA = schema_string("claim_decision_binding")
EVIDENCE_REQUIREMENT_SCHEMA = schema_string("claim_evidence_requirement")
UNCERTAINTY_DEMAND_SCHEMA = schema_string("claim_uncertainty_demand")
ASSUMPTION_SCHEMA = schema_string("claim_caller_assumption")

_IDENTITY_TAG = "crafty.claims.claim.identity/1"
_RECORD_TAG = "crafty.claims.claim.record/1"


class ClaimKind(str, Enum):
    """The two decidable shapes a claim may take.

    ``THRESHOLD``       ``qoi OP target`` with a strict or non-strict inequality.
    ``TOLERANCE_BAND``  ``|qoi - target| <= tolerance``.

    A request to *compute* a quantity without an answer condition is not a
    claim: it has no truth value, and SUPPORTED / CONTRADICTED would have
    nothing to mean. It is served by the system run tools.
    """

    THRESHOLD = "threshold"
    TOLERANCE_BAND = "tolerance_band"


_THRESHOLD_OPERATORS = frozenset(
    {
        ConstraintOperator.LESS_THAN,
        ConstraintOperator.LESS_EQUAL,
        ConstraintOperator.GREATER_THAN,
        ConstraintOperator.GREATER_EQUAL,
    }
)


class RequestedOutput(str, Enum):
    """What the caller wants reported back. Presentation only: not identity."""

    VERDICT = "verdict"
    QOI_VALUE = "qoi_value"
    MARGIN = "margin"
    UNCERTAINTY = "uncertainty"
    EXPLANATION = "explanation"


def _unit(value: Any, *, field_name: str) -> str:
    text = require_text(value, field=field_name)
    try:
        unit = normalize_unit(text)
        dimensionality(unit)
    except ScientificCoreError as exc:
        raise ClaimContractError(f"{field_name} {text!r} is not a unit: {exc}") from exc
    return unit


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuantityOfInterest:
    """Which quantity the claim is about, the unit it is stated in, and which instance.

    ``name`` is matched **exactly** against the quantity names capabilities
    declare they produce. ``units`` fixes the dimensional requirement: a
    capability producing the same name in another dimension is not a
    candidate. ``qualifiers`` select one instance when a capability produces
    the quantity once per element (``{"component_id": "R1"}``).
    """

    name: str
    units: str
    qualifiers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_identifier(self.name, field="qoi.name"))
        object.__setattr__(self, "units", _unit(self.units, field_name="qoi.units"))
        qualifiers = {}
        for key, value in require_mapping(self.qualifiers, field="qoi.qualifiers").items():
            qualifiers[require_identifier(key, field="qoi.qualifiers key")] = require_text(
                value, field=f"qoi.qualifiers.{key}"
            )
        object.__setattr__(self, "qualifiers", freeze(qualifiers))

    @property
    def dimension(self) -> str:
        return dimensionality(self.units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QOI_SCHEMA,
            "name": self.name,
            "units": self.units,
            "qualifiers": {key: self.qualifiers[key] for key in sorted(self.qualifiers)},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityOfInterest":
        payload = require_mapping(payload, field="qoi")
        require_keys(payload, required=("schema", "name", "units", "qualifiers"), record="qoi")
        require_schema_exact(payload, QOI_SCHEMA, record="qoi")
        return cls(name=payload["name"], units=payload["units"], qualifiers=payload["qualifiers"])


@dataclass(frozen=True)
class ClaimTarget:
    """The value the QOI is compared with: a literal quantity, or a named input.

    ``input_ref`` covers ``maximum stress < material yield stress``: the bound
    is itself an input of the claim, and naming it -- rather than copying its
    number -- keeps the comparison bound to the value the capability ran with.
    Exactly one of the two is set.
    """

    value: Quantity | None = None
    input_ref: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.input_ref is None):
            raise ClaimContractError(
                "a claim target is exactly one of a quantity value or an input_ref"
            )
        if self.value is not None and not isinstance(self.value, Quantity):
            raise ClaimContractError(
                "target.value must be a Quantity: a bound without a unit cannot be compared"
            )
        if self.input_ref is not None:
            object.__setattr__(self, "input_ref", require_path(self.input_ref, field="target.input_ref"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TARGET_SCHEMA,
            "value": None if self.value is None else self.value.to_dict(),
            "input_ref": self.input_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ClaimTarget":
        payload = require_mapping(payload, field="target")
        require_keys(payload, required=("schema", "value", "input_ref"), record="target")
        require_schema_exact(payload, TARGET_SCHEMA, record="target")
        raw = payload["value"]
        value = None
        if raw is not None:
            value = decode_input_value(raw, field="target.value")
            if not isinstance(value, Quantity):
                raise ClaimContractError("target.value must be a quantity record")
        return cls(value=value, input_ref=payload["input_ref"])


@dataclass(frozen=True)
class DecisionBinding:
    """The intended use: the terminal decision this claim's evidence is for.

    It maps one-to-one onto SRIA's :class:`~engcore.sria.charter.TerminalDecision`
    rather than duplicating it, so the assessment can build a real charter.
    """

    decision_id: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_text(self.decision_id, field="decision.decision_id"))
        object.__setattr__(self, "statement", require_text(self.statement, field="decision.statement"))

    def terminal_decision(self) -> TerminalDecision:
        return TerminalDecision(decision_id=self.decision_id, statement=self.statement)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": DECISION_SCHEMA, "decision_id": self.decision_id, "statement": self.statement}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionBinding":
        payload = require_mapping(payload, field="decision")
        require_keys(payload, required=("schema", "decision_id", "statement"), record="decision")
        require_schema_exact(payload, DECISION_SCHEMA, record="decision")
        return cls(decision_id=payload["decision_id"], statement=payload["statement"])


_LEVEL_ORDER = {level: index for index, level in enumerate(ValidationLevel)}


@dataclass(frozen=True)
class EvidenceRequirement:
    """The evidentiary levels the decision requires, in the Core's own vocabulary.

    Non-empty: a decision standard cannot be inferred. ``UNVERIFIED`` is the
    absence of a level and cannot be required. Stored in the enum's own order
    so the same set always has the same identity.
    """

    required_levels: tuple[ValidationLevel, ...]

    def __post_init__(self) -> None:
        raw = self.required_levels
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (tuple, list, frozenset, set)):
            raise ClaimContractError("evidence.required_levels must be a collection of ValidationLevel")
        try:
            levels = [ValidationLevel(item) for item in raw]
        except ValueError as exc:
            raise ClaimContractError(f"evidence.required_levels: unknown ValidationLevel ({exc})") from exc
        if not levels:
            raise ClaimContractError(
                "evidence.required_levels must name at least one level; a decision "
                "standard cannot be inferred"
            )
        if ValidationLevel.UNVERIFIED in levels:
            raise ClaimContractError("UNVERIFIED is the absence of a level and cannot be required")
        if len(set(levels)) != len(levels):
            raise ClaimContractError("evidence.required_levels contains a duplicate level")
        object.__setattr__(
            self, "required_levels", tuple(sorted(levels, key=_LEVEL_ORDER.__getitem__))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_REQUIREMENT_SCHEMA,
            "required_levels": [level.value for level in self.required_levels],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRequirement":
        payload = require_mapping(payload, field="evidence")
        require_keys(payload, required=("schema", "required_levels"), record="evidence")
        require_schema_exact(payload, EVIDENCE_REQUIREMENT_SCHEMA, record="evidence")
        return cls(required_levels=tuple(require_list(payload["required_levels"], field="evidence.required_levels")))


_CHANNEL_ORDER = {channel: index for index, channel in enumerate(UncertaintyChannel)}


@dataclass(frozen=True)
class UncertaintyDemand:
    """Which uncertainty the decision requires to be quantified, and how.

    ``required_channels`` uses SRIA's channel vocabulary. **Empty is a
    declaration, not a default**: it states that a point comparison is
    acceptable for this decision, and the assessment says so. A non-empty set
    means each named channel must be quantified with an attributed source, and
    an UNKNOWN channel makes the claim INSUFFICIENT_EVIDENCE -- never zero.

    ``coverage_factor`` is the ``k`` that turns a standard uncertainty into a
    half-width for the conformity decision. It is the caller's decision rule,
    so it is never chosen here: a STANDARD record met with no ``k`` declared
    leaves the claim undecided rather than borrowing a conventional 2.

    ``require_supported_discrepancy`` asks that model-form discrepancy be
    *supported* under SRIA's existing rule (``model_discrepancy_check``):
    UNKNOWN and an unsupported ZERO_DECLARED do not satisfy it.
    """

    required_channels: frozenset[UncertaintyChannel]
    coverage_factor: float | None
    require_supported_discrepancy: bool

    def __post_init__(self) -> None:
        raw = self.required_channels
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (tuple, list, frozenset, set)):
            raise ClaimContractError("uncertainty.required_channels must be a collection of channels")
        try:
            channels = [UncertaintyChannel(item) for item in raw]
        except ValueError as exc:
            raise ClaimContractError(f"uncertainty.required_channels: unknown channel ({exc})") from exc
        if len(set(channels)) != len(channels):
            raise ClaimContractError("uncertainty.required_channels contains a duplicate channel")
        object.__setattr__(self, "required_channels", frozenset(channels))
        if self.coverage_factor is not None:
            if isinstance(self.coverage_factor, bool) or not isinstance(self.coverage_factor, (int, float)):
                raise ClaimContractError("uncertainty.coverage_factor must be a number or null")
            k = float(self.coverage_factor)
            if not math.isfinite(k) or k <= 0.0:
                raise ClaimContractError("uncertainty.coverage_factor must be finite and positive")
            if not channels:
                raise ClaimContractError(
                    "uncertainty.coverage_factor is declared but no channel is required; "
                    "a decision rule for an uncertainty nobody asked for is not a declaration"
                )
            object.__setattr__(self, "coverage_factor", k)
        require_bool(self.require_supported_discrepancy, field="uncertainty.require_supported_discrepancy")

    @property
    def demands_quantification(self) -> bool:
        return bool(self.required_channels)

    def ordered_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(sorted(self.required_channels, key=_CHANNEL_ORDER.__getitem__))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_DEMAND_SCHEMA,
            "required_channels": [channel.value for channel in self.ordered_channels()],
            "coverage_factor": self.coverage_factor,
            "require_supported_discrepancy": self.require_supported_discrepancy,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyDemand":
        payload = require_mapping(payload, field="uncertainty")
        require_keys(
            payload,
            required=("schema", "required_channels", "coverage_factor", "require_supported_discrepancy"),
            record="uncertainty",
        )
        require_schema_exact(payload, UNCERTAINTY_DEMAND_SCHEMA, record="uncertainty")
        return cls(
            required_channels=frozenset(
                require_list(payload["required_channels"], field="uncertainty.required_channels")
            ),
            coverage_factor=payload["coverage_factor"],
            require_supported_discrepancy=payload["require_supported_discrepancy"],
        )


@dataclass(frozen=True)
class CallerAssumption:
    """Something the caller states and is accountable for. Never evidence."""

    assumption_id: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "assumption_id", require_identifier(self.assumption_id, field="assumption.assumption_id")
        )
        object.__setattr__(self, "statement", require_text(self.statement, field="assumption.statement"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ASSUMPTION_SCHEMA, "assumption_id": self.assumption_id, "statement": self.statement}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CallerAssumption":
        payload = require_mapping(payload, field="assumption")
        require_keys(payload, required=("schema", "assumption_id", "statement"), record="assumption")
        require_schema_exact(payload, ASSUMPTION_SCHEMA, record="assumption")
        return cls(assumption_id=payload["assumption_id"], statement=payload["statement"])


def _discrepancy_from_dict(payload: Any) -> ModelDiscrepancy:
    raw = require_mapping(payload, field="discrepancy")
    require_keys(raw, required=("schema", "kind", "reference", "rationale"), record="discrepancy")
    try:
        return ModelDiscrepancy.from_dict(raw)
    except Exception as exc:  # the SRIA record raises its own contract error
        raise ClaimContractError(f"discrepancy is not a valid declaration: {exc}") from exc


# ---------------------------------------------------------------------------
# The claim
# ---------------------------------------------------------------------------

#: Every field of the serialized claim other than ``schema``, which each
#: reader names itself.
_CLAIM_FIELDS = (
    "claim_id",
    "statement",
    "kind",
    "qoi",
    "operator",
    "target",
    "tolerance",
    "required_capabilities",
    "operating_context",
    "known_inputs",
    "missing_inputs",
    "assumptions",
    "decision",
    "evidence",
    "uncertainty",
    "discrepancy",
    "requested_outputs",
)


@dataclass(frozen=True)
class ScientificClaim:
    """One structured scientific claim. Immutable, serializable, strict.

    ``operating_context`` and ``known_inputs`` are both keyed by input paths in
    the vocabulary capabilities declare (``cell.nominal_capacity``,
    ``stages[0].body.duration``). They differ in what they say: the context is
    the regime the claim is *about* (a duration, an ambient temperature, an
    operating point), the known inputs are the physical description of the
    subject. Both are part of identity; the keys may not overlap.

    ``missing_inputs`` are inputs the caller states are **unknown**. They are
    never filled in: the compiler reports them as missing even when a
    capability would accept a default.
    """

    claim_id: str
    statement: str
    kind: ClaimKind
    qoi: QuantityOfInterest
    operator: ConstraintOperator
    target: ClaimTarget
    tolerance: Quantity | None
    required_capabilities: frozenset[ScientificCapability]
    operating_context: Mapping[str, Any]
    known_inputs: Mapping[str, Any]
    missing_inputs: frozenset[str]
    assumptions: tuple[CallerAssumption, ...]
    decision: DecisionBinding
    evidence: EvidenceRequirement
    uncertainty: UncertaintyDemand
    discrepancy: ModelDiscrepancy
    requested_outputs: frozenset[RequestedOutput]
    #: Phase 2B: what the caller states is uncertain about the inputs (a declaration, never evidence).
    #: Serialized only when present, so a claim without it keeps its identity.
    input_uncertainty: InputUncertainty | None = None
    #: Phase 3: the decision this claim serves and the policy that sets its evidence bar.
    #: Serialized only when present; when present it is part of identity, so a policy change is a new context.
    decision_context: DecisionContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", require_text(self.claim_id, field="claim_id"))
        object.__setattr__(self, "statement", require_text(self.statement, field="statement"))
        try:
            object.__setattr__(self, "kind", ClaimKind(self.kind))
        except ValueError as exc:
            raise ClaimContractError(f"kind: {exc}") from exc
        try:
            object.__setattr__(self, "operator", ConstraintOperator(self.operator))
        except ValueError as exc:
            raise ClaimContractError(f"operator: {exc}") from exc
        for label, kind in (
            ("qoi", QuantityOfInterest),
            ("target", ClaimTarget),
            ("decision", DecisionBinding),
            ("evidence", EvidenceRequirement),
            ("uncertainty", UncertaintyDemand),
            ("discrepancy", ModelDiscrepancy),
        ):
            if not isinstance(getattr(self, label), kind):
                raise ClaimContractError(f"{label} must be a {kind.__name__}")

        self._check_comparison()
        self._check_inputs()
        self._check_input_uncertainty()
        if self.decision_context is not None and not isinstance(self.decision_context, DecisionContext):
            raise ClaimContractError("decision_context must be a DecisionContext record or None")

        caps = self.required_capabilities
        if isinstance(caps, (str, bytes)) or not isinstance(caps, (frozenset, set, tuple, list)):
            raise ClaimContractError("required_capabilities must be a collection")
        try:
            object.__setattr__(
                self,
                "required_capabilities",
                frozenset(ScientificCapability.coerce(item) for item in caps),
            )
        except ScientificCoreError as exc:
            raise ClaimContractError(f"required_capabilities: {exc}") from exc

        assumptions = tuple(self.assumptions)
        if any(not isinstance(item, CallerAssumption) for item in assumptions):
            raise ClaimContractError("assumptions must be CallerAssumption records")
        ids = [item.assumption_id for item in assumptions]
        if len(set(ids)) != len(ids):
            raise ClaimContractError("assumptions contain a duplicate assumption_id")
        object.__setattr__(self, "assumptions", tuple(sorted(assumptions, key=lambda a: a.assumption_id)))

        outputs = self.requested_outputs
        if isinstance(outputs, (str, bytes)) or not isinstance(outputs, (frozenset, set, tuple, list)):
            raise ClaimContractError("requested_outputs must be a collection")
        try:
            outputs = frozenset(RequestedOutput(item) for item in outputs)
        except ValueError as exc:
            raise ClaimContractError(f"requested_outputs: {exc}") from exc
        if not outputs:
            raise ClaimContractError("requested_outputs must name at least one output")
        object.__setattr__(self, "requested_outputs", outputs)

    # ---- construction rules -------------------------------------------------

    def _check_comparison(self) -> None:
        qoi_dimension = self.qoi.dimension
        if self.kind is ClaimKind.THRESHOLD:
            if self.operator not in _THRESHOLD_OPERATORS:
                raise ClaimContractError(
                    f"a THRESHOLD claim compares with <, <=, > or >=; got "
                    f"{self.operator.value!r}. Approximate equality is a "
                    f"TOLERANCE_BAND claim with an explicit tolerance"
                )
            if self.tolerance is not None:
                raise ClaimContractError(
                    "a THRESHOLD claim carries no tolerance: state the bound you "
                    "mean. Margin for uncertainty is the uncertainty demand's job"
                )
        else:
            if self.operator is not ConstraintOperator.EQUAL:
                raise ClaimContractError("a TOLERANCE_BAND claim uses the '==' operator")
            if not isinstance(self.tolerance, Quantity):
                raise ClaimContractError(
                    "a TOLERANCE_BAND claim requires a tolerance Quantity; "
                    "'approximately' without a width is not decidable"
                )
            if dimensionality(self.tolerance.units) != qoi_dimension:
                raise ClaimContractError(
                    f"tolerance {self.tolerance} is [{dimensionality(self.tolerance.units)}] "
                    f"but the QOI is [{qoi_dimension}]"
                )
            try:
                require_spread_unit(self.tolerance.units, context="claim tolerance")
            except ScientificCoreError as exc:
                raise ClaimContractError(str(exc)) from exc
            if self.tolerance.magnitude < 0.0:
                raise ClaimContractError("tolerance must be non-negative")
        if self.target.value is not None:
            target_dimension = dimensionality(self.target.value.units)
            if target_dimension != qoi_dimension:
                raise ClaimContractError(
                    f"incompatible dimensions: the QOI {self.qoi.name!r} is stated in "
                    f"{self.qoi.units!r} [{qoi_dimension}] and the target "
                    f"{self.target.value} is [{target_dimension}]; no comparison "
                    f"between them means anything"
                )

    def _check_inputs(self) -> None:
        context = {
            require_path(key, field="operating_context key"): check_input_value(
                value, field=f"operating_context.{key}"
            )
            for key, value in require_mapping(self.operating_context, field="operating_context").items()
        }
        known = {
            require_path(key, field="known_inputs key"): check_input_value(value, field=f"known_inputs.{key}")
            for key, value in require_mapping(self.known_inputs, field="known_inputs").items()
        }
        raw_missing = self.missing_inputs
        if isinstance(raw_missing, (str, bytes)) or not isinstance(raw_missing, (frozenset, set, tuple, list)):
            raise ClaimContractError("missing_inputs must be a collection of input paths")
        missing = [require_path(item, field="missing_inputs item") for item in raw_missing]
        if len(set(missing)) != len(missing):
            raise ClaimContractError("missing_inputs contains a duplicate path")
        overlap = (set(context) & set(known)) | (set(context) & set(missing)) | (set(known) & set(missing))
        if overlap:
            raise ClaimContractError(
                f"input path(s) {sorted(overlap)} appear in more than one of "
                f"operating_context, known_inputs and missing_inputs; one input has "
                f"one status"
            )
        object.__setattr__(self, "operating_context", freeze(context))
        object.__setattr__(self, "known_inputs", freeze(known))
        object.__setattr__(self, "missing_inputs", frozenset(missing))

    def _check_input_uncertainty(self) -> None:
        spec = self.input_uncertainty
        if spec is None:
            return
        if not isinstance(spec, InputUncertainty):
            raise ClaimContractError("input_uncertainty must be an InputUncertainty record or None")
        supplied = dict(self.known_inputs)
        supplied.update(self.operating_context)
        for dist in spec.distributions:
            stated = supplied.get(dist.path)
            if not isinstance(stated, Quantity):
                raise ClaimContractError(
                    f"input_uncertainty names {dist.path}, which the claim does not state as a quantity; "
                    f"a distribution is about a stated input, and its center is the stated value"
                )
            if dimensionality(stated.units) != dimensionality(dist.center.units):
                raise ClaimContractError(f"input_uncertainty for {dist.path} is not in the stated value's dimension")
            center = dist.center.to(stated.units).magnitude
            if not math.isclose(center, stated.magnitude, rel_tol=1e-12, abs_tol=0.0):
                raise ClaimContractError(
                    f"input_uncertainty for {dist.path} is centered at {dist.center}, but the claim states "
                    f"{stated}; the reported run is the nominal of the propagated distribution, so they must agree"
                )

    # ---- views ---------------------------------------------------------------

    @property
    def supplied_inputs(self) -> Mapping[str, Any]:
        """Operating context and known inputs together (their keys are disjoint)."""
        merged = dict(self.known_inputs)
        merged.update(self.operating_context)
        return freeze(merged)

    def resolve_target(self) -> Quantity | None:
        """The bound as a Quantity, or ``None`` when ``input_ref`` names nothing supplied."""
        if self.target.value is not None:
            return self.target.value
        value = self.supplied_inputs.get(self.target.input_ref)
        return value if isinstance(value, Quantity) else None

    def constraint(self, bound: Quantity) -> ConstraintDefinition:
        """This claim's comparison as the Core's own constraint record."""
        if dimensionality(bound.units) != self.qoi.dimension:
            raise ClaimContractError(
                f"target {bound} is [{dimensionality(bound.units)}], the QOI is [{self.qoi.dimension}]"
            )
        return ConstraintDefinition(
            name=f"claim:{self.claim_id}",
            metric=self.qoi.name,
            operator=self.operator,
            bound=bound,
            tolerance=self.tolerance,
        )

    # ---- identity ------------------------------------------------------------

    def _scientific_content(self) -> dict[str, Any]:
        payload = self.to_dict()
        for presentation_only in ("schema", "claim_id", "statement", "requested_outputs"):
            payload.pop(presentation_only)
        return payload

    @property
    def identity_digest(self) -> str:
        """Scientific identity: everything but the id, the prose and the output format.

        Two claims with the same identity digest ask the same question, of the
        same subject, for the same decision, at the same evidence bar, under
        the same caller assumptions and discrepancy declaration.
        """
        return tagged_digest(_IDENTITY_TAG, self._scientific_content())

    @property
    def record_digest(self) -> str:
        """Identity of this exact record, including id, prose and outputs."""
        return tagged_digest(_RECORD_TAG, self.to_dict())

    # ---- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CLAIM_SCHEMA,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "kind": self.kind.value,
            "qoi": self.qoi.to_dict(),
            "operator": self.operator.value,
            "target": self.target.to_dict(),
            "tolerance": None if self.tolerance is None else self.tolerance.to_dict(),
            "required_capabilities": sorted(cap.identifier for cap in self.required_capabilities),
            "operating_context": encode_inputs(self.operating_context),
            "known_inputs": encode_inputs(self.known_inputs),
            "missing_inputs": sorted(self.missing_inputs),
            "assumptions": [item.to_dict() for item in self.assumptions],
            "decision": self.decision.to_dict(),
            "evidence": self.evidence.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            "discrepancy": self.discrepancy.to_dict(),
            "requested_outputs": sorted(output.value for output in self.requested_outputs),
            **({"input_uncertainty": self.input_uncertainty.to_dict()} if self.input_uncertainty is not None else {}),
            **({"decision_context": self.decision_context.to_dict()} if self.decision_context is not None else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificClaim":
        """Read a claim, refusing every unknown, missing or malformed field."""
        payload = require_mapping(payload, field="claim")
        require_keys(payload, required=("schema",) + _CLAIM_FIELDS, optional=("input_uncertainty", "decision_context"), record="claim")
        require_schema_exact(payload, CLAIM_SCHEMA, record="claim")
        tolerance = payload["tolerance"]
        if tolerance is not None:
            tolerance = decode_input_value(tolerance, field="tolerance")
            if not isinstance(tolerance, Quantity):
                raise ClaimContractError("tolerance must be a quantity record or null")
        return cls(
            claim_id=payload["claim_id"],
            statement=payload["statement"],
            kind=_enum(ClaimKind, payload["kind"], field_name="kind"),
            qoi=QuantityOfInterest.from_dict(payload["qoi"]),
            operator=_enum(ConstraintOperator, payload["operator"], field_name="operator"),
            target=ClaimTarget.from_dict(payload["target"]),
            tolerance=tolerance,
            required_capabilities=frozenset(
                require_text(item, field="required_capabilities item")
                for item in require_list(payload["required_capabilities"], field="required_capabilities")
            ),
            operating_context=decode_inputs(payload["operating_context"], field="operating_context"),
            known_inputs=decode_inputs(payload["known_inputs"], field="known_inputs"),
            missing_inputs=frozenset(require_list(payload["missing_inputs"], field="missing_inputs")),
            assumptions=tuple(
                CallerAssumption.from_dict(item)
                for item in require_list(payload["assumptions"], field="assumptions")
            ),
            decision=DecisionBinding.from_dict(payload["decision"]),
            evidence=EvidenceRequirement.from_dict(payload["evidence"]),
            uncertainty=UncertaintyDemand.from_dict(payload["uncertainty"]),
            discrepancy=_discrepancy_from_dict(payload["discrepancy"]),
            requested_outputs=frozenset(require_list(payload["requested_outputs"], field="requested_outputs")),
            input_uncertainty=None
            if payload.get("input_uncertainty") is None
            else InputUncertainty.from_dict(payload["input_uncertainty"]),
            decision_context=None
            if payload.get("decision_context") is None
            else DecisionContext.from_dict(payload["decision_context"]),
        )


def _enum(kind: type[Enum], value: Any, *, field_name: str) -> Any:
    if not isinstance(value, str):
        raise ClaimContractError(f"{field_name} must be a string, got {type(value).__name__}")
    try:
        return kind(value)
    except ValueError as exc:
        raise ClaimContractError(f"{field_name}: {exc}") from exc


def discrepancy_is_unknown(claim: ScientificClaim) -> bool:
    """Whether the claim's own discrepancy declaration is UNKNOWN."""
    return claim.discrepancy.kind is DiscrepancyKind.UNKNOWN


__all__ = [
    "ASSUMPTION_SCHEMA",
    "CLAIM_SCHEMA",
    "DECISION_SCHEMA",
    "EVIDENCE_REQUIREMENT_SCHEMA",
    "QOI_SCHEMA",
    "TARGET_SCHEMA",
    "UNCERTAINTY_DEMAND_SCHEMA",
    "CallerAssumption",
    "ClaimKind",
    "ClaimTarget",
    "DecisionBinding",
    "EvidenceRequirement",
    "QuantityOfInterest",
    "RequestedOutput",
    "ScientificClaim",
    "UncertaintyDemand",
    "discrepancy_is_unknown",
]
