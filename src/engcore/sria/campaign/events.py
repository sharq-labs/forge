"""M5M — the append-only campaign event log.

Every meaningful transition in a campaign run is recorded here, in order, and
the record is the thing a resume reads back. That makes the log the campaign's
memory rather than a debugging aid, so it has two properties that a list of log
lines does not:

**Append-only.** There is no update, no delete, no reordering. The only way to
add an event is :meth:`CampaignEventLog.append`, and the events themselves are
frozen. A campaign whose history could be rewritten could not be audited, and a
resume that read a rewritten history would silently diverge from what actually
happened.

**Hash-chained.** Each event carries the digest of its predecessor, so removing
or altering an event anywhere in the chain is detectable by
:meth:`CampaignEventLog.verify_chain`. This is tamper-evidence, not tamper-
proofing: it catches truncation and edits, and it makes "the log says the action
executed" a claim someone can check.

This is deliberately not an event-sourcing framework. There is no projection
engine, no bus, no handler registry. It is an ordered, verifiable list of typed
facts that the runner writes and the resume logic reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..decision.replay import canonical_digest

EVENT_SCHEMA = schema_string("sria_campaign_event")
EVENT_LOG_SCHEMA = schema_string("sria_campaign_event_log")


def _event_payload_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _event_payload_snapshot(item)
            for key, item in sorted(dict.items(value))
        }
    if isinstance(value, list):
        return [_event_payload_snapshot(item) for item in list.__iter__(value)]
    if isinstance(value, tuple):
        return tuple(_event_payload_snapshot(item) for item in value)
    return value


def _event_payload_fingerprint(value: Any) -> str:
    return canonical_digest(_event_payload_snapshot(value))


class _ImmutableEventMapping(dict[str, Any]):
    """Dict-compatible event payload mapping that rejects mutation."""

    _MUTATION_MESSAGE = "campaign event payloads are immutable"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if getattr(self, "_initialized", False):
            self._reject_mutation()
        super().__init__(*args, **kwargs)
        self._fingerprint = _event_payload_fingerprint(self)
        self._initialized = True

    def _reject_mutation(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(self._MUTATION_MESSAGE)

    def _validate_unchanged(self) -> None:
        if self._fingerprint != _event_payload_fingerprint(self):
            self._reject_mutation()

    def __contains__(self, key: object) -> bool:
        self._validate_unchanged()
        return dict.__contains__(self, key)

    def __getitem__(self, key: str) -> Any:
        self._validate_unchanged()
        return dict.__getitem__(self, key)

    def __iter__(self):
        self._validate_unchanged()
        return dict.__iter__(self)

    def __len__(self) -> int:
        self._validate_unchanged()
        return dict.__len__(self)

    def __setitem__(self, key: str, value: Any) -> None:
        self._reject_mutation()

    def __delitem__(self, key: str) -> None:
        self._reject_mutation()

    def clear(self) -> None:
        self._reject_mutation()

    def pop(self, key: str, default: Any = None) -> Any:
        self._reject_mutation()

    def popitem(self) -> tuple[str, Any]:
        self._reject_mutation()

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._reject_mutation()

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._reject_mutation()

    def __ior__(self, other: Mapping[str, Any]) -> "_ImmutableEventMapping":
        self._reject_mutation()

    def get(self, key: str, default: Any = None) -> Any:
        self._validate_unchanged()
        return dict.get(self, key, default)

    def items(self):
        self._validate_unchanged()
        return dict.items(self)

    def keys(self):
        self._validate_unchanged()
        return dict.keys(self)

    def values(self):
        self._validate_unchanged()
        return dict.values(self)


class _ImmutableEventList(list[Any]):
    """List-compatible event payload sequence that rejects mutation."""

    _MUTATION_MESSAGE = "campaign event payloads are immutable"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if getattr(self, "_initialized", False):
            self._reject_mutation()
        super().__init__(*args, **kwargs)
        self._fingerprint = _event_payload_fingerprint(self)
        self._initialized = True

    def _reject_mutation(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(self._MUTATION_MESSAGE)

    def _validate_unchanged(self) -> None:
        if self._fingerprint != _event_payload_fingerprint(self):
            self._reject_mutation()

    def __getitem__(self, index: Any) -> Any:
        self._validate_unchanged()
        return list.__getitem__(self, index)

    def __iter__(self):
        self._validate_unchanged()
        return list.__iter__(self)

    def __len__(self) -> int:
        self._validate_unchanged()
        return list.__len__(self)

    def __setitem__(self, index: Any, value: Any) -> None:
        self._reject_mutation()

    def __delitem__(self, index: Any) -> None:
        self._reject_mutation()

    def append(self, value: Any) -> None:
        self._reject_mutation()

    def clear(self) -> None:
        self._reject_mutation()

    def extend(self, values: Any) -> None:
        self._reject_mutation()

    def insert(self, index: int, value: Any) -> None:
        self._reject_mutation()

    def pop(self, index: int = -1) -> Any:
        self._reject_mutation()

    def remove(self, value: Any) -> None:
        self._reject_mutation()

    def reverse(self) -> None:
        self._reject_mutation()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._reject_mutation()

    def __iadd__(self, values: Any) -> "_ImmutableEventList":
        self._reject_mutation()

    def __imul__(self, value: int) -> "_ImmutableEventList":
        self._reject_mutation()


def _freeze_event_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _ImmutableEventMapping(
            {str(key): _freeze_event_payload(item) for key, item in dict(value).items()}
        )
    if isinstance(value, list | tuple):
        return _ImmutableEventList([_freeze_event_payload(item) for item in value])
    return value


def _thaw_event_payload(value: Any) -> Any:
    if isinstance(value, (_ImmutableEventMapping, _ImmutableEventList)):
        value._validate_unchanged()
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_event_payload(item)
            for key, item in sorted(dict(value).items())
        }
    if isinstance(value, list | tuple):
        return [_thaw_event_payload(item) for item in value]
    return value


class CampaignEventType(str, Enum):
    """What happened. One member per auditable transition."""

    CAMPAIGN_CREATED = "campaign_created"
    SNAPSHOT_CREATED = "snapshot_created"
    CANDIDATES_GENERATED = "candidates_generated"
    DECISION_RECOMMENDED = "decision_recommended"
    ACTION_SELECTED = "action_selected"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EVIDENCE_CREATED = "evidence_created"
    CRITICS_COMPLETED = "critics_completed"
    ARBITER_DECIDED = "arbiter_decided"
    EVIDENCE_ADMITTED = "evidence_admitted"
    EVIDENCE_NOT_ADMITTED = "evidence_not_admitted"
    CALIBRATION_UPDATED = "calibration_updated"
    BUDGET_UPDATED = "budget_updated"
    ITERATION_COMPLETED = "iteration_completed"
    STOP_PROPOSED = "stop_proposed"
    STOP_REVIEWED = "stop_reviewed"
    CAMPAIGN_PAUSED = "campaign_paused"
    CAMPAIGN_COMPLETED = "campaign_completed"
    CAMPAIGN_FAILED = "campaign_failed"


@dataclass(frozen=True)
class CampaignEvent:
    """One immutable fact, positioned in a verifiable chain."""

    sequence: int
    event_type: CampaignEventType
    run_id: str
    iteration: int
    payload: Mapping[str, Any] = field(default_factory=dict)
    at: str = ""
    #: Digest of the preceding event. Empty only for the first event.
    prev_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", CampaignEventType(self.event_type))
        if self.sequence < 0:
            raise ValueError("event sequence must be non-negative")
        if self.iteration < 0:
            raise ValueError("event iteration must be non-negative")
        if not str(self.run_id).strip():
            raise ValueError("campaign event requires a run_id")
        object.__setattr__(self, "payload", _freeze_event_payload(self.payload))

    @property
    def digest(self) -> str:
        """Content digest, including the predecessor's — this is the chain."""
        return canonical_digest(self._chain_payload())

    def _chain_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "payload": self.payload,
            "at": self.at,
            "prev_digest": self.prev_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        return _thaw_event_payload({"schema": EVENT_SCHEMA, **self._chain_payload()})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignEvent":
        require_schema(payload, EVENT_SCHEMA)
        return cls(
            sequence=int(payload["sequence"]),
            event_type=CampaignEventType(payload["event_type"]),
            run_id=payload["run_id"],
            iteration=int(payload.get("iteration", 0)),
            payload=payload.get("payload", {}),
            at=payload.get("at", ""),
            prev_digest=payload.get("prev_digest", ""),
        )


