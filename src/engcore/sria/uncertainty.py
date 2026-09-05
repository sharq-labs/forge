"""Uncertainty channel contract — semantics only, no UQ engine.

The Scientific Core already answers *how much* uncertainty a value carries
(:class:`~engcore.scientific.results.uncertainty.Uncertainty`, with ``UNKNOWN``
as the honest default). It does not answer *what kind*, and lumping the kinds
together is how a model-form error silently becomes a noise estimate.

M1 reserves four channels and forces two declarations that are usually left
implicit:

* ``subject_model`` — is this uncertainty about the prediction, or about the
  observation process? Confusing the two is what makes calibration circular.
* ``discrepancy`` — model-form discrepancy must be declared, even when the
  declaration is "we are asserting zero". ``ZERO_DECLARED`` is a claim someone
  is accountable for; a missing field is not.

No inference is performed here. This module defines vocabulary and refuses
incomplete declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.uncertainty import Uncertainty
from ..scientific.serialization import require_schema, schema_string
from .errors import UncertaintyContractError

UNCERTAINTY_DECLARATION_SCHEMA = schema_string("sria_uncertainty_declaration")
DISCREPANCY_SCHEMA = schema_string("sria_model_discrepancy")


class UncertaintyChannel(str, Enum):
    """Sources of uncertainty that must not be silently merged."""

    ALEATORIC = "aleatoric"
    EPISTEMIC_PARAMETER = "epistemic_parameter"
    MODEL_FORM = "model_form"
    NUMERICAL = "numerical"


class SubjectModel(str, Enum):
    """Which model the uncertainty is a property of."""

    PREDICTION_MODEL = "prediction_model"
    OBSERVATION_MODEL = "observation_model"


class DiscrepancyKind(str, Enum):
    ZERO_DECLARED = "zero_declared"
    CONSTRAINED_PRIOR = "constrained_prior"


@dataclass(frozen=True)
class ModelDiscrepancy:
    """An explicit statement about model-form discrepancy."""

    kind: DiscrepancyKind
    reference: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", DiscrepancyKind(self.kind))
        reference = str(self.reference).strip()
        if self.kind is DiscrepancyKind.CONSTRAINED_PRIOR and not reference:
            raise UncertaintyContractError(
                "CONSTRAINED_PRIOR discrepancy requires a reference: a prior "
                "nobody can point at is not a constraint"
            )
        object.__setattr__(self, "reference", reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DISCREPANCY_SCHEMA,
            "kind": self.kind.value,
            "reference": self.reference,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelDiscrepancy":
        require_schema(payload, DISCREPANCY_SCHEMA)
        return cls(
            kind=DiscrepancyKind(payload["kind"]),
            reference=payload.get("reference", ""),
            rationale=payload.get("rationale", ""),
        )


@dataclass(frozen=True)
class UncertaintyDeclaration:
    """Per-channel uncertainty plus the two mandatory declarations."""

    subject_model: SubjectModel
    discrepancy: ModelDiscrepancy
    channels: Mapping[UncertaintyChannel, Uncertainty] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_model", SubjectModel(self.subject_model))

        if not isinstance(self.discrepancy, ModelDiscrepancy):
            raise UncertaintyContractError(
                "uncertainty declaration requires an explicit ModelDiscrepancy; "
                "an absent declaration is not the same as declaring zero"
            )

        channels: dict[UncertaintyChannel, Uncertainty] = {}
        for key, value in self.channels.items():
            channel = UncertaintyChannel(key)
            if not isinstance(value, Uncertainty):
                raise UncertaintyContractError(
                    f"channel {channel.value!r} must carry an Uncertainty record"
                )
            channels[channel] = value
        object.__setattr__(self, "channels", channels)

    def channel(self, channel: UncertaintyChannel) -> Uncertainty:
        """Uncertainty for a channel; explicitly UNKNOWN when undeclared."""
        return self.channels.get(UncertaintyChannel(channel), Uncertainty.unknown())

    @property
    def quantified_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(
            sorted(
                (c for c, u in self.channels.items() if u.is_quantified),
                key=lambda c: c.value,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_DECLARATION_SCHEMA,
            "subject_model": self.subject_model.value,
            "discrepancy": self.discrepancy.to_dict(),
            "channels": {
                c.value: self.channels[c].to_dict()
                for c in sorted(self.channels, key=lambda c: c.value)
            },
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyDeclaration":
        require_schema(payload, UNCERTAINTY_DECLARATION_SCHEMA)
        return cls(
            subject_model=SubjectModel(payload["subject_model"]),
            discrepancy=ModelDiscrepancy.from_dict(payload["discrepancy"]),
            channels={
                UncertaintyChannel(k): Uncertainty.from_dict(v)
                for k, v in (payload.get("channels") or {}).items()
            },
            notes=payload.get("notes", ""),
        )
