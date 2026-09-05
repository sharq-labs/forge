"""Typed critic assessment records.

A critic's entire output is one of these. It cannot write belief, cannot alter
evidence, and cannot admit anything — it can only say what it checked, what it
found, and what verdict that supports.

The type carries three distinctions that a free-text report loses:

**Checked vs. skipped.** ``checks_skipped`` is a first-class field, so "we did
not look" is visible instead of being indistinguishable from "we looked and it
was fine". The Arbiter reads it directly.

**NOT_ASSESSED vs. PASS.** Absence of a diagnostic never becomes a pass. A
critic that could not evaluate a mandatory check returns ``NOT_ASSESSED``, and
that propagates all the way to blocking a final VALID.

**Findings are typed.** Human-readable messages ride along, but severity,
category and the check they came from are structured, so an Arbiter reasons
over data rather than parsing prose.

Mapping to frozen M1: the Scientific Core's
:class:`~engcore.sria.evidence.AssessmentVerdict` has no ``NOT_ASSESSED``
member, so :meth:`CriticAssessment.to_evidence_assessment` maps it to
``INCONCLUSIVE`` — the closest frozen term that does not overclaim — while the
richer verdict is preserved here. Mapping rather than extending keeps M1
frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..evidence import Assessment, AssessmentVerdict
from ..provenance import AssessmentProvenance
from .uncertainty_budget import ChannelState, UncertaintyBudget

ASSESSMENT_SCHEMA = schema_string("sria_critic_assessment")
FINDING_SCHEMA = schema_string("sria_critic_finding")
CHECK_SCHEMA = schema_string("sria_critic_check")
UNCERTAINTY_OBSERVATION_SCHEMA = schema_string("sria_uncertainty_observation")


class CriticClass(str, Enum):
    """Which kind of trust a critic speaks to. Deliberately not one critic."""

    NUMERICAL = "numerical"        # did the computation compute correctly?
    DOMAIN = "domain"              # is the science admissible? (Domain Pack)
    CALIBRATION = "calibration"    # are the computational models trustworthy?
    PROCESS = "process"            # were the declared obligations followed?


class CriticVerdict(str, Enum):
    """A critic's conclusion.

    ``NOT_ASSESSED`` is the crucial member: it separates "checked and fine"
    from "could not check", which a PASS/FAIL pair cannot express.
    """

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_ASSESSED = "not_assessed"


class Severity(str, Enum):
    INFO = "info"
    ADVISORY = "advisory"
    MAJOR = "major"
    BLOCKING = "blocking"


class FindingImpact(str, Enum):
    """What a finding is entitled to do to the final verdict.

    The distinction M3.1 exists to draw. ``ASSURANCE_BLOCKING`` says "this
    cannot be certified"; ``EVIDENCE_INVALIDATING`` says "the subject
    itself has been shown wrong". An untrusted runtime cost model is the
    former and must never be allowed to act as the latter — it cannot make
    a correctly computed voltage scientifically false.
    """

    #: Blocks VALID. Yields INCONCLUSIVE / NOT_ASSESSED, never INVALID.
    ASSURANCE_BLOCKING = "assurance_blocking"
    #: Evidence-backed invalidation of the subject. May support INVALID.
    EVIDENCE_INVALIDATING = "evidence_invalidating"


@dataclass(frozen=True)
class CheckRecord:
    """One named check a critic ran, or explicitly did not."""

    name: str
    outcome: CriticVerdict
    mandatory: bool = False
    detail: str = ""
    observed: float | None = None
    threshold: float | None = None
    threshold_source: str = ""

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("check requires a name")
        object.__setattr__(self, "outcome", CriticVerdict(self.outcome))
        if not isinstance(self.mandatory, bool):
            raise ValueError("check 'mandatory' must be an explicit bool")
        if self.threshold is not None and not str(self.threshold_source).strip():
            # A bare number in code is exactly the "global magic number" the
            # charter/domain-pack ownership rule exists to prevent.
            raise ValueError(
                f"check {self.name!r} carries a threshold with no declared "
                f"source; thresholds belong to a charter, domain pack or "
                f"registered policy, not to critic code"
            )

    @property
    def blocks_valid(self) -> bool:
        return self.mandatory and self.outcome is not CriticVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHECK_SCHEMA,
            "name": self.name,
            "outcome": self.outcome.value,
            "mandatory": self.mandatory,
            "detail": self.detail,
            "observed": self.observed,
            "threshold": self.threshold,
            "threshold_source": self.threshold_source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckRecord":
        require_schema(payload, CHECK_SCHEMA)
        return cls(
            name=payload["name"],
            outcome=CriticVerdict(payload["outcome"]),
            mandatory=bool(payload.get("mandatory", False)),
            detail=payload.get("detail", ""),
            observed=payload.get("observed"),
            threshold=payload.get("threshold"),
            threshold_source=payload.get("threshold_source", ""),
        )


@dataclass(frozen=True)
class Finding:
    """A typed observation. The message is commentary, the fields are data."""

    code: str
    severity: Severity
    category: str
    message: str = ""
    check_name: str = ""
    impact: FindingImpact = FindingImpact.ASSURANCE_BLOCKING

    def __post_init__(self) -> None:
        if not str(self.code).strip():
            raise ValueError("finding requires a code")
        object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "impact", FindingImpact(self.impact))
        if (
            self.impact is FindingImpact.EVIDENCE_INVALIDATING
            and self.severity is not Severity.BLOCKING
        ):
            raise ValueError(
                f"finding {self.code!r} claims to invalidate the subject but is "
                f"only {self.severity.value}; invalidation must be blocking"
            )

    @property
    def invalidates_subject(self) -> bool:
        return self.impact is FindingImpact.EVIDENCE_INVALIDATING

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FINDING_SCHEMA,
            "code": self.code,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "check_name": self.check_name,
            "impact": self.impact.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Finding":
        require_schema(payload, FINDING_SCHEMA)
        return cls(
            code=payload["code"],
            severity=Severity(payload["severity"]),
            category=payload.get("category", ""),
            message=payload.get("message", ""),
            check_name=payload.get("check_name", ""),
            impact=FindingImpact(
                payload.get("impact", FindingImpact.ASSURANCE_BLOCKING.value)
            ),
        )


@dataclass(frozen=True)
class UncertaintyObservation:
    """What a critic saw in the uncertainty budget, per channel."""

    channel: str
    state: str
    quantified: bool
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_OBSERVATION_SCHEMA,
            "channel": self.channel,
            "state": self.state,
            "quantified": self.quantified,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyObservation":
        require_schema(payload, UNCERTAINTY_OBSERVATION_SCHEMA)
        return cls(
            channel=payload["channel"],
            state=payload["state"],
            quantified=bool(payload["quantified"]),
            note=payload.get("note", ""),
        )


def observations_from_budget(
    budget: UncertaintyBudget,
) -> tuple[UncertaintyObservation, ...]:
    """Record every channel's state, including the ones nobody declared.

    Iterates the closed channel vocabulary rather than the budget's entries,
    so an undeclared channel appears as UNKNOWN instead of being absent from
    the audit entirely.
    """
    from ..uncertainty import UncertaintyChannel

    out = []
    for channel in UncertaintyChannel:
        entry = budget.entry(channel)
        out.append(
            UncertaintyObservation(
                channel=channel.value,
                state=entry.state.value,
                quantified=entry.is_quantified,
                note=entry.rationale,
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class CriticAssessment:
    """The complete, immutable output of one critic run."""

    assessment_id: str
    critic_id: str
    critic_version: str
    critic_class: CriticClass
    subject_ref: str                       # evidence id or result id
    verdict: CriticVerdict
    provenance: AssessmentProvenance
    checks: tuple[CheckRecord, ...] = ()
    checks_skipped: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    uncertainty_observations: tuple[UncertaintyObservation, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        for label in ("assessment_id", "critic_id", "subject_ref"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"critic assessment requires {label}")
        object.__setattr__(self, "critic_class", CriticClass(self.critic_class))
        object.__setattr__(self, "verdict", CriticVerdict(self.verdict))
        if not isinstance(self.provenance, AssessmentProvenance):
            raise ValueError(
                "critic assessment requires AssessmentProvenance; an "
                "unattributable judgement cannot be replayed"
            )
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "checks_skipped", tuple(self.checks_skipped))
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(
            self, "uncertainty_observations", tuple(self.uncertainty_observations)
        )

        # A verdict of PASS while a mandatory check did not pass is internally
        # inconsistent, and it is the exact inconsistency M3 must prevent.
        if self.verdict is CriticVerdict.PASS:
            blocking = [c.name for c in self.checks if c.blocks_valid]
            if blocking:
                raise ValueError(
                    f"critic {self.critic_id!r} reports PASS while mandatory "
                    f"checks {sorted(blocking)} did not pass"
                )

    # ---- views ----------------------------------------------------------
    @property
    def mandatory_checks(self) -> tuple[CheckRecord, ...]:
        return tuple(c for c in self.checks if c.mandatory)

    @property
    def blocking_checks(self) -> tuple[CheckRecord, ...]:
        return tuple(c for c in self.checks if c.blocks_valid)

    @property
    def has_blocking_findings(self) -> bool:
        return any(f.severity is Severity.BLOCKING for f in self.findings)

    @property
    def invalidating_findings(self) -> tuple[Finding, ...]:
        """Findings entitled to support a scientific INVALID."""
        return tuple(f for f in self.findings if f.invalidates_subject)

    @property
    def unknown_uncertainty_channels(self) -> tuple[str, ...]:
        return tuple(
            o.channel
            for o in self.uncertainty_observations
            if o.state == ChannelState.UNKNOWN.value
        )

    def check(self, name: str) -> CheckRecord | None:
        for record in self.checks:
            if record.name == name:
                return record
        return None

    # ---- bridge to the frozen M1 evidence assessment --------------------
    def to_evidence_assessment(self) -> Assessment:
        """Convert for attachment to Evidence via ``with_assessment``.

        ``NOT_ASSESSED`` has no M1 equivalent and maps to ``INCONCLUSIVE``:
        the closest frozen term that does not claim more than was established.
        The precise verdict remains on this record.
        """
        mapping = {
            CriticVerdict.PASS: AssessmentVerdict.PASS,
            CriticVerdict.FAIL: AssessmentVerdict.FAIL,
            CriticVerdict.INCONCLUSIVE: AssessmentVerdict.INCONCLUSIVE,
            CriticVerdict.NOT_ASSESSED: AssessmentVerdict.INCONCLUSIVE,
        }
        rationale = self.summary or f"{self.critic_id}: {self.verdict.value}"
        if self.verdict is CriticVerdict.NOT_ASSESSED:
            rationale = f"NOT_ASSESSED (mapped to inconclusive) — {rationale}"
        # The frozen M1 verdict loses NOT_ASSESSED; keep the true verdict in
        # typed provenance metadata so a replay can still tell 'could not
        # check' from 'checked, inconclusive'.
        provenance = replace(
            self.provenance,
            metadata={
                **dict(self.provenance.metadata),
                "critic_verdict": self.verdict.value,
                "critic_class": self.critic_class.value,
                "critic_assessment_id": self.assessment_id,
            },
        )
        return Assessment(
            verdict=mapping[self.verdict],
            provenance=provenance,
            rationale=rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSESSMENT_SCHEMA,
            "assessment_id": self.assessment_id,
            "critic_id": self.critic_id,
            "critic_version": self.critic_version,
            "critic_class": self.critic_class.value,
            "subject_ref": self.subject_ref,
            "verdict": self.verdict.value,
            "provenance": self.provenance.to_dict(),
            "checks": [c.to_dict() for c in self.checks],
            "checks_skipped": list(self.checks_skipped),
            "findings": [f.to_dict() for f in self.findings],
            "uncertainty_observations": [
                o.to_dict() for o in self.uncertainty_observations
            ],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CriticAssessment":
        require_schema(payload, ASSESSMENT_SCHEMA)
        return cls(
            assessment_id=payload["assessment_id"],
            critic_id=payload["critic_id"],
            critic_version=payload.get("critic_version", ""),
            critic_class=CriticClass(payload["critic_class"]),
            subject_ref=payload["subject_ref"],
            verdict=CriticVerdict(payload["verdict"]),
            provenance=AssessmentProvenance.from_dict(payload["provenance"]),
            checks=tuple(CheckRecord.from_dict(c) for c in payload.get("checks", ())),
            checks_skipped=tuple(payload.get("checks_skipped", ())),
            findings=tuple(Finding.from_dict(f) for f in payload.get("findings", ())),
            uncertainty_observations=tuple(
                UncertaintyObservation.from_dict(o)
                for o in payload.get("uncertainty_observations", ())
            ),
            summary=payload.get("summary", ""),
        )
