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

NOT ASSESSED IS NOT UNKNOWN, AND SILENCE IS NEITHER
----------------------------------------------------
Three positions, not two. ``ValidityStatus.UNKNOWN`` means somebody asked and
the context could not settle it. **Not assessed** means nobody asked — and it
is now something a result *says*, in :attr:`ScientificResult.validity_not_assessed`,
with a reason, rather than something a reader infers from a field being empty.
The third position, silence, no longer exists: a result that declares a model
and neither assesses it nor declares why it did not **cannot be constructed**.

That is the whole of this milestone's change, and it is aimed at the core
rather than at the domains. ``validity`` was populated on one path of five.
The four that returned ``{}`` did not each make the same oversight; they took
the permission the core handed them, and a fifth domain would have taken it
too. So the permission is gone: coverage of every declared model is checked at
construction, and the error names the models and both ways to satisfy it.

Assessed-and-empty and not-assessed remain impossible to confuse, and now a
reader can tell which it is looking at without knowing which domain wrote it:

* there is no representation of "present but unassessed". A ``None`` value in
  the mapping is refused at construction, so a model is either a key with a
  real assessment or it is not a key.
* :meth:`ScientificResult.validity_of` **raises** for a model that was not
  assessed. It does not return ``None`` and it does not synthesize an
  ``UNKNOWN``; a caller that wants a total function must ask
  :meth:`is_assessed` first, which is the point at which the difference
  becomes visible.
* a model that was not assessed is a key in ``validity_not_assessed`` whose
  value is the *stated reason*, and
  :meth:`ScientificResult.non_assessment_reason` returns it. The same model id
  cannot appear on both mappings: assessed and not assessed at once is not a
  position.
* :attr:`ScientificResult.unassessed_models` enumerates them, so the gap stays
  countable — and is now equal to the declaration by construction rather than
  by inference.

WHEN THE MODULE THAT BUILDS THE RESULT CANNOT BE EDITED
-------------------------------------------------------
A frozen module is a real case: this repository SHA-256 pins the source of a
reproduced experiment, so a module inside one cannot be given a new argument
without breaking the pin that makes "it was not edited afterwards" a checkable
claim. Such a module can neither state a position nor be exempted from having
one, and it still declares models.

So a **package** may state the position on behalf of a module it contains, by
defining a mapping under the name in :data:`UNASSESSED_DECLARATIONS_ATTRIBUTE`
at package scope. The core walks the constructing module's package chain,
takes the first such mapping that names it, and records the reason it finds.

This module knows the *name* of that attribute and nothing else. Which modules
need it, and why, is the declaring package's business and is stated in the
declaring package's own words — the universal core names no domain, which is
the layering rule ``test_x2`` enforces over this whole subtree.

It is not an opt-out. A package-level declaration is as visible, as
attributable and as reason-bearing as a per-result one; the only thing it
changes is who says it. And ``tests/test_core_guards.py`` refuses any entry in
any such mapping whose module is not SHA-256 pinned by a frozen experiment
config — so the exemption is read off the pins rather than remembered, and it
expires the day the freeze does.

Nothing in this module ever writes an ``UNKNOWN`` of its own. The only
statuses a result carries are ones some model's ``ValidityDomain.assess``
actually produced.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..models.definition import ValidityAssessment, ValidityStatus
from ..serialization import require_schema_any, schema_string, unwritable
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
RESULT_SCHEMA = schema_string("scientific_result", 4)

#: The version before ``validity_not_assessed`` existed. Still read, never
#: written. Bumped for the same reason /3 was: a /3 payload can say nothing
#: about *why* a model was not assessed, so a /4 reader loading one has to
#: supply that reason itself rather than pretend the record carried it, and a
#: /3 reader handed a /4 payload would silently drop a stated position.
RESULT_SCHEMA_V3 = schema_string("scientific_result", 3)

#: The version before ``validity`` existed. Still read, never written.
RESULT_SCHEMA_V2 = schema_string("scientific_result", 2)

#: The version before ``data_references`` existed. Still read, never written.
RESULT_SCHEMA_V1 = schema_string("scientific_result", 1)

