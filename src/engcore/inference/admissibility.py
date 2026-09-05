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

    def to_dict(self) -> dict[str, Any]:
        """Compact audit representation; the source result remains authoritative."""
        return {
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
