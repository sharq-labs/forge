"""Design history: an append-only, hash-chained record of every attempt, including failures.

D3 :mod:`.memory` retains EVALUATED observations for selection.  This module
records what memory does not: every attempt a search made, whatever its
outcome -- success, failure, refusal, constraint violation, provider failure,
partial result -- with the verdict, uncertainty status, fidelity, provider
and lineage it had.  A failed candidate is information.

Each entry carries the digest of the entry before it, so the history is
tamper-evident: rewriting or deleting an old attempt changes every later
head digest.

:meth:`DesignHistory.should_skip` stops a search rediscovering a known-invalid
candidate.  Only DETERMINISTIC negatives are skipped (a refusal or a
constraint violation for the same candidate identity at the same rung, under
the same evaluation context digest).  A provider failure is not deterministic:
it is retried only under a different provider identity.

This is an auditable engineering search history.  It is not a learned model,
and nothing here predicts an outcome that was not observed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem

HISTORY_ENTRY_SCHEMA = "engcore.design.history_entry/1"
GENESIS = "0" * 64


class AttemptOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    REFUSED = "refused"
    CONSTRAINT_VIOLATED = "constraint_violated"
    CONTRADICTED = "contradicted"        # evaluated and did not meet the declared criteria
    PROVIDER_FAILED = "provider_failed"

    @property
    def deterministic_negative(self) -> bool:
        return self in (AttemptOutcome.REFUSED, AttemptOutcome.CONSTRAINT_VIOLATED, AttemptOutcome.CONTRADICTED)


@dataclass(frozen=True)
class DesignAttempt:
    """One attempt: candidate identity, rung, context, outcome, verdict, uncertainty, provider, lineage and why."""

    candidate_key: str
    rung_id: str
    context_digest: str
    outcome: AttemptOutcome
    reason: str
    provider: str = ""
    verdict: str = "not_assessed"
    uncertainty: str = "unknown"
    violated_constraints: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    improvement_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", AttemptOutcome(self.outcome))
        for label in ("candidate_key", "rung_id", "context_digest", "reason"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a design attempt records its {label}")
        if self.outcome is AttemptOutcome.CONSTRAINT_VIOLATED and not self.violated_constraints:
            raise InvalidScientificProblem("a constraint violation names the violated constraints")
        if self.outcome is not AttemptOutcome.CONSTRAINT_VIOLATED and self.violated_constraints:
            raise InvalidScientificProblem("violated constraints are recorded only on a constraint-violated attempt")
        if self.outcome is AttemptOutcome.PROVIDER_FAILED and not str(self.provider).strip():
            raise InvalidScientificProblem("a provider failure names the provider identity")
        if self.verdict in ("validated", "supported_by_validation") and self.outcome is not AttemptOutcome.SUCCEEDED:
            raise InvalidScientificProblem("only a succeeded attempt can carry a validation-derived verdict")
        object.__setattr__(self, "violated_constraints", tuple(sorted(self.violated_constraints)))
        object.__setattr__(self, "parents", tuple(sorted(self.parents)))

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_key": self.candidate_key, "rung_id": self.rung_id, "context_digest": self.context_digest,
                "outcome": self.outcome.value, "reason": self.reason, "provider": self.provider, "verdict": self.verdict,
                "uncertainty": self.uncertainty, "violated_constraints": list(self.violated_constraints), "parents": list(self.parents),
                "improvement_note": self.improvement_note}


@dataclass(frozen=True)
class HistoryEntry:
    sequence: int
    previous: str
    attempt: DesignAttempt

    @property
    def digest(self) -> str:
        return canonical_digest({"schema": HISTORY_ENTRY_SCHEMA, "sequence": self.sequence, "previous": self.previous,
                                 "attempt": self.attempt.to_dict()})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HISTORY_ENTRY_SCHEMA, "sequence": self.sequence, "previous": self.previous, "attempt": self.attempt.to_dict(),
                "digest": self.digest}


class DesignHistory:
    """Append-only attempt log with deterministic-negative de-duplication."""

    def __init__(self, entries: Iterable[HistoryEntry] = ()) -> None:
        self._entries: list[HistoryEntry] = []
        for e in entries:
            self._append_entry(e)

    def _append_entry(self, entry: HistoryEntry) -> None:
        if entry.sequence != len(self._entries) or entry.previous != self.head:
            raise InvalidScientificProblem("history entry does not extend the current head; the log is not rewritten")
        self._entries.append(entry)

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[HistoryEntry, ...]:
        return tuple(self._entries)

    def record(self, attempt: DesignAttempt) -> HistoryEntry:
        if not isinstance(attempt, DesignAttempt):
            raise InvalidScientificProblem("history records DesignAttempt records")
        entry = HistoryEntry(len(self._entries), self.head, attempt)
        self._append_entry(entry)
        return entry

    def attempts_of(self, candidate_key: str, rung_id: str | None = None) -> tuple[DesignAttempt, ...]:
        return tuple(e.attempt for e in self._entries if e.attempt.candidate_key == candidate_key
                     and (rung_id is None or e.attempt.rung_id == rung_id))

    def known_negative(self, candidate_key: str, rung_id: str, context_digest: str, provider: str) -> DesignAttempt | None:
        """The recorded DETERMINISTIC negative (refused / constraint violated / contradicted) for this candidate, rung,
        context AND provider, if any.  Successes and provider failures are never skipped: a success may need a fresh
        observation for promotion, and a provider failure may be transient.  Another provider is never blocked."""
        for a in reversed(self.attempts_of(candidate_key, rung_id)):
            if a.context_digest == context_digest and a.provider == provider and a.outcome.deterministic_negative:
                return a
        return None

    def should_skip(self, candidate_key: str, rung_id: str, context_digest: str, *, provider: str) -> tuple[bool, str]:
        a = self.known_negative(candidate_key, rung_id, context_digest, provider)
        if a is None:
            return False, ""
        return True, f"already {a.outcome.value} at {rung_id!r} by {provider} in this context: {a.reason}"

    def outcome_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self._entries:
            counts[e.attempt.outcome.value] = counts.get(e.attempt.outcome.value, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "search_history_not_evidence", "head": self.head, "entries": [e.to_dict() for e in self._entries]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, expected_head: str | None = None) -> "DesignHistory":
        """Rebuild and verify.  ``expected_head`` (e.g. a DiscoveryRun's history_head) detects a truncated tail."""
        entries = []
        for p in payload["entries"]:
            a = p["attempt"]
            attempt = DesignAttempt(a["candidate_key"], a["rung_id"], a["context_digest"], a["outcome"], a["reason"], a["provider"],
                                    a["verdict"], a["uncertainty"], tuple(a["violated_constraints"]), tuple(a["parents"]),
                                    a.get("improvement_note", ""))
            entry = HistoryEntry(p["sequence"], p["previous"], attempt)
            if entry.digest != p["digest"]:
                raise InvalidScientificProblem(f"history entry {p['sequence']} does not match its digest")
            entries.append(entry)
        history = cls(entries)
        if history.head != payload["head"]:
            raise InvalidScientificProblem("history head does not match its entries")
        if expected_head is not None and history.head != expected_head:
            raise InvalidScientificProblem("history head is not the anchored head; entries were removed or added")
        return history
