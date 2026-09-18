"""Validation obligations — what a campaign declared it requires.

Obligations connect a :class:`~engcore.sria.charter.CampaignCharter` to the
Arbiter's checks. They exist so that thresholds live where they can be argued
about — in a charter, a domain pack, or a registered policy — rather than as
constants inside assurance code.

This is not pedantry about configuration. A magic number in a critic is a
scientific decision made by whoever last edited that file, applied silently to
every campaign, with no record of who chose it or why. An obligation carries
its own ``source``, so the answer to "why did this need a trusted calibration?"
is always retrievable.

An empty obligation set is legal and means something precise: *nothing was
required*, so the Arbiter cannot issue VALID — it has no standard to certify
against.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..calibration.critic import CalibrationVerdict
from ..charter import CampaignCharter
from ..uncertainty import UncertaintyChannel
from .assessment import CriticClass

OBLIGATION_SCHEMA = schema_string("sria_validation_obligation")
OBLIGATION_SET_SCHEMA = schema_string("sria_validation_obligation_set")


class ObligationKind(str, Enum):
    REQUIRED_CRITIC = "required_critic"
    REQUIRED_CHECK = "required_check"
    REQUIRED_UNCERTAINTY_CHANNEL = "required_uncertainty_channel"
    REQUIRED_CALIBRATION_STATUS = "required_calibration_status"
    REQUIRED_DOMAIN_CHECK = "required_domain_check"
    #: Appended (member order is frozen). The evidence must carry exactly this
    #: ``context_ref`` -- the charter-and-decision it was produced for.
    REQUIRED_CONTEXT = "required_context"


#: The one spelling of a charter-bound context of use. Evidence produced for a
#: decision under a charter carries ``charter:<charter digest>#decision:<id>``.
CHARTER_CONTEXT_PREFIX = "charter:"
_DECISION_MARK = "#decision:"


def charter_context_ref(charter_digest: str, decision_id: str) -> str:
    """The context reference evidence made for ``decision_id`` under a charter carries."""
    digest = str(charter_digest).strip()
    decision = str(decision_id).strip()
    if not digest or not decision:
        raise ValueError("a charter context names both a charter digest and a decision id")
    return f"{CHARTER_CONTEXT_PREFIX}{digest}{_DECISION_MARK}{decision}"


def parse_charter_context_ref(context_ref: str) -> tuple[str, str] | None:
    """``(charter_digest, decision_id)`` for a charter-bound reference, else ``None``.

    A reference that starts with the charter prefix but does not parse is
    returned as ``("", "")`` -- a malformed claim to a charter, which must never
    be read as "no claim to a charter".
    """
    text = str(context_ref)
    if not text.startswith(CHARTER_CONTEXT_PREFIX):
        return None
    body = text[len(CHARTER_CONTEXT_PREFIX):]
    digest, mark, decision = body.partition(_DECISION_MARK)
    if not mark or not digest.strip() or not decision.strip() or _DECISION_MARK in decision:
        return ("", "")
    return (digest, decision)


@dataclass(frozen=True)
class ValidationObligation:
    """One declared requirement, with the authority that declared it."""

    obligation_id: str
    kind: ObligationKind
    target: str
    source: str
    detail: str = ""

    def __post_init__(self) -> None:
        for label in ("obligation_id", "target", "source"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"validation obligation requires {label}; an obligation "
                    f"with no declared source is a global magic number"
                )
        object.__setattr__(self, "kind", ObligationKind(self.kind))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBLIGATION_SCHEMA,
            "obligation_id": self.obligation_id,
            "kind": self.kind.value,
            "target": self.target,
            "source": self.source,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationObligation":
        require_schema(payload, OBLIGATION_SCHEMA)
        return cls(
            obligation_id=payload["obligation_id"],
            kind=ObligationKind(payload["kind"]),
            target=payload["target"],
            source=payload["source"],
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class ObligationSet:
    """Everything a campaign requires before a result may be called VALID.

    ``charter_digest`` names the exact :class:`CampaignCharter` the set was
    derived from. :func:`obligations_from_charter` sets it; a hand-built set
    has none, and a campaign runner refuses a set whose charter digest is not
    its own charter's (audit SRIA-TRUST-02). ``digest`` is the identity of the
    policy itself, which every Arbiter decision records.
    """

    campaign_id: str
    obligations: tuple[ValidationObligation, ...] = ()
    charter_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "obligations", tuple(self.obligations))
        ids = [o.obligation_id for o in self.obligations]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate obligation ids: {sorted(duplicates)}")

    @property
    def is_empty(self) -> bool:
        return not self.obligations

    @property
    def digest(self) -> str:
        """Canonical identity of this policy: campaign, charter and obligations."""
        blob = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def of_kind(self, kind: ObligationKind) -> tuple[ValidationObligation, ...]:
        kind = ObligationKind(kind)
        return tuple(o for o in self.obligations if o.kind is kind)

    @property
    def required_critics(self) -> tuple[CriticClass, ...]:
        return tuple(
            CriticClass(o.target)
            for o in self.of_kind(ObligationKind.REQUIRED_CRITIC)
        )

    @property
    def required_checks(self) -> tuple[str, ...]:
        return tuple(o.target for o in self.of_kind(ObligationKind.REQUIRED_CHECK))

    @property
    def required_domain_checks(self) -> tuple[str, ...]:
        return tuple(
            o.target for o in self.of_kind(ObligationKind.REQUIRED_DOMAIN_CHECK)
        )

    @property
    def required_uncertainty_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(
            UncertaintyChannel(o.target)
            for o in self.of_kind(ObligationKind.REQUIRED_UNCERTAINTY_CHANNEL)
        )

    @property
    def required_contexts(self) -> tuple[str, ...]:
        return tuple(o.target for o in self.of_kind(ObligationKind.REQUIRED_CONTEXT))

    @property
    def required_calibration_verdicts(self) -> tuple[CalibrationVerdict, ...]:
        return tuple(
            CalibrationVerdict(o.target)
            for o in self.of_kind(ObligationKind.REQUIRED_CALIBRATION_STATUS)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBLIGATION_SET_SCHEMA,
            "campaign_id": self.campaign_id,
            "obligations": [o.to_dict() for o in self.obligations],
            "charter_digest": self.charter_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObligationSet":
        require_schema(payload, OBLIGATION_SET_SCHEMA)
        return cls(
            campaign_id=payload["campaign_id"],
            obligations=tuple(
                ValidationObligation.from_dict(o)
                for o in payload.get("obligations", ())
            ),
            charter_digest=payload.get("charter_digest", ""),
        )


def obligations_from_charter(
    charter: CampaignCharter,
    *,
    required_critics: Iterable[CriticClass] = (),
    required_checks: Iterable[str] = (),
    required_domain_checks: Iterable[str] = (),
    required_uncertainty_channels: Iterable[UncertaintyChannel] = (),
    required_calibration_verdicts: Iterable[CalibrationVerdict] = (),
    context_decision_id: str | None = None,
) -> ObligationSet:
    """Derive obligations from a charter, attributing each to that charter.

    The charter's own ``confidence_requirements`` are the authority; the
    explicit arguments let a campaign state assurance requirements that the M1
    charter vocabulary does not yet model, without inventing global defaults.

    ``context_decision_id`` binds the policy to one of the charter's terminal
    decisions: the set then carries a ``REQUIRED_CONTEXT`` obligation, and the
    Arbiter refuses VALID over evidence whose ``context_ref`` is not exactly
    ``charter:<this charter's digest>#decision:<that id>``. A decision the
    charter does not declare is refused here, not bound.
    """
    source = f"charter:{charter.campaign_id}"
    obligations: list[ValidationObligation] = []

    for critic in required_critics:
        critic = CriticClass(critic)
        obligations.append(
            ValidationObligation(
                obligation_id=f"critic:{critic.value}",
                kind=ObligationKind.REQUIRED_CRITIC,
                target=critic.value,
                source=source,
            )
        )
    for name in required_checks:
        obligations.append(
            ValidationObligation(
                obligation_id=f"check:{name}",
                kind=ObligationKind.REQUIRED_CHECK,
                target=str(name),
                source=source,
            )
        )
    for name in required_domain_checks:
        obligations.append(
            ValidationObligation(
                obligation_id=f"domain_check:{name}",
                kind=ObligationKind.REQUIRED_DOMAIN_CHECK,
                target=str(name),
                source=source,
            )
        )
    for channel in required_uncertainty_channels:
        channel = UncertaintyChannel(channel)
        obligations.append(
            ValidationObligation(
                obligation_id=f"uncertainty:{channel.value}",
                kind=ObligationKind.REQUIRED_UNCERTAINTY_CHANNEL,
                target=channel.value,
                source=source,
                detail="channel must be quantified before VALID",
            )
        )
    for verdict in required_calibration_verdicts:
        verdict = CalibrationVerdict(verdict)
        obligations.append(
            ValidationObligation(
                obligation_id=f"calibration:{verdict.value}",
                kind=ObligationKind.REQUIRED_CALIBRATION_STATUS,
                target=verdict.value,
                source=source,
            )
        )

    # Charter confidence requirements are recorded so their provenance
    # survives even though M3 does not yet evaluate ValidationLevel directly.
    for requirement in charter.confidence_requirements:
        for level in requirement.required_levels:
            obligations.append(
                ValidationObligation(
                    obligation_id=f"confidence:{requirement.requirement_id}:{level.value}",
                    kind=ObligationKind.REQUIRED_CHECK,
                    target=f"validation_level:{level.value}",
                    source=f"{source}#{requirement.requirement_id}",
                    detail=requirement.description,
                )
            )

    if context_decision_id is not None:
        declared = {d.decision_id for d in charter.terminal_decisions}
        if context_decision_id not in declared:
            raise ValueError(
                f"decision {context_decision_id!r} is not a terminal decision of charter "
                f"{charter.campaign_id!r} (declared: {sorted(declared)}); a policy cannot be bound "
                f"to a decision its charter never made"
            )
        obligations.append(
            ValidationObligation(
                obligation_id=f"context:{context_decision_id}",
                kind=ObligationKind.REQUIRED_CONTEXT,
                target=charter_context_ref(charter.digest, context_decision_id),
                source=source,
                detail="evidence must have been produced for exactly this charter and decision",
            )
        )

    return ObligationSet(
        campaign_id=charter.campaign_id,
        obligations=tuple(obligations),
        charter_digest=charter.digest,
    )
