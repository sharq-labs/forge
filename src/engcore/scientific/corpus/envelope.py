"""The validated envelope: where evidence says a prediction is supported.

TWO STATEMENTS THAT MUST NOT COLLAPSE INTO ONE
-----------------------------------------------
*Declared applicability* is a modelling claim: the regime the model's authors
say it is meant for. *Validation coverage* is an empirical fact: the regime it
has actually been tested in. They come apart constantly, and both directions
matter:

* theoretically applicable but empirically unsupported -- the model says it
  handles this, and nobody has ever checked;
* empirically validated here but currently outside declared applicability --
  there are passing cases, and the model's own declaration says this is not
  its regime.

An engine that reduced these to one boolean would lose exactly the information
a reviewer needs. So :class:`EnvelopeClassification` carries both, always, and
the empirical verdict never overrides the declaration or vice versa.

``UNKNOWN`` is a real answer here. A point that cannot even be located in the
region -- because the caller did not supply one of its coordinates -- is not
``EXTRAPOLATING`` and is certainly not ``SUPPORTED``. It is unknown, and saying
so is the whole discipline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .coverage import CoverageStatus, ValidationCoverage, ValidationRegion
from .dataset import Applicability
from .source import CorpusError, text

ENVELOPE_SCHEMA = schema_string("corpus_validation_envelope")
ENVELOPE_CLASSIFICATION_SCHEMA = schema_string("corpus_envelope_classification")


class EnvelopeVerdict(str, Enum):
    """What the empirical evidence says about one prediction point."""

    #: Enough passing evidence in this cell, and no failure in it.
    SUPPORTED = "supported"
    #: Some passing evidence, below the region's declared minimum.
    SPARSE_SUPPORT = "sparse_support"
    #: Inside the region's declared axes, but this cell has no scored evidence.
    EXTRAPOLATING = "extrapolating"
    #: This cell has failing evidence, or the point lies beyond every tested
    #: cell of the region. Either way, the validated envelope does not cover it.
    OUTSIDE_VALIDATED_ENVELOPE = "outside_validated_envelope"
    #: The point could not be located, so no empirical statement is available.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EnvelopeClassification:
    """Both statements about one point, side by side and never merged."""

    verdict: EnvelopeVerdict
    declared: Applicability
    cell_label: str = ""
    passed: int = 0
    failed: int = 0
    why: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", EnvelopeVerdict(self.verdict))
        object.__setattr__(self, "declared", Applicability(self.declared))
        object.__setattr__(self, "why", text(self.why, label="classification why"))

    @property
    def applicable_but_unsupported(self) -> bool:
        """Declared in scope, with no empirical support behind it."""
        return self.declared is Applicability.INSIDE and self.verdict in (
            EnvelopeVerdict.EXTRAPOLATING,
            EnvelopeVerdict.OUTSIDE_VALIDATED_ENVELOPE,
            EnvelopeVerdict.UNKNOWN,
        )

    @property
    def supported_but_undeclared(self) -> bool:
        """Empirically supported, in a regime the model does not claim."""
        return self.declared is Applicability.OUTSIDE and self.verdict in (
            EnvelopeVerdict.SUPPORTED,
            EnvelopeVerdict.SPARSE_SUPPORT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENVELOPE_CLASSIFICATION_SCHEMA,
            "verdict": self.verdict.value,
            "declared": self.declared.value,
            "cell_label": self.cell_label,
            "passed": self.passed,
            "failed": self.failed,
            "why": self.why,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvelopeClassification":
        require_schema(payload, ENVELOPE_CLASSIFICATION_SCHEMA)
        return cls(
            EnvelopeVerdict(payload["verdict"]),
            Applicability(payload["declared"]),
            payload.get("cell_label", ""),
            payload.get("passed", 0),
            payload.get("failed", 0),
            payload["why"],
        )


@dataclass(frozen=True)
class ValidationEnvelope:
    """A campaign's coverage, turned into a question you can ask of a point."""

    envelope_id: str
    coverage: ValidationCoverage
    campaign_report_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "envelope_id", text(self.envelope_id, label="envelope_id"))
        if not isinstance(self.coverage, ValidationCoverage):
            raise CorpusError("a validation envelope requires ValidationCoverage")
        digest = str(self.campaign_report_digest).strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise CorpusError("envelope campaign_report_digest must be sha256 hex")
        object.__setattr__(self, "campaign_report_digest", digest)

    @property
    def region(self) -> ValidationRegion:
        return self.coverage.region

    @property
    def has_any_support(self) -> bool:
        """Whether any cell holds passing evidence.

        Built from cell status, which is built from answers. Refusals -- correct
        ones included -- cannot make this true: declining to predict somewhere
        does not put that place inside the validated envelope.
        """
        return any(
            cell.status in (CoverageStatus.SUPPORTED, CoverageStatus.SPARSE)
            for cell in self.coverage.cells
        )

    @property
    def guardrail_counts(self) -> dict[str, int]:
        """Refusal behaviour across the region. Reported beside the envelope, never inside it."""
        return self.coverage.guardrail_counts()

    def classify(
        self,
        coordinates: Mapping[str, Quantity],
        *,
        declared: Applicability = Applicability.UNDECLARED,
    ) -> EnvelopeClassification:
        """Where one prediction point stands, empirically and by declaration."""
        declared = Applicability(declared)
        missing = sorted(set(self.region.names) - set(coordinates))
        if missing:
            return EnvelopeClassification(
                EnvelopeVerdict.UNKNOWN,
                declared,
                why=(
                    f"the point does not state {missing}, so it cannot be located "
                    f"in region {self.region.region_id!r}"
                ),
            )
        cell = self.coverage.cell_at(coordinates)
        if cell is None:
            return EnvelopeClassification(
                EnvelopeVerdict.UNKNOWN,
                declared,
                why=(
                    f"the point could not be located in region "
                    f"{self.region.region_id!r}"
                ),
            )
        label = cell.label
        if cell.status is CoverageStatus.FAILED:
            return EnvelopeClassification(
                EnvelopeVerdict.OUTSIDE_VALIDATED_ENVELOPE,
                declared,
                label,
                cell.passed,
                cell.failed,
                why=(
                    f"{cell.failed} of {cell.scored} scored cases fail in this cell; "
                    f"the validated envelope does not cover it"
                ),
            )
        if cell.status is CoverageStatus.SUPPORTED:
            return EnvelopeClassification(
                EnvelopeVerdict.SUPPORTED,
                declared,
                label,
                cell.passed,
                cell.failed,
                why=(
                    f"{cell.passed} passing cases and no failure in this cell, at or "
                    f"above the region minimum of "
                    f"{self.region.minimum_supporting_cases}"
                ),
            )
        if cell.status is CoverageStatus.SPARSE:
            return EnvelopeClassification(
                EnvelopeVerdict.SPARSE_SUPPORT,
                declared,
                label,
                cell.passed,
                cell.failed,
                why=(
                    f"{cell.passed} passing case(s) in this cell, below the region "
                    f"minimum of {self.region.minimum_supporting_cases}"
                ),
            )
        return EnvelopeClassification(
            EnvelopeVerdict.EXTRAPOLATING,
            declared,
            label,
            cell.passed,
            cell.failed,
            why="no scored case has ever landed in this cell",
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENVELOPE_SCHEMA,
            "envelope_id": self.envelope_id,
            "coverage": self.coverage.to_dict(),
            "campaign_report_digest": self.campaign_report_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationEnvelope":
        require_schema(payload, ENVELOPE_SCHEMA)
        return cls(
            payload["envelope_id"],
            ValidationCoverage.from_dict(payload["coverage"]),
            payload["campaign_report_digest"],
        )


__all__ = [
    "ENVELOPE_CLASSIFICATION_SCHEMA",
    "ENVELOPE_SCHEMA",
    "EnvelopeClassification",
    "EnvelopeVerdict",
    "ValidationEnvelope",
]
