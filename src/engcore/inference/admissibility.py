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

from ..scientific.results.result import ScientificResult
from ..scientific.results.validation import ValidationLevel, ValidationReport
from ..scientific.units.quantity import Quantity


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
