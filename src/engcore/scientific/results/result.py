"""ScientificResult — the platform's output contract.

A result is never just ``temperature = 84``. It is:

    VALUE + UNIT + SOURCE MODEL + SOLVER + ASSUMPTIONS + UNCERTAINTY
          + VALIDITY + VALIDATION STATUS + PROVENANCE

Every one of those is a typed field here, and the type system refuses the
degenerate case: values must be Quantities, provenance is mandatory, and the
validation report can only claim what its checks established.

VALIDITY AND VALIDATION ARE DIFFERENT QUESTIONS
------------------------------------------------
``validation`` answers *was this result checked*. ``validity`` answers *was the
model applicable in the first place*. A converged, fully checked solve of an
inapplicable model is still a converged, fully checked solve, and the platform
holds the two on different fields so that neither can quietly stand in for the
other.

``validity`` is a **mapping**, keyed by model id, because a coupled result
covers several models and a single field would collapse them: a run whose
thermal model is in domain and whose material model is not has two answers, and
reporting one would be reporting the wrong one half the time.

NOT ASSESSED IS NOT UNKNOWN
----------------------------
The empty mapping means **nobody asked**. ``ValidityStatus.UNKNOWN`` means
somebody asked and the context could not settle it. They call for different
work — go and make the assessment, versus go and gather the input the
assessment needed — so the record makes them structurally impossible to
confuse rather than merely documenting the difference:

* there is no representation of "present but unassessed". A ``None`` value in
  the mapping is refused at construction, so a model is either a key with a
  real assessment or it is not a key.
* :meth:`ScientificResult.validity_of` **raises** for a model that was not
  assessed. It does not return ``None`` and it does not synthesize an
  ``UNKNOWN``; a caller that wants a total function must ask
  :meth:`is_assessed` first, which is the point at which the difference
  becomes visible.
* :attr:`ScientificResult.unassessed_models` enumerates the declared models
  that carry no assessment, so the gap is countable rather than implicit.

Nothing in this module ever writes an ``UNKNOWN`` of its own. The only
statuses a result carries are ones some model's ``ValidityDomain.assess``
actually produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..models.definition import ValidityAssessment, ValidityStatus
from ..serialization import require_schema_any, schema_string
from ..solvers.protocol import ConvergenceState, SolverIdentity
from ..units.quantity import Quantity
from ..units.validation import check_unit_map
from .immutable import detach, freeze
from .data_reference import ScientificDataReference
from .provenance import ProvenanceRecord
from .uncertainty import Uncertainty
from .validation import ValidationLevel, ValidationOutcome, ValidationReport

#: The version this writer emits. Bumped again for ``validity``, on exactly the
#: argument DATA-BOUNDARY0 made for ``data_references``: whether the model
#: applied is **scientific content**, not decoration. A reader that silently
#: ignored the field would report a result while dropping the answer to *may I
#: rely on this*, and would do it most dangerously in the case that matters —
#: a result whose model is recorded as OUTSIDE_VALIDATED_DOMAIN read as one
#: about which nothing was said. A version bump makes that reader fail loudly.
RESULT_SCHEMA = schema_string("scientific_result", 3)

#: The version before ``validity`` existed. Still read, never written.
RESULT_SCHEMA_V2 = schema_string("scientific_result", 2)

#: The version before ``data_references`` existed. Still read, never written.
RESULT_SCHEMA_V1 = schema_string("scientific_result", 1)

#: Exactly the versions this reader knows how to interpret. Not a range.
SUPPORTED_RESULT_SCHEMAS = (RESULT_SCHEMA_V1, RESULT_SCHEMA_V2, RESULT_SCHEMA)


@dataclass(frozen=True)
class ScientificResult:
    """An interpreted, attributable scientific output."""

    result_id: str
    values: Mapping[str, Quantity]
    provenance: ProvenanceRecord
    problem_id: str = ""
    models: tuple[tuple[str, str], ...] = ()
    solver: SolverIdentity | None = None
    convergence: ConvergenceState = ConvergenceState.NOT_APPLICABLE
    validation: ValidationReport = field(default_factory=ValidationReport)
    #: One ``ValidityAssessment`` per model that was assessed, keyed by model
    #: id. Empty means **not assessed**, which is not the same as assessed and
    #: UNKNOWN -- see the module docstring, which explains how the record makes
    #: the two impossible to confuse rather than only documenting it.
    #:
    #: Optional and defaulting to empty, so a solver that computes numbers
    #: without holding the operating point an assessment needs constructs
    #: exactly as it did before, and says nothing rather than something false.
    validity: Mapping[str, ValidityAssessment] = field(default_factory=dict)
    uncertainty: Mapping[str, Uncertainty] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    #: **Legacy, generic, and unchanged by DATA-BOUNDARY0.** A free-form
    #: tuple of strings that predates this milestone, with no schema, no
    #: written contract and no in-repo producer. Its accepted values are
    #: exactly what they were: no value that loaded before is refused now.
    #:
    #: **New scientific-data code MUST NOT use it as the bulk-data channel.**
    #: It is untyped, carries no unit, no count and no content identity, and
    #: nothing can check what was put in it — which is how a storage location
    #: ends up inside a scientific record by habit. Bulk data belongs in
    #: ``data_references``, which is checkable. A fitness test asserts that
    #: the modules introduced by DATA-BOUNDARY0 do not write this field; it
    #: deliberately constrains new code only, because absence of an in-repo
    #: producer is not evidence that no external caller exists.
    artifacts: tuple[str, ...] = ()
    #: Storage-independent identities of bulk arrays this result refers to.
    #: Small and O(1) in the size of the data they name; resolved through a
    #: store in the runtime data plane, which the Scientific Core never
    #: imports.
    data_references: tuple[ScientificDataReference, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        result_id = str(self.result_id).strip()
        if not result_id:
            raise ScientificCoreError("result requires a non-empty result_id")
        object.__setattr__(self, "result_id", result_id)

        values = dict(self.values)
        for name, value in values.items():
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"result value {name!r} must be a Quantity — a bare number "
                    f"is not a scientific result"
                )
        # Frozen, so the check above cannot be defeated after it has run: a
        # bare number the constructor refuses could be written straight into
        # ``values`` a line later, and `to_dict` then died on it. See
        # ``results.immutable``.
        object.__setattr__(self, "values", freeze(values))

        if not isinstance(self.provenance, ProvenanceRecord):
            raise ScientificCoreError(
                "result requires a ProvenanceRecord: an unattributable number "
                "is not a scientific result"
            )

        object.__setattr__(self, "convergence", ConvergenceState(self.convergence))
        object.__setattr__(self, "models", tuple(tuple(m) for m in self.models))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "metadata", freeze(self.metadata))

        references = tuple(self.data_references)
        seen: set[str] = set()
        for reference in references:
            if not isinstance(reference, ScientificDataReference):
                raise ScientificCoreError(
                    f"data reference must be a ScientificDataReference, got "
                    f"{type(reference).__name__}"
                )
            if reference.name in seen:
                raise ScientificCoreError(
                    f"duplicate data reference name {reference.name!r}; one "
                    f"logical name must identify one array"
                )
            if reference.name in values:
                raise ScientificCoreError(
                    f"{reference.name!r} is both a scalar value and a bulk "
                    f"data reference; one name must mean one thing"
                )
            seen.add(reference.name)
        object.__setattr__(
            self,
            "data_references",
            tuple(sorted(references, key=lambda r: r.name)),
        )

        object.__setattr__(self, "validity", freeze(self._checked_validity()))

        uncertainty = dict(self.uncertainty)
        for name, record in uncertainty.items():
            if not isinstance(record, Uncertainty):
                raise ScientificCoreError(
                    f"uncertainty for {name!r} must be an Uncertainty record"
                )
            if name not in values:
                raise ScientificCoreError(
                    f"uncertainty declared for unknown value {name!r}"
                )
        object.__setattr__(self, "uncertainty", freeze(uncertainty))

    def _checked_validity(self) -> dict:
        """Normalise the validity mapping, refusing every way to blur a gap."""
        declared = {model_id for model_id, _version in self.models}
        assessments = dict(self.validity)
        if assessments and not declared:
            raise ScientificCoreError(
                f"result {self.result_id!r} carries {len(assessments)} validity "
                f"assessment(s) but declares no models. An assessment is a "
                f"verdict about a named model at a named version; a result "
                f"that names none cannot say which model, and a consumer "
                f"cannot attribute it"
            )
        checked = {}
        for model_id, assessment in assessments.items():
            key = str(model_id).strip()
            if not key:
                raise ScientificCoreError(
                    "a validity assessment must name the model it belongs to; "
                    "an unattributed verdict cannot be acted on"
                )
            if assessment is None:
                raise ScientificCoreError(
                    f"validity for {key!r} is None. A model that was not "
                    f"assessed is absent from this mapping; a key present with "
                    f"no assessment would be a third state between 'not asked' "
                    f"and 'asked and unknown', and there is no such state"
                )
            if not isinstance(assessment, ValidityAssessment):
                raise ScientificCoreError(
                    f"validity for {key!r} must be a ValidityAssessment, got "
                    f"{type(assessment).__name__}"
                )
            # Normalised through the enum for the reason NEEDS.md 1.9 records:
            # ValidityAssessment has no __post_init__, so it may hold a bare
            # string, and an unrecognised one must not travel inside a result
            # as though it were a verdict. This guards the field this record
            # owns; the general fix is still 1.9's.
            try:
                status = ValidityStatus(assessment.status)
            except ValueError as exc:
                raise ScientificCoreError(
                    f"validity for {key!r} carries an unrecognised status "
                    f"({exc}); a status this platform does not understand must "
                    f"not be read as a verdict about the model"
                ) from None
            if key not in declared:
                raise ScientificCoreError(
                    f"validity names model {key!r}, which is not among the "
                    f"models this result declares ({sorted(declared)}); a "
                    f"verdict about a model that did not take part is not a "
                    f"verdict about this result"
                )
            checked[key] = (
                assessment
                if assessment.status is status
                else ValidityAssessment(
                    status=status,
                    satisfied=assessment.satisfied,
                    violated=assessment.violated,
                    unknown=assessment.unknown,
                )
            )
        return checked

    # ---- accessors ------------------------------------------------------
    def is_assessed(self, model_id: str) -> bool:
        """Whether anybody asked the applicability question about this model.

        The total counterpart to :meth:`validity_of`. A caller that wants to
        branch rather than handle an exception asks this first, and asking it
        is the point at which "not assessed" becomes visible as its own case.
        """
        return str(model_id).strip() in self.validity

    def validity_of(self, model_id: str) -> ValidityAssessment:
        """The assessment for one model. **Raises when there is none.**

        Deliberately not total, and deliberately not returning ``None``. Either
        alternative would put the caller one ``or`` away from treating an
        unasked question as an unanswerable one, and those recommend opposite
        work: make the assessment, versus gather the input it needed.
        """
        key = str(model_id).strip()
        try:
            return self.validity[key]
        except KeyError:
            raise ScientificCoreError(
                f"result {self.result_id!r} carries no validity assessment for "
                f"model {key!r}. This is 'not assessed', which is not "
                f"ValidityStatus.UNKNOWN: nobody asked whether the model "
                f"applied, so there is no verdict to report and none is "
                f"invented here"
            ) from None

    @property
    def unassessed_models(self) -> tuple[str, ...]:
        """Declared models carrying no assessment, so the gap is countable.

        Empty when every declared model was assessed -- including when the
        result declares no models at all, which is a result that names nothing
        to assess rather than one that assessed nothing.
        """
        return tuple(
            sorted(
                {model_id for model_id, _version in self.models}
                - set(self.validity)
            )
        )

    def value(self, name: str) -> Quantity:
        try:
            return self.values[name]
        except KeyError:
            raise ScientificCoreError(
                f"result {self.result_id!r} has no value {name!r}"
            ) from None

    def uncertainty_of(self, name: str) -> Uncertainty:
        """Uncertainty for a value; explicitly UNKNOWN when none was computed."""
        self.value(name)  # existence check
        return self.uncertainty.get(name, Uncertainty.unknown())

    @property
    def validation_status(self) -> ValidationOutcome:
        return self.validation.status

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        return self.validation.attained_levels

    @property
    def is_usable(self) -> bool:
        """Converged (or not applicable) and no failed validation check.

        Deliberately conservative and deliberately *not* called ``is_valid``:
        it reports the absence of known problems, not the presence of proof.
        """
        return (
            self.convergence
            in (ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE)
            and self.validation.status is not ValidationOutcome.FAIL
        )

    def check_units_against(self, expected_units: Mapping[str, str]) -> None:
        """Verify reported values carry the dimensionality the problem declared."""
        check_unit_map(self.values, expected_units, context=f"result {self.result_id!r}")

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "result_id": self.result_id,
            "problem_id": self.problem_id,
            "values": {
                k: v.to_dict() for k, v in sorted(self.values.items())
            },
            "models": [list(m) for m in self.models],
            "solver": self.solver.to_dict() if self.solver else None,
            "convergence": self.convergence.value,
            "validation": self.validation.to_dict(),
            "validity": {
                k: v.to_dict() for k, v in sorted(self.validity.items())
            },
            "uncertainty": {
                k: v.to_dict() for k, v in sorted(self.uncertainty.items())
            },
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "artifacts": list(self.artifacts),
            "data_references": [r.to_dict() for r in self.data_references],
            "provenance": self.provenance.to_dict(),
            # Detached at every depth, in one pass: a payload is a message
            # and a caller may edit it, but editing it must not reach back into
            # the record. Every other branch of this payload is built out of
            # freshly created dicts already, so this is the only one.
            "metadata": {
                key: detach(value)
                for key, value in sorted(self.metadata.items(), key=lambda kv: kv[0])
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificResult":
        version = require_schema_any(payload, SUPPORTED_RESULT_SCHEMAS)
        solver = payload.get("solver")
        return cls(
            result_id=payload["result_id"],
            problem_id=payload.get("problem_id", ""),
            values={
                k: Quantity.from_dict(v)
                for k, v in (payload.get("values") or {}).items()
            },
            models=tuple(tuple(m) for m in payload.get("models", ())),
            solver=SolverIdentity.from_dict(solver) if solver else None,
            convergence=ConvergenceState(payload.get("convergence", "not_applicable")),
            validation=ValidationReport.from_dict(payload["validation"])
            if payload.get("validation")
            else ValidationReport(),
            # A /1 or /2 payload predates this field and cannot carry one, so
            # it loads as not-assessed -- which is the truth about it. A /3
            # payload with the key absent, or explicitly null, loads the same
            # way for the same reason: there is one representation of "nobody
            # asked", and it is the empty mapping.
            validity={}
            if version in (RESULT_SCHEMA_V1, RESULT_SCHEMA_V2)
            else {
                k: ValidityAssessment.from_dict(v)
                for k, v in (payload.get("validity") or {}).items()
            },
            uncertainty={
                k: Uncertainty.from_dict(v)
                for k, v in (payload.get("uncertainty") or {}).items()
            },
            assumptions=tuple(payload.get("assumptions", ())),
            warnings=tuple(payload.get("warnings", ())),
            artifacts=tuple(payload.get("artifacts", ())),
            # The one compatibility branch. A ``scientific_result/1`` payload
            # predates bulk references and cannot carry one, so it loads with
            # none rather than having a key it never had read out of it.
            #
            # Why /2 exists at all: `data_references` is part of the scientific
            # content of a result. An older reader that accepted a /2 payload
            # would return a result that silently understates what was
            # computed, which is worse than refusing to read it. So a new
            # payload fails loudly on an old reader, and an old payload still
            # loads on the new one. See docs/milestones/data-boundary0-evidence.md.
            data_references=()
            if version == RESULT_SCHEMA_V1
            else tuple(
                ScientificDataReference.from_dict(r)
                for r in payload.get("data_references", ())
            ),
            provenance=ProvenanceRecord.from_dict(payload["provenance"]),
            metadata=dict(payload.get("metadata", {})),
        )