#: Exactly the versions this reader knows how to interpret. Not a range.
SUPPORTED_RESULT_SCHEMAS = (
    RESULT_SCHEMA_V1,
    RESULT_SCHEMA_V2,
    RESULT_SCHEMA_V3,
    RESULT_SCHEMA,
)

#: The reason recorded for a model whose non-assessment the record itself
#: could not carry, because the payload predates the field.
LEGACY_NON_ASSESSMENT = (
    "not assessed: loaded from a scientific_result payload written before a "
    "result could state why a model went unassessed, so no reason was "
    "recorded and none is invented here"
)

#: The package-scope attribute through which a package states the position of
#: a module it contains that cannot state its own. A mapping from module name
#: to the reason, in the declaring package's words.
#:
#: The core knows this name and nothing more. It never learns which modules
#: are declared, why, or what domain they belong to -- that is the whole point
#: of putting the mapping in the package rather than a list here.
UNASSESSED_DECLARATIONS_ATTRIBUTE = "SCIENTIFIC_UNASSESSED_DECLARATIONS"


def _constructing_module() -> str:
    """The module that is building this result.

    The first frame outside this one is the constructor's caller: the only
    frames in between are the dataclass ``__init__`` and this record's own
    ``__post_init__``.
    """
    frame = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module != __name__ and not module.startswith("dataclasses"):
            return module
        frame = frame.f_back
    return ""  # pragma: no cover - a result built with no caller frame


