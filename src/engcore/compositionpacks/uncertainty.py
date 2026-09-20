"""Executable system-level uncertainty composition authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..domainpacks.manifest import ArtifactRef
from ..scientific.results.uncertainty import (
    Uncertainty,
    UncertaintySource,
)
from ..scientific.serialization import require_schema, schema_string
from ..sria.uncertainty import (
    CHANNEL_ACCEPTS_SOURCE,
    UncertaintyChannel,
)
from .errors import InvalidCompositionPackProvider

SYSTEM_UNCERTAINTY_RESULT_SCHEMA = schema_string(
    "composition_system_uncertainty_result"
)


@dataclass(frozen=True)
class SystemUncertaintyResult:
    quantity: str
    channel: UncertaintyChannel
    uncertainty: Uncertainty
    method_id: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        quantity = str(self.quantity).strip()
        method = str(self.method_id).strip()
        if not quantity or not method:
            raise InvalidCompositionPackProvider(
                "system uncertainty result requires quantity and method_id"
            )
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "method_id", method)
        object.__setattr__(
            self, "channel", UncertaintyChannel(self.channel)
        )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidCompositionPackProvider(
                "system uncertainty result requires Uncertainty"
            )
        if not self.uncertainty.is_quantified:
            raise InvalidCompositionPackProvider(
                "system uncertainty producer may emit only quantified results; "
                "omit unavailable channels instead of fabricating a value"
            )
        source = UncertaintySource(self.uncertainty.source_kind)
        if source is UncertaintySource.UNSPECIFIED:
            raise InvalidCompositionPackProvider(
                "quantified system uncertainty must declare source_kind"
            )
        if source not in CHANNEL_ACCEPTS_SOURCE[self.channel]:
            raise InvalidCompositionPackProvider(
                f"uncertainty source {source.value!r} contradicts channel "
                f"{self.channel.value!r}"
            )
        object.__setattr__(
            self,
            "evidence",
            tuple(
                str(item).strip()
                for item in self.evidence
                if str(item).strip()
            ),
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.quantity, self.channel.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SYSTEM_UNCERTAINTY_RESULT_SCHEMA,
            "quantity": self.quantity,
            "channel": self.channel.value,
            "uncertainty": self.uncertainty.to_dict(),
            "method_id": self.method_id,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "SystemUncertaintyResult":
        require_schema(payload, SYSTEM_UNCERTAINTY_RESULT_SCHEMA)
        return cls(
            quantity=payload["quantity"],
            channel=UncertaintyChannel(payload["channel"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
            method_id=payload["method_id"],
            evidence=tuple(payload.get("evidence", ())),
        )


@dataclass(frozen=True)
class ProvidedCompositionUncertainty:
    blueprint_id: str
    ref: ArtifactRef
    rule_id: str
    quantities: tuple[str, ...]
    channels: tuple[UncertaintyChannel, ...]
    implementation: Any

    def __post_init__(self) -> None:
        blueprint = str(self.blueprint_id).strip()
        rule_id = str(self.rule_id).strip()
        if not blueprint or not rule_id:
            raise InvalidCompositionPackProvider(
                "composition uncertainty producer requires blueprint_id and rule_id"
            )
        object.__setattr__(self, "blueprint_id", blueprint)
        object.__setattr__(self, "rule_id", rule_id)
        if not isinstance(self.ref, ArtifactRef):
            raise InvalidCompositionPackProvider(
                "composition uncertainty ref must be ArtifactRef"
            )
        quantities = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in self.quantities
                    if str(item).strip()
                }
            )
        )
        channels = tuple(
            sorted(
                {UncertaintyChannel(item) for item in self.channels},
                key=lambda item: item.value,
            )
        )
        if not quantities or not channels:
            raise InvalidCompositionPackProvider(
                "composition uncertainty producer requires quantities and channels"
            )
        object.__setattr__(self, "quantities", quantities)
        object.__setattr__(self, "channels", channels)
        if not callable(self.implementation):
            raise InvalidCompositionPackProvider(
                "composition uncertainty implementation must be callable"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.rule_id


__all__ = [
    "ProvidedCompositionUncertainty",
    "SYSTEM_UNCERTAINTY_RESULT_SCHEMA",
    "SystemUncertaintyResult",
]