class ChainBroken(Exception):
    """The event log was truncated or edited after the fact."""


class CampaignEventLog:
    """Ordered, append-only, hash-chained history of one campaign run."""

    def __init__(self, run_id: str, events: tuple[CampaignEvent, ...] = ()) -> None:
        if not str(run_id).strip():
            raise ValueError("campaign event log requires a run_id")
        self._run_id = run_id
        self._events: list[CampaignEvent] = list(events)
        if self._events:
            self.verify_chain()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def events(self) -> tuple[CampaignEvent, ...]:
        return tuple(self._events)

    def event_at(self, sequence: int) -> CampaignEvent:
        """Return one absolute sequence entry without copying whole history."""
        if sequence < 0 or sequence >= len(self._events):
            raise IndexError("event sequence outside the log")
        return self._events[sequence]

    def events_from(self, sequence: int) -> tuple[CampaignEvent, ...]:
        """Return only the suffix beginning at ``sequence``."""
        if sequence < 0 or sequence > len(self._events):
            raise IndexError("event suffix starts outside the log")
        return tuple(self._events[sequence:])

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[CampaignEvent]:
        return iter(tuple(self._events))

    @property
    def head_digest(self) -> str:
        return self._events[-1].digest if self._events else ""

    def append(
        self,
        event_type: CampaignEventType,
        *,
        iteration: int,
        payload: Mapping[str, Any] | None = None,
        at: str = "",
    ) -> CampaignEvent:
        """The only way to add history. There is no update and no delete."""
        event = CampaignEvent(
            sequence=len(self._events),
            event_type=event_type,
            run_id=self._run_id,
            iteration=iteration,
            payload=payload or {},
            at=at,
            prev_digest=self.head_digest,
        )
        self._events.append(event)
        return event

    def of_type(self, *types: CampaignEventType) -> tuple[CampaignEvent, ...]:
        wanted = {CampaignEventType(t) for t in types}
        return tuple(e for e in self._events if e.event_type in wanted)

    def in_iteration(self, iteration: int) -> tuple[CampaignEvent, ...]:
        return tuple(e for e in self._events if e.iteration == iteration)

    def last(
        self, event_type: CampaignEventType, *, iteration: int | None = None
    ) -> CampaignEvent | None:
        wanted = CampaignEventType(event_type)
        for event in reversed(self._events):
            if event.event_type is not wanted:
                continue
            if iteration is not None and event.iteration != iteration:
                continue
            return event
        return None

    def has(self, event_type: CampaignEventType, *, iteration: int) -> bool:
        return self.last(event_type, iteration=iteration) is not None

    def verify_chain(self) -> bool:
        """Detect truncation, reordering or edits. Raises on a broken chain."""
        previous = ""
        for index, event in enumerate(self._events):
            if event.sequence != index:
                raise ChainBroken(
                    f"event {index} declares sequence {event.sequence}; the log "
                    f"was reordered or an entry was removed"
                )
            if event.run_id != self._run_id:
                raise ChainBroken(
                    f"event {index} belongs to run {event.run_id!r}, not "
                    f"{self._run_id!r}"
                )
            if event.prev_digest != previous:
                raise ChainBroken(
                    f"event {index} ({event.event_type.value}) does not follow "
                    f"its predecessor; the log was edited after the fact"
                )
            previous = event.digest
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVENT_LOG_SCHEMA,
            "run_id": self._run_id,
            "events": [e.to_dict() for e in self._events],
            "head_digest": self.head_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignEventLog":
        require_schema(payload, EVENT_LOG_SCHEMA)
        log = cls(
            run_id=payload["run_id"],
            events=tuple(
                CampaignEvent.from_dict(e) for e in payload.get("events", ())
            ),
        )
        declared = payload.get("head_digest", "")
        if declared and declared != log.head_digest:
            raise ChainBroken(
                "the stored head digest does not match the reloaded events"
            )
        return log