def _stated_by_a_package_for(module: str) -> str | None:
    """A reason some package states on ``module``'s behalf, if one does.

    Walked only on the failure path -- a result that states its own position
    never reaches here -- so the cost falls on the exemption rather than on
    every construction. The chain is walked from the nearest package outwards,
    so the closest declaration wins and a distant package cannot quietly
    override one made next to the module.
    """
    parts = module.split(".")
    for depth in range(len(parts) - 1, 0, -1):
        package = sys.modules.get(".".join(parts[:depth]))
        declarations = getattr(
            package, UNASSESSED_DECLARATIONS_ATTRIBUTE, None
        )
        if isinstance(declarations, Mapping) and module in declarations:
            reason = str(declarations[module]).strip()
            if reason:
                return reason
    return None


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
    #: One stated reason per declared model that was **not** assessed, keyed by
    #: model id. This is the field that removed the permission: between it and
    #: ``validity``, every model a result declares must be accounted for, and a
    #: result that accounts for neither cannot be constructed. An empty reason
    #: is refused -- a declaration of non-assessment that does not say why is
    #: the silence this field exists to replace.
    validity_not_assessed: Mapping[str, str] = field(default_factory=dict)
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
        # Refused HERE, not at `to_dict`. A result holding a value that
        # cannot be written down is a result whose provenance does not exist:
        # it is in memory, it looks like every other result, and the only
        # thing that will ever say otherwise is a TypeError from json,
        # somewhere else, later, in whatever was trying to record it. The one
        # free-form field is checked before it is frozen, so the error names
        # the type the caller passed rather than the frozen form of it.
        unrecordable = unwritable(self.metadata, path="metadata")
        if unrecordable is not None:
            where, kind = unrecordable
            raise ScientificCoreError(
                f"result {str(self.result_id).strip()!r} cannot be recorded: "
                f"{where} is a {kind}, which no scientific record can carry. A "
                f"result that exists in memory and cannot be written down is a "
                f"result whose provenance does not exist"
            )
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

        assessed, declined = self._checked_validity()
        object.__setattr__(self, "validity", freeze(assessed))
        object.__setattr__(self, "validity_not_assessed", freeze(declined))

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

    def _checked_validity(self) -> tuple[dict, dict]:
        """Normalise both validity mappings, refusing every way to blur a gap.

        Returns ``(assessed, declined)``. The second is what makes the first
        honest: between them they must cover every declared model, so there is
        no longer a way for a result to say nothing about one.
        """
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

        declined: dict[str, str] = {}
        for model_id, reason in dict(self.validity_not_assessed).items():
            key = str(model_id).strip()
            if not key:
                raise ScientificCoreError(
                    "a declaration of non-assessment must name the model it "
                    "is about; an unattributed one cannot be acted on"
                )
            text = "" if reason is None else str(reason).strip()
            if not text:
                raise ScientificCoreError(
                    f"validity_not_assessed for {key!r} carries no reason. "
                    f"Declaring that nobody asked is a position, and a "
                    f"position states why; an empty reason is the silence "
                    f"this field exists to replace"
                )
            if key in checked:
                raise ScientificCoreError(
                    f"model {key!r} is both assessed and declared unassessed. "
                    f"Those are two different answers to one question and a "
                    f"result cannot give both"
                )
            if key not in declared:
                raise ScientificCoreError(
                    f"validity_not_assessed names model {key!r}, which is not "
                    f"among the models this result declares "
                    f"({sorted(declared)}); a statement about a model that did "
                    f"not take part is not a statement about this result"
                )
            declined[key] = text

        silent = sorted(declared - set(checked) - set(declined))
        if silent:
            module = _constructing_module()
            stated = _stated_by_a_package_for(module)
            if stated is None:
                raise ScientificCoreError(
                    f"result {self.result_id!r} declares model(s) "
                    f"{silent} and says nothing about whether they applied. "
                    f"Every declared model must be either assessed (a key in "
                    f"`validity`) or declared unassessed with a reason (a key "
                    f"in `validity_not_assessed`). 'Not assessed' is a "
                    f"position this platform will record; it is not a default "
                    f"it will assume on a caller's behalf. If {module!r} "
                    f"cannot be edited to state one, a package containing it "
                    f"may state it under "
                    f"{UNASSESSED_DECLARATIONS_ATTRIBUTE}"
                )
            for key in silent:
                declined[key] = stated

        return checked, declined

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

    def non_assessment_reason(self, model_id: str) -> str:
        """Why this model was not assessed. **Raises when it was.**

        The counterpart to :meth:`validity_of`, and deliberately as partial as
        it is: asking a model that carries a real assessment for its reason is
        a caller confusing the two positions, and it gets an error rather than
        an empty string that would read like "no reason given".
        """
        key = str(model_id).strip()
        try:
            return self.validity_not_assessed[key]
        except KeyError:
            if key in self.validity:
                raise ScientificCoreError(
                    f"model {key!r} in result {self.result_id!r} WAS assessed "
                    f"({self.validity[key].status.value}); it has a verdict, "
                    f"not a reason for having none. Ask validity_of"
                ) from None
            raise ScientificCoreError(
                f"result {self.result_id!r} does not declare model {key!r} at "
                f"all, so it has neither an assessment nor a reason for the "
                f"absence of one"
            ) from None

    @property
    def unassessed_models(self) -> tuple[str, ...]:
        """Declared models carrying no assessment, so the gap is countable.

        Equal to the keys of ``validity_not_assessed`` by construction now,
        rather than by inference: the constructor refuses a declared model that
        is on neither mapping, so the difference this once computed can no
        longer be non-empty for a reason nobody stated.

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
            "validity_not_assessed": dict(
                sorted(self.validity_not_assessed.items())
            ),
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
            # A payload older than /4 cannot carry a reason, and a /4 payload
            # that declares a model without one was never constructible. So the
            # gap in an old payload is filled with the truth about it -- the
            # record predates the field -- rather than with silence, which the
            # constructor would refuse, or with an invented reason.
            validity_not_assessed=_declarations_for(payload, version),
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


def _declarations_for(payload: Mapping[str, Any], version: str) -> dict[str, str]:
    """The non-assessment declarations a payload carries, or the truth if it
    predates them.

    Kept out of :meth:`ScientificResult.from_dict`'s argument list because it
    is the one branch that has to look at two other fields at once: which
    models the payload declares, and which of them its ``validity`` covers.
    """
    stated = {
        str(k): str(v)
        for k, v in (payload.get("validity_not_assessed") or {}).items()
    }
    if version == RESULT_SCHEMA:
        return stated
    declared = {str(m[0]) for m in payload.get("models", ())}
    assessed = set(
        (payload.get("validity") or {})
        if version not in (RESULT_SCHEMA_V1, RESULT_SCHEMA_V2)
        else {}
    )
    for model_id in declared - assessed - set(stated):
        stated[model_id] = LEGACY_NON_ASSESSMENT
    return stated
