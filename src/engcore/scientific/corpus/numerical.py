"""Which numerical checks were actually performed, and which were not.

A solver reporting "converged" has said one thing about one check. It has not
said its grid was refined, its conditioning measured, its conservation audited
or its backward error bounded. The gap between those is where numerical
credibility is usually lost -- not by claiming a bad number, but by letting the
absence of a study read as its success.

So this record is a roster, not a score. Each declared check is either
performed with a result, or explicitly ``NOT_PERFORMED`` with a stated reason.
There is no third state and no default, which is what makes
:attr:`NumericalEvidence.absent_checks` a usable answer to "what was not
studied here".

A check nothing produced cannot be added: :func:`require_supported` refuses a
result for a check the solver never declared it can perform, so a wrapper
cannot fabricate a convergence study on a solver's behalf.

AND IT BELONGS TO ONE COMPUTATION
----------------------------------
``producer_id`` said which solver; it did not say which run. A convergence
study from yesterday's execution is real evidence about yesterday's execution
and says nothing about this one, but a certification gate comparing only a
producer name would accept it. So numerical evidence carries an
:class:`~engcore.scientific.corpus.authority.EvidenceBinding`, and a gate that
requires numerical evidence checks the binding before the results.

Evidence from another run stays evidence. It simply cannot satisfy this run's
gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from .authority import EvidenceBinding, require_binding
from .source import CorpusError, text

NUMERICAL_CHECK_SCHEMA = schema_string("corpus_numerical_check")
NUMERICAL_EVIDENCE_SCHEMA = schema_string("corpus_numerical_evidence")


class NumericalCheck(str, Enum):
    """The kinds of numerical study this Core knows how to record."""

    CONVERGENCE = "convergence"
    RESIDUAL = "residual"
    CONDITIONING = "conditioning"
    BACKWARD_ERROR = "backward_error"
    CONSERVATION = "conservation"
    REFINEMENT = "refinement"
    STABILITY = "stability"


class CheckOutcome(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    #: Performed, and the result does not decide the question.
    INCONCLUSIVE = "inconclusive"
    #: Not performed. The reason is required.
    NOT_PERFORMED = "not_performed"

    @property
    def was_performed(self) -> bool:
        return self is not CheckOutcome.NOT_PERFORMED


@dataclass(frozen=True, order=True)
class NumericalCheckResult:
    """One numerical check: what was asked, what came back, or why not."""

    check: NumericalCheck
    outcome: CheckOutcome
    detail: str
    measured: float | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check", NumericalCheck(self.check))
        object.__setattr__(self, "outcome", CheckOutcome(self.outcome))
        object.__setattr__(self, "detail", text(self.detail, label="numerical check detail"))
        for label in ("measured", "threshold"):
            value = getattr(self, label)
            if value is None:
                continue
            number = float(value)
            if not math.isfinite(number):
                raise CorpusError(f"numerical check {label} must be finite")
            object.__setattr__(self, label, number)
        if not self.outcome.was_performed and self.measured is not None:
            raise CorpusError(
                f"{self.check.value} is recorded as not performed but carries a "
                f"measured value; a check that did not run produced no number"
            )
        if self.outcome is CheckOutcome.SATISFIED and self.measured is None:
            raise CorpusError(
                f"{self.check.value} is recorded satisfied with no measured value; "
                f"a satisfied check is a measurement, not an assertion"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": NUMERICAL_CHECK_SCHEMA,
            "check": self.check.value,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "measured": self.measured,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NumericalCheckResult":
        require_schema(payload, NUMERICAL_CHECK_SCHEMA)
        return cls(
            NumericalCheck(payload["check"]),
            CheckOutcome(payload["outcome"]),
            payload["detail"],
            payload.get("measured"),
            payload.get("threshold"),
        )


def require_supported(
    supported: tuple[NumericalCheck, ...], result: NumericalCheckResult
) -> NumericalCheckResult:
    """Refuse a result for a check the producer never declared it can perform."""
    declared = {NumericalCheck(item) for item in supported}
    if result.check not in declared and result.outcome.was_performed:
        raise CorpusError(
            f"a result was offered for {result.check.value!r}, which this producer "
            f"does not declare it can perform; a solver must not claim checks it "
            f"cannot produce"
        )
    return result


@dataclass(frozen=True)
class NumericalEvidence:
    """The complete numerical roster for one computation.

    Complete in a specific sense: every check the producer declared it supports
    appears, with an outcome. A supported check with no entry is refused, so
    "we did not get round to it" cannot look like "nothing to report".
    """

    producer_id: str
    supported_checks: tuple[NumericalCheck, ...]
    results: tuple[NumericalCheckResult, ...]
    #: Which computation these numbers came out of. Optional on the record so a
    #: solver can emit its roster before it knows the run identity, and
    #: REQUIRED by certification -- unbound evidence cannot satisfy a gate.
    binding: EvidenceBinding | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "producer_id", text(self.producer_id, label="producer_id"))
        if self.binding is not None:
            require_binding(self.binding, label="numerical evidence binding")
        supported = tuple(
            sorted({NumericalCheck(item) for item in self.supported_checks}, key=lambda i: i.value)
        )
        object.__setattr__(self, "supported_checks", supported)
        results = tuple(sorted(self.results))
        if any(not isinstance(item, NumericalCheckResult) for item in results):
            raise CorpusError("numerical evidence requires NumericalCheckResult records")
        seen = [item.check for item in results]
        if len(seen) != len(set(seen)):
            raise CorpusError("numerical evidence repeats a check")
        missing = sorted(item.value for item in supported if item not in set(seen))
        if missing:
            raise CorpusError(
                f"numerical evidence omits declared checks {missing}; a supported "
                f"check with no entry is silence where a result belongs"
            )
        for item in results:
            require_supported(supported, item)
        object.__setattr__(self, "results", results)

    @property
    def absent_checks(self) -> tuple[str, ...]:
        """Declared checks that were not performed. Explicit, never implied."""
        return tuple(
            item.check.value for item in self.results if not item.outcome.was_performed
        )

    @property
    def violated_checks(self) -> tuple[str, ...]:
        return tuple(
            item.check.value
            for item in self.results
            if item.outcome is CheckOutcome.VIOLATED
        )

    @property
    def performed_checks(self) -> tuple[str, ...]:
        return tuple(
            item.check.value for item in self.results if item.outcome.was_performed
        )

    def belongs_to(self, computation: EvidenceBinding) -> tuple[str, ...]:
        """Why these numbers are not about that computation. Empty means they are."""
        if self.binding is None:
            return (
                f"numerical evidence from {self.producer_id!r} names no execution "
                f"binding, so it cannot be shown to be about this computation",
            )
        return self.binding.mismatches(computation)

    def satisfies(self, required: tuple[NumericalCheck, ...]) -> bool:
        """Whether every required check was performed and none was violated."""
        wanted = {NumericalCheck(item) for item in required}
        by_check = {item.check: item for item in self.results}
        for check in wanted:
            result = by_check.get(check)
            if result is None or not result.outcome.was_performed:
                return False
            if result.outcome is CheckOutcome.VIOLATED:
                return False
        return True

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": NUMERICAL_EVIDENCE_SCHEMA,
            "producer_id": self.producer_id,
            "supported_checks": [item.value for item in self.supported_checks],
            "results": [item.to_dict() for item in self.results],
            "binding": None if self.binding is None else self.binding.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NumericalEvidence":
        require_schema(payload, NUMERICAL_EVIDENCE_SCHEMA)
        return cls(
            payload["producer_id"],
            tuple(NumericalCheck(i) for i in payload.get("supported_checks", ())),
            tuple(NumericalCheckResult.from_dict(i) for i in payload.get("results", ())),
            (
                None
                if payload.get("binding") is None
                else EvidenceBinding.from_dict(payload["binding"])
            ),
        )


__all__ = [
    "NUMERICAL_CHECK_SCHEMA",
    "NUMERICAL_EVIDENCE_SCHEMA",
    "CheckOutcome",
    "NumericalCheck",
    "NumericalCheckResult",
    "NumericalEvidence",
    "require_supported",
]
