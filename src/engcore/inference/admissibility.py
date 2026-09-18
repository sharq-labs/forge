"""The smallest shared boundary a numerical inference engine may consume.

K1 showed that a single solver result can be both converged and scientifically
usable while still lacking the sequence-level evidence required to claim
numerical adequacy.  K1.5 therefore refuses to let downstream inference accept
``ScientificResult`` directly.

A numerical prediction reaches inference only after a domain adapter has:

* interpreted which result metrics are the requested observables;
* preserved them as unit-bearing ``Quantity`` values;
* bound them to the domain/model declaration that produced them;
* supplied the source result and its provenance; and
* supplied a sequence-level ``ValidationReport`` that actually *earned*
  ``NUMERICALLY_CONVERGED``.

This module deliberately knows nothing about CSTRs, likelihoods, priors,
posteriors, MCMC, BoTorch, or experiment design.  The domain owns meaning; this
shared layer owns only the reusable refusal rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..scientific.models.definition import ValidityStatus
from ..scientific.results.result import ConvergenceState, ScientificResult
from ..scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ..scientific.units.quantity import Quantity


# R-71 (I-28 part C): definitional, not tuned -- one member is a single solve.
_SEQUENCE_MEMBERS = 2


class InferenceAdmissibilityError(ValueError):
    """Raised when something tries to cross the inference boundary unqualified."""


@dataclass(frozen=True)
class AdmissibleNumericalPrediction:
    """A domain-interpreted numerical prediction admitted for inference.

    ``observable_names`` are names already interpreted by ``adapter_id``.  The
    values themselves are *not* copied into this object: :attr:`values` reads
    them from ``source_result`` so a caller cannot replace an audited Quantity
    with a bare float while retaining the admission wrapper.

    This type is intentionally specific to **numerical** forward predictions.
    Future analytic inference paths need not pretend that numerical tolerance
    convergence applies to them.
    """

    prediction_id: str
    domain: str
    adapter_id: str
    binding_ref: str
    source_result: ScientificResult
    observable_names: tuple[str, ...]
    sequence_validation: ValidationReport
    verification_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in (
            "prediction_id",
            "domain",
            "adapter_id",
            "binding_ref",
            "verification_ref",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InferenceAdmissibilityError(
                    f"admissible numerical prediction requires non-empty {label}"
                )
            object.__setattr__(self, label, value)

        if not isinstance(self.source_result, ScientificResult):
            raise InferenceAdmissibilityError(
                "numerical inference requires a ScientificResult source; raw "
                "arrays, mappings and solver buffers are not admissible"
            )
        if not self.source_result.is_usable:
            raise InferenceAdmissibilityError(
                f"source result {self.source_result.result_id!r} is not "
                "scientifically usable according to its domain validation"
            )
        _require_the_source_names_a_model(self.source_result, "numerical")
        _require_applicability_not_refuted(self.source_result, "numerical")
        _require_binding_names_the_source(self.source_result, self.binding_ref, "numerical")
        # ScientificResult already makes provenance mandatory, but retain this
        # explicit invariant here so the inference boundary documents what it
        # relies on rather than relying on an incidental implementation detail.
        if self.source_result.provenance is None:  # pragma: no cover - Core forbids it
            raise InferenceAdmissibilityError(
                "numerical inference refuses a source without provenance"
            )

        if not isinstance(self.sequence_validation, ValidationReport):
            raise InferenceAdmissibilityError(
                "numerical inference requires a sequence-level ValidationReport"
            )
        if not self.sequence_validation.claims(
            ValidationLevel.NUMERICALLY_CONVERGED
        ):
            raise InferenceAdmissibilityError(
                "sequence validation did not establish NUMERICALLY_CONVERGED; "
                "a usable single solve cannot certify its own numerical adequacy"
            )
        # R-71 (I-28 part C): "a usable single solve cannot certify its own numerical
        # adequacy" was the whole purpose of the line above, and the source's OWN report
        # was accepted as the sequence's, which is precisely that solve certifying itself.
        if self.sequence_validation == self.source_result.validation:
            raise InferenceAdmissibilityError(
                f"numerical inference refuses source result "
                f"{self.source_result.result_id!r}: its sequence_validation is the "
                f"source's own validation report. A usable single solve cannot certify "
                f"its own numerical adequacy, so the sequence's evidence is a different "
                f"record from the single solve's"
            )
        _require_a_sequence_of_members(self.sequence_validation)

        names = tuple(str(name).strip() for name in self.observable_names)
        if not names or any(not name for name in names):
            raise InferenceAdmissibilityError(
                "at least one non-empty domain-interpreted observable is required"
            )
        if len(set(names)) != len(names):
            raise InferenceAdmissibilityError(
                f"duplicate inference observable names are not allowed: {names!r}"
            )
        for name in names:
            try:
                value = self.source_result.value(name)
            except Exception as exc:
                raise InferenceAdmissibilityError(
                    f"source result does not contain requested observable {name!r}"
                ) from exc
            if not isinstance(value, Quantity):  # Core also enforces this.
                raise InferenceAdmissibilityError(
                    f"observable {name!r} is not a unit-bearing Quantity"
                )
        object.__setattr__(self, "observable_names", names)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def values(self) -> Mapping[str, Quantity]:
        """The admitted observable values, still unit-bearing and attributable."""
        return {name: self.source_result.value(name) for name in self.observable_names}

    def value(self, name: str) -> Quantity:
        name = str(name)
        if name not in self.observable_names:
            raise InferenceAdmissibilityError(
                f"observable {name!r} was not admitted for this prediction"
            )
        return self.source_result.value(name)

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        return self.sequence_validation.attained_levels

    @property
    def admission_route(self) -> str:
        """Which boundary this value crossed. Recorded, never inferred.

        A downstream reader asking "what backs this number" gets a different
        answer for the two routes -- sequence-level convergence here, declared
        applicability of a closed form there -- and the audit trail has to say
        which, because the strength of the claim differs.
        """
        return "numerical"

    def to_dict(self) -> dict[str, Any]:
        """Compact audit representation; the source result remains authoritative."""
        return {
            "admission_route": self.admission_route,
            "prediction_id": self.prediction_id,
            "domain": self.domain,
            "adapter_id": self.adapter_id,
            "binding_ref": self.binding_ref,
            "source_result_id": self.source_result.result_id,
            "source_provenance": self.source_result.provenance.to_dict(),
            "observables": {
                name: self.source_result.value(name).to_dict()
                for name in self.observable_names
            },
            "sequence_validation": self.sequence_validation.to_dict(),
            "verification_ref": self.verification_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AdmissibleAnalyticPrediction:
    """A domain-interpreted CLOSED-FORM prediction admitted for inference.

    The gap this fills, and why it is not a weaker copy of the numerical gate
    ---------------------------------------------------------------------------
    :class:`AdmissibleNumericalPrediction` demands
    ``claims(NUMERICALLY_CONVERGED)``, and ``ValidationReport.claims`` is exact
    membership rather than a ladder. That is right for a discretized solve: a
    single usable result cannot certify its own numerical adequacy, and only a
    sequence can.

    It is not right for a model with nothing to discretize. ``R(T) = R_ref (1 +
    alpha (T - T_ref))`` has no mesh, no step size and no tolerance; its
    production validation attains ``DIMENSIONALLY_VALID`` and stops, because
    that is the whole truth about it. Forcing such a model through the
    numerical gate means writing a check that claims tolerance convergence for
    arithmetic -- which this module's own header already refused in advance:
    "Future analytic inference paths need not pretend that numerical tolerance
    convergence applies to them."

    So the analytic route asks for what an analytic prediction can actually
    earn, and the crucial part is what it REFUSES:

    **A prediction claiming NUMERICALLY_CONVERGED is rejected here.** Without
    that, this class would be a back door -- a numerical result that could not
    satisfy the sequence-validation requirement could be relabelled analytic
    and admitted on the weaker evidence. The two routes are disjoint by
    construction, and a caller must pick the one that matches what its model
    is, not the one whose bar it can clear.

    The scientific content of an analytic admission is the model's
    APPLICABILITY, not its convergence. That is why a usable source result
    carrying its own validity assessment plus a declared closed form is the
    right evidence here, and a convergence sequence is not.
    """

    prediction_id: str
    domain: str
    adapter_id: str
    binding_ref: str
    source_result: ScientificResult
    observable_names: tuple[str, ...]
    validation: ValidationReport
    analytic_basis: str
    verification_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in (
            "prediction_id",
            "domain",
            "adapter_id",
            "binding_ref",
            "verification_ref",
            "analytic_basis",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InferenceAdmissibilityError(
                    f"admissible analytic prediction requires non-empty {label}"
                )
            object.__setattr__(self, label, value)

        if not isinstance(self.source_result, ScientificResult):
            raise InferenceAdmissibilityError(
                "analytic inference requires a ScientificResult source; raw "
                "arrays, mappings and solver buffers are not admissible"
            )
        if not self.source_result.is_usable:
            raise InferenceAdmissibilityError(
                f"source result {self.source_result.result_id!r} is not "
                "scientifically usable according to its domain validation"
            )
        _require_the_source_names_a_model(self.source_result, "analytic")
        _require_applicability_not_refuted(self.source_result, "analytic")
        _require_binding_names_the_source(self.source_result, self.binding_ref, "analytic")
        _require_the_source_has_nothing_to_converge(self.source_result, self.prediction_id)
        if self.source_result.provenance is None:  # pragma: no cover - Core forbids it
            raise InferenceAdmissibilityError(
                "analytic inference refuses a source without provenance"
            )

        if not isinstance(self.validation, ValidationReport):
            raise InferenceAdmissibilityError(
                "analytic inference requires a ValidationReport"
            )
        if self.validation.claims(ValidationLevel.NUMERICALLY_CONVERGED):
            raise InferenceAdmissibilityError(
                f"prediction {self.prediction_id!r} claims NUMERICALLY_CONVERGED "
                f"and is therefore a NUMERICAL prediction: admit it through "
                f"require_admissible_numerical_prediction, which holds it to "
                f"sequence-level evidence. The analytic route is for models "
                f"with nothing to converge, not a lower bar for models that "
                f"have something to converge and did not establish it"
            )
        # R-71: the dimensional evidence has to exist in the record the prediction is
        # about, not only in a report handed over beside it.
        if not self.source_result.validation.claims(ValidationLevel.DIMENSIONALLY_VALID):
            raise InferenceAdmissibilityError(
                f"analytic inference refuses source result "
                f"{self.source_result.result_id!r}: its own validation report does not "
                f"establish DIMENSIONALLY_VALID. The evidence for an analytic admission "
                f"is a fact about the source record, and a report attached beside it does "
                f"not put it there"
            )
        if not self.validation.claims(ValidationLevel.DIMENSIONALLY_VALID):
            raise InferenceAdmissibilityError(
                f"prediction {self.prediction_id!r} did not establish "
                f"DIMENSIONALLY_VALID; an analytic prediction whose dimensions "
                f"were never checked has no evidence at all behind it"
            )

        names = tuple(str(name).strip() for name in self.observable_names)
        if not names or any(not name for name in names):
            raise InferenceAdmissibilityError(
                "at least one non-empty domain-interpreted observable is required"
            )
        if len(set(names)) != len(names):
            raise InferenceAdmissibilityError(
                f"duplicate inference observable names are not allowed: {names!r}"
            )
        for name in names:
            try:
                value = self.source_result.value(name)
            except Exception as exc:
                raise InferenceAdmissibilityError(
                    f"source result does not contain requested observable {name!r}"
                ) from exc
            if not isinstance(value, Quantity):  # Core also enforces this.
                raise InferenceAdmissibilityError(
                    f"observable {name!r} is not a unit-bearing Quantity"
                )
        object.__setattr__(self, "observable_names", names)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def values(self) -> Mapping[str, Quantity]:
        return {name: self.source_result.value(name) for name in self.observable_names}

    def value(self, name: str) -> Quantity:
        name = str(name)
        if name not in self.observable_names:
            raise InferenceAdmissibilityError(
                f"observable {name!r} was not admitted for this prediction"
            )
        return self.source_result.value(name)

    @property
    def attained_levels(self) -> frozenset[ValidationLevel]:
        return self.validation.attained_levels

    @property
    def admission_route(self) -> str:
        return "analytic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "admission_route": self.admission_route,
            "prediction_id": self.prediction_id,
            "domain": self.domain,
            "adapter_id": self.adapter_id,
            "binding_ref": self.binding_ref,
            "source_result_id": self.source_result.result_id,
            "source_provenance": self.source_result.provenance.to_dict(),
            "observables": {
                name: self.source_result.value(name).to_dict()
                for name in self.observable_names
            },
            "validation": self.validation.to_dict(),
            "analytic_basis": self.analytic_basis,
            "verification_ref": self.verification_ref,
            "metadata": dict(self.metadata),
        }


def require_admissible_analytic_prediction(
    candidate: object,
) -> AdmissibleAnalyticPrediction:
    """The gate an analytic forward prediction crosses before it is read."""
    if not isinstance(candidate, AdmissibleAnalyticPrediction):
        raise InferenceAdmissibilityError(
            "analytic inference accepts only AdmissibleAnalyticPrediction; "
            f"got {type(candidate).__name__}. A bare array/mapping/"
            "ScientificResult has not crossed the domain admission boundary"
        )
    if ValidationLevel.DIMENSIONALLY_VALID not in candidate.attained_levels:
        raise InferenceAdmissibilityError(
            "admitted analytic prediction lost its DIMENSIONALLY_VALID evidence"
        )
    if ValidationLevel.NUMERICALLY_CONVERGED in candidate.attained_levels:
        raise InferenceAdmissibilityError(
            "an analytic prediction that claims NUMERICALLY_CONVERGED belongs "
            "on the numerical route"
        )
    return candidate


#: Either admission route. Consumers that do not care which boundary a value
#: crossed -- the forward table, for instance -- take this; consumers that do
#: care read ``admission_route``.
AdmittedPrediction = (AdmissibleNumericalPrediction, AdmissibleAnalyticPrediction)


def require_admitted_prediction(
    candidate: object,
) -> "AdmissibleNumericalPrediction | AdmissibleAnalyticPrediction":
    """Admit through whichever route the prediction's own evidence supports.

    Dispatches on the TYPE the caller built, never on which bar the candidate
    happens to clear: a numerical prediction is held to sequence validation
    even if it would satisfy the analytic route, because the type records what
    the model is.
    """
    if isinstance(candidate, AdmissibleAnalyticPrediction):
        return require_admissible_analytic_prediction(candidate)
    return require_admissible_numerical_prediction(candidate)


def require_admissible_numerical_prediction(
    candidate: object,
) -> AdmissibleNumericalPrediction:
    """The gate downstream numerical inference calls before reading a value.

    Deliberately does **not** auto-wrap a ``ScientificResult``.  Auto-wrapping
    would erase the whole K1.5 distinction by turning ``is_usable`` into an
    implicit sequence-validation claim.
    """

    if not isinstance(candidate, AdmissibleNumericalPrediction):
        raise InferenceAdmissibilityError(
            "numerical inference accepts only AdmissibleNumericalPrediction; "
            f"got {type(candidate).__name__}. A bare array/mapping/"
            "ScientificResult has not crossed the domain sequence-validation "
            "boundary"
        )
    # Re-reading the derived level makes the consumption rule explicit even
    # though construction already enforced it.
    if ValidationLevel.NUMERICALLY_CONVERGED not in candidate.attained_levels:
        raise InferenceAdmissibilityError(
            "admitted prediction lost its NUMERICALLY_CONVERGED evidence"
        )
    return candidate


def _source_reference_candidates(result) -> tuple[str, ...]:
    """Everything the source result's own record names, for a binding reference to be one of (R-71).

    The candidates are not a new convention: they are what the in-tree producers already write. The battery
    calibration and the TCR study pass `model_id@version`; the CSTR routes pass a physics fingerprint that
    the source's provenance metadata carries and that the domain already compares against it.
    """
    provenance = result.provenance
    candidates = {str(result.result_id)}
    if provenance is not None:
        candidates.add(str(provenance.run_id))
        for value in (getattr(provenance, "metadata", None) or {}).values():
            candidates.add(str(value))
        for model_id, version in tuple(getattr(provenance, "models", ()) or ()):
            candidates.update({str(model_id), f"{model_id}@{version}"})
        for solver_id, version in tuple(getattr(provenance, "solvers", ()) or ()):
            candidates.update({str(solver_id), f"{solver_id}@{version}"})
    for model_id, version in tuple(result.models or ()):
        candidates.update({str(model_id), f"{model_id}@{version}"})
    solver = getattr(result, "solver", None)
    if solver is not None:
        candidates.update({str(solver.solver_id), f"{solver.solver_id}@{solver.version}"})
    for value in (getattr(result, "metadata", None) or {}).values():
        candidates.add(str(value))
    return tuple(sorted(candidate for candidate in candidates if candidate.strip()))


def _require_binding_names_the_source(result, binding_ref: str, route: str) -> None:
    """R-71: a binding reference that binds nothing is a field with a name and no content.

    The audited record's reference was 'binding:p', which names nothing in the source it claims to bind. A
    reference is accepted when the source's own record contains it -- its id, its run id, a model or solver
    identity it declares, or a value its metadata carries.
    """
    candidates = _source_reference_candidates(result)
    text = str(binding_ref)
    if not any(candidate in text for candidate in candidates):
        raise InferenceAdmissibilityError(
            f"{route} inference refuses binding_ref {binding_ref!r}: it names nothing in source result "
            f"{result.result_id!r}. A binding reference binds the prediction to the record it came from, so "
            f"it carries something that record names -- its id, its run id, a model or solver identity it "
            f"declares, or a value its metadata carries"
        )


def _require_the_source_names_a_model(result, route: str) -> None:
    """R-71: the applicability rule iterates over the source's models, so no models means no rule.

    A source with no models satisfied every applicability check vacuously and crossed either route -- and a
    number no model claims is not evidence about a model's parameters, which is what the applicability
    refusal says in its own message.
    """
    if not tuple(result.models or ()):
        raise InferenceAdmissibilityError(
            f"{route} inference refuses source result {result.result_id!r}: it names no model. A number no "
            f"model claims is not evidence about a model's parameters, and an applicability rule over no "
            f"models is satisfied by anything"
        )


def _require_the_source_has_nothing_to_converge(result, prediction_id: str) -> None:
    """R-71: whether a model has something to converge is a fact about the SOURCE, not about the attached report.

    The route's own refusal already says it is "for models with nothing to converge, not a lower bar for
    models that have something to converge and did not establish it" -- and it read the report the CALLER
    passed, so it fired exactly when it was not needed. A closed-form evaluation records
    ``NOT_APPLICABLE`` convergence (both in-tree analytic producers do); any other state is the record of an
    iterative solve.
    """
    if result.validation.claims(ValidationLevel.NUMERICALLY_CONVERGED):
        raise InferenceAdmissibilityError(
            f"analytic inference refuses source result {result.result_id!r} for prediction "
            f"{prediction_id!r}: the source's OWN validation claims NUMERICALLY_CONVERGED, so it has "
            f"something to converge and belongs on the numerical route, which holds it to sequence-level "
            f"evidence"
        )
    if result.convergence is not ConvergenceState.NOT_APPLICABLE:
        raise InferenceAdmissibilityError(
            f"analytic inference refuses source result {result.result_id!r} for prediction "
            f"{prediction_id!r}: its convergence state is {result.convergence.value!r}. A model with "
            f"nothing to converge records NOT_APPLICABLE; any other state is the record of an iterative "
            f"solve, and an iterative solve crosses the numerical route or not at all"
        )


def _require_a_sequence_of_members(report: ValidationReport) -> None:
    """R-71: a convergence SEQUENCE has members, so the check establishing it names at least two.

    Two is definitional rather than tuned: one member is a single solve, which is the thing this boundary
    exists to refuse. What the report is NOT held to -- naming this model, these observables, or the run ids
    of the members -- is stated as a residual in the batch protocol, because a ValidationReport carries
    evidence strings and not a typed sequence record.
    """
    for check in report.checks:
        if (
            check.outcome is ValidationOutcome.PASS
            and check.establishes is ValidationLevel.NUMERICALLY_CONVERGED
            and len({str(entry) for entry in check.evidence}) >= _SEQUENCE_MEMBERS
        ):
            return
    raise InferenceAdmissibilityError(
        f"numerical inference refuses a sequence_validation whose NUMERICALLY_CONVERGED check names fewer "
        f"than {_SEQUENCE_MEMBERS} distinct evidence entries: a convergence sequence has members, and one "
        f"member is the single solve this boundary refuses"
    )


def _require_applicability_not_refuted(result: ScientificResult, route: str) -> None:
    """Refuse a source whose applicability was assessed and not established.

    ``ScientificResult.is_usable`` answers *converged, and no check failed* and
    deliberately not *is this model in its validated domain*; that distinction
    is pinned in ``tests/test_core_semantic_invariants.py``, and a caller who
    wants validity must ask for it. This boundary is that caller. Without the
    question, a numerically clean result whose model was assessed
    ``OUTSIDE_VALIDATED_DOMAIN`` -- or ``UNKNOWN``, because the context the
    assessment needed was missing -- was admitted, and entered a posterior as
    evidence about parameters of a model not shown to apply.

    An explicit, reasoned non-assessment stays admissible. A calibration sweep
    evaluates candidate declarations the study is still choosing, and records
    each forward result as not assessed with that reason; an applicability
    verdict about a candidate would be a statement about a declaration nobody
    has made. That record says what it did not do, which is the honest state,
    and it is not a verdict this boundary can overrule. Asserting applicability
    of the calibrated result itself is the calibrating domain's job.
    """
    refuted = sorted(
        (model_id, result.validity[model_id].status.value)
        for model_id, _version in result.models
        if model_id in result.validity
        and result.validity[model_id].status is not ValidityStatus.IN_DOMAIN
    )
    if refuted:
        raise InferenceAdmissibilityError(
            f"{route} inference refuses source result {result.result_id!r}: "
            f"applicability was assessed and not established for {refuted}. A "
            f"prediction from a model not shown to apply where it ran is not "
            f"evidence about that model's parameters"
        )
