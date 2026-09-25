"""Time Engine: canonical time points, windows, histories and a replayable timeline.

This module *extends* the existing transient authority rather than competing
with it:

* :class:`~engcore.scenarios.contracts.ScenarioSpecification` stays the
  authority for what is imposed over a horizon (segments, inputs, scheduled
  events, initial state).  :meth:`Timeline.from_scenario` binds to its digest.
* :class:`~engcore.scientific.multiphysics.receipts.StateTransitionReceipt`
  stays the authority for execution-produced state change.  The timeline holds
  those receipts verbatim and only checks that they chain; it never
  synthesizes one.
* :class:`~engcore.scientific.multiphysics.state.CheckpointRecord` stays the
  participant checkpoint record.  A :class:`TimelineCheckpoint` binds a set of
  them to a deterministic prefix digest of the timeline.

What this module adds is the time vocabulary those records were missing: an
explicit time basis, typed points and windows that refuse cross-basis
comparison, typed markers with fail-closed ordering, usage/exposure/cycle
histories whose gaps are UNKNOWN rather than zero, and replay comparison.

Nothing here is evidence.  A consistent replay, a roundtrip or a digest match
shows that the same record was reproduced -- never that it is physically true.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.receipts import StateTransitionReceipt, require_digest
from ..scientific.multiphysics.state import CheckpointRecord
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import (
    Quantity,
    dimensionality,
    is_ratio_scale,
    normalize_unit,
)
from .contracts import InterpolationKind, NamedQuantity, ScenarioSpecification, TimeSeriesInput

TIME_BASIS_SCHEMA = schema_string("time_basis")
TIME_POINT_SCHEMA = schema_string("time_point")
TIME_WINDOW_SCHEMA = schema_string("time_window")
TIMELINE_EVENT_SCHEMA = schema_string("timeline_event")
HISTORY_ENTRY_SCHEMA = schema_string("history_entry")
HISTORY_SCHEMA = schema_string("quantity_history")
CYCLE_RECORD_SCHEMA = schema_string("cycle_record")
CYCLE_HISTORY_SCHEMA = schema_string("cycle_history")
TIMELINE_CHECKPOINT_SCHEMA = schema_string("timeline_checkpoint")
TIMELINE_SCHEMA = schema_string("timeline")
REPLAY_COMPARISON_SCHEMA = schema_string("timeline_replay_comparison")

#: The epoch every ABSOLUTE_UTC basis must name.  A different origin string is
#: a different clock, not a formatting choice.
UTC_EPOCH_ORIGIN = "1970-01-01T00:00:00Z"

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_TIME_DIMENSION = dimensionality("second")


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier")
    return text


def _strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise InvalidScientificProblem(
            f"{label} shape mismatch; missing={sorted(expected - set(payload))}, "
            f"extra={sorted(set(payload) - expected)}"
        )


def _seconds(value: Quantity, label: str) -> Quantity:
    if not isinstance(value, Quantity) or dimensionality(value.units) != _TIME_DIMENSION:
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    return value.to("second")


def canonical_digest(payload: Any) -> str:
    """sha256 over canonical JSON; the one digest rule used by this module."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Time basis, points and windows
# --------------------------------------------------------------------------


class TimeBasisKind(str, Enum):
    #: Seconds elapsed since a declared, named origin (a scenario start, a
    #: test start).  Two ELAPSED bases with different origins are unrelated.
    ELAPSED = "elapsed"
    #: Seconds since the UTC epoch.  No leap-second or timezone arithmetic is
    #: performed; offsets are whatever the declaring source stated.
    ABSOLUTE_UTC = "absolute_utc"


@dataclass(frozen=True)
class TimeBasis:
    """The clock a time point is measured on.  There is no default basis."""

    basis_id: str
    kind: TimeBasisKind
    origin: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "basis_id", _identifier(self.basis_id, "time basis_id"))
        try:
            kind = TimeBasisKind(self.kind)
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported time basis kind {self.kind!r}") from exc
        object.__setattr__(self, "kind", kind)
        origin = str(self.origin or "").strip()
        if not origin:
            raise InvalidScientificProblem(
                "time basis requires a declared origin; an unnamed origin makes "
                "every offset on it incomparable"
            )
        if kind is TimeBasisKind.ABSOLUTE_UTC and origin != UTC_EPOCH_ORIGIN:
            raise InvalidScientificProblem(
                f"ABSOLUTE_UTC basis must declare origin {UTC_EPOCH_ORIGIN!r}"
            )
        object.__setattr__(self, "origin", origin)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIME_BASIS_SCHEMA, "basis_id": self.basis_id, "kind": self.kind.value, "origin": self.origin}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimeBasis":
        require_schema(payload, TIME_BASIS_SCHEMA)
        _strict_keys(payload, {"schema", "basis_id", "kind", "origin"}, "time basis")
        return cls(payload["basis_id"], payload["kind"], payload["origin"])


@dataclass(frozen=True)
class TimePoint:
    """An instant on one named basis.

    Ordering between points on different bases is refused, not guessed: there
    is no conversion between declared origins in this Core.
    """

    basis_id: str
    offset: Quantity

    def __post_init__(self) -> None:
        if self.basis_id is None or not str(self.basis_id).strip():
            raise InvalidScientificProblem("time point requires a time basis; none was declared")
        object.__setattr__(self, "basis_id", _identifier(self.basis_id, "time point basis_id"))
        object.__setattr__(self, "offset", _seconds(self.offset, "time point offset"))

    @property
    def seconds(self) -> float:
        return self.offset.magnitude

    def _require_same_basis(self, other: "TimePoint") -> None:
        if not isinstance(other, TimePoint):
            raise InvalidScientificProblem("time points compare only with time points")
        if other.basis_id != self.basis_id:
            raise InvalidScientificProblem(
                f"cannot order time points on different bases "
                f"{self.basis_id!r} and {other.basis_id!r}"
            )

    def __lt__(self, other: "TimePoint") -> bool:
        self._require_same_basis(other)
        return self.seconds < other.seconds

    def __le__(self, other: "TimePoint") -> bool:
        self._require_same_basis(other)
        return self.seconds <= other.seconds

    def __gt__(self, other: "TimePoint") -> bool:
        self._require_same_basis(other)
        return self.seconds > other.seconds

    def __ge__(self, other: "TimePoint") -> bool:
        self._require_same_basis(other)
        return self.seconds >= other.seconds

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIME_POINT_SCHEMA, "basis_id": self.basis_id, "offset": self.offset.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimePoint":
        require_schema(payload, TIME_POINT_SCHEMA)
        _strict_keys(payload, {"schema", "basis_id", "offset"}, "time point")
        return cls(payload["basis_id"], Quantity.from_dict(payload["offset"]))


class WindowClosure(str, Enum):
    #: ``[start, end)`` -- the same ownership rule as scenario segments.
    HALF_OPEN = "half_open"
    #: ``[start, end]`` -- used for horizons, whose final instant must belong.
    CLOSED = "closed"


@dataclass(frozen=True)
class TimeWindow:
    start: TimePoint
    end: TimePoint
    closure: WindowClosure = WindowClosure.HALF_OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.start, TimePoint) or not isinstance(self.end, TimePoint):
            raise InvalidScientificProblem("time window bounds must be TimePoint records")
        self.start._require_same_basis(self.end)
        if not self.end.seconds > self.start.seconds:
            raise InvalidScientificProblem(
                "time window end must be strictly after its start; an empty or "
                "inverted window is inconsistent"
            )
        try:
            object.__setattr__(self, "closure", WindowClosure(self.closure))
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported window closure {self.closure!r}") from exc

    @property
    def basis_id(self) -> str:
        return self.start.basis_id

    @property
    def duration(self) -> Quantity:
        return Quantity(self.end.seconds - self.start.seconds, "second")

    def contains(self, point: TimePoint) -> bool:
        self.start._require_same_basis(point)
        if point.seconds < self.start.seconds:
            return False
        if self.closure is WindowClosure.CLOSED:
            return point.seconds <= self.end.seconds
        return point.seconds < self.end.seconds

    def covers(self, other: "TimeWindow") -> bool:
        """Whether ``other`` lies entirely inside this window."""
        self.start._require_same_basis(other.start)
        if other.start.seconds < self.start.seconds or other.end.seconds > self.end.seconds:
            return False
        if other.end.seconds == self.end.seconds and other.closure is WindowClosure.CLOSED:
            return self.closure is WindowClosure.CLOSED
        return True

    def overlaps(self, other: "TimeWindow") -> bool:
        self.start._require_same_basis(other.start)
        return self.start.seconds < other.end.seconds and other.start.seconds < self.end.seconds

    def intersection_seconds(self, other: "TimeWindow") -> float:
        self.start._require_same_basis(other.start)
        return max(0.0, min(self.end.seconds, other.end.seconds) - max(self.start.seconds, other.start.seconds))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIME_WINDOW_SCHEMA, "start": self.start.to_dict(), "end": self.end.to_dict(), "closure": self.closure.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimeWindow":
        require_schema(payload, TIME_WINDOW_SCHEMA)
        _strict_keys(payload, {"schema", "start", "end", "closure"}, "time window")
        return cls(TimePoint.from_dict(payload["start"]), TimePoint.from_dict(payload["end"]), payload["closure"])


# --------------------------------------------------------------------------
# Typed events
# --------------------------------------------------------------------------


class TimelineEventKind(str, Enum):
    #: Requested synchronization instant (from a scenario).  Order-independent.
    SCHEDULED_SYNCHRONIZATION = "scheduled_synchronization"
    #: A synchronization boundary execution actually reached.  Order-independent.
    REACHED_SYNCHRONIZATION = "reached_synchronization"
    #: A declared discontinuity in one quantity (``subject_id``).  Interpolation
    #: across it is refused.
    DISCONTINUITY = "discontinuity"
    #: A requested change of state for ``subject_id``.  A request, never an
    #: applied change: application is proven only by a state-transition receipt.
    STATE_CHANGE_REQUEST = "state_change_request"
    #: Execution stopped here, for the reason named by ``subject_id``.
    TERMINATION = "termination"


#: Kinds whose relative order at a shared instant changes meaning.  Two of them
#: at the same instant must carry explicit, distinct sequence numbers.
ORDER_SENSITIVE_KINDS = frozenset(
    {
        TimelineEventKind.DISCONTINUITY,
        TimelineEventKind.STATE_CHANGE_REQUEST,
        TimelineEventKind.TERMINATION,
    }
)

_SUBJECT_REQUIRED = ORDER_SENSITIVE_KINDS


@dataclass(frozen=True)
class TimelineEvent:
    """A typed marker on the timeline.  Classification: marker, not evidence."""

    event_id: str
    kind: TimelineEventKind
    at: TimePoint
    subject_id: str = ""
    sequence: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _identifier(self.event_id, "timeline event_id"))
        try:
            kind = TimelineEventKind(self.kind)
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported timeline event kind {self.kind!r}") from exc
        object.__setattr__(self, "kind", kind)
        if not isinstance(self.at, TimePoint):
            raise InvalidScientificProblem("timeline event requires a TimePoint")
        subject = str(self.subject_id or "").strip()
        if kind in _SUBJECT_REQUIRED:
            subject = _identifier(subject, f"{kind.value} event subject_id")
        object.__setattr__(self, "subject_id", subject)
        if self.sequence is not None:
            if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
                raise InvalidScientificProblem("timeline event sequence must be a non-negative integer")

    @property
    def order_sensitive(self) -> bool:
        return self.kind in ORDER_SENSITIVE_KINDS

    def sort_key(self) -> tuple:
        return (self.at.seconds, 1 if self.order_sensitive else 0, -1 if self.sequence is None else self.sequence, self.kind.value, self.event_id)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIMELINE_EVENT_SCHEMA, "classification": "timeline_marker_not_evidence", "event_id": self.event_id, "kind": self.kind.value, "at": self.at.to_dict(), "subject_id": self.subject_id, "sequence": self.sequence}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimelineEvent":
        require_schema(payload, TIMELINE_EVENT_SCHEMA)
        _strict_keys(payload, {"schema", "classification", "event_id", "kind", "at", "subject_id", "sequence"}, "timeline event")
        if payload["classification"] != "timeline_marker_not_evidence":
            raise InvalidScientificProblem("timeline event classification mismatch")
        return cls(payload["event_id"], payload["kind"], TimePoint.from_dict(payload["at"]), payload["subject_id"], payload["sequence"])


def order_events(events: Iterable[TimelineEvent]) -> tuple[TimelineEvent, ...]:
    """Deterministically order events, refusing ambiguity.

    Synchronization markers commute with each other: a boundary placed twice
    at one instant is one boundary, so their relative order is declared
    irrelevant and fixed by id for determinism.  Order-sensitive events at a
    shared instant are refused unless every one of them carries an explicit
    sequence and no two sequences are equal.
    """
    items = tuple(events)
    if any(not isinstance(item, TimelineEvent) for item in items):
        raise InvalidScientificProblem("timeline events must be TimelineEvent records")
    ids = [item.event_id for item in items]
    if len(ids) != len(set(ids)):
        raise InvalidScientificProblem("timeline contains duplicate event ids")
    by_instant: dict[float, list[TimelineEvent]] = {}
    for item in items:
        by_instant.setdefault(item.at.seconds, []).append(item)
    for instant, group in by_instant.items():
        sensitive = [item for item in group if item.order_sensitive]
        if len(sensitive) < 2:
            continue
        sequences = [item.sequence for item in sensitive]
        if any(value is None for value in sequences) or len(set(sequences)) != len(sequences):
            raise InvalidScientificProblem(
                f"ambiguous event ordering at {instant} second: "
                f"{sorted(item.event_id for item in sensitive)} are order-sensitive "
                f"and need explicit distinct sequence numbers"
            )
    return tuple(sorted(items, key=TimelineEvent.sort_key))


# --------------------------------------------------------------------------
# Usage / exposure histories
# --------------------------------------------------------------------------


class HistoryKind(str, Enum):
    USAGE = "usage"
    EXPOSURE = "exposure"


class HistoryRepresentation(str, Enum):
    #: The declared value holds over each entry's whole window.  The only
    #: representation supported; anything else is refused at construction.
    PIECEWISE_CONSTANT = "piecewise_constant"


class ValueStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HistoryEntry:
    """A declared value holding over one half-open window."""

    window: TimeWindow
    value: NamedQuantity

    def __post_init__(self) -> None:
        if not isinstance(self.window, TimeWindow) or self.window.closure is not WindowClosure.HALF_OPEN:
            raise InvalidScientificProblem("history entries own half-open windows [start, end)")
        if not isinstance(self.value, NamedQuantity):
            raise InvalidScientificProblem("history entry value must be a NamedQuantity (value plus uncertainty)")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HISTORY_ENTRY_SCHEMA, "window": self.window.to_dict(), "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HistoryEntry":
        require_schema(payload, HISTORY_ENTRY_SCHEMA)
        _strict_keys(payload, {"schema", "window", "value"}, "history entry")
        return cls(TimeWindow.from_dict(payload["window"]), NamedQuantity.from_dict(payload["value"]))


@dataclass(frozen=True)
class HistoryValue:
    """A history query result.  UNKNOWN carries no value -- never a zero."""

    status: ValueStatus
    value: NamedQuantity | None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status is ValueStatus.KNOWN and self.value is None:
            raise InvalidScientificProblem("a KNOWN history value requires a value")
        if self.status is ValueStatus.UNKNOWN and self.value is not None:
            raise InvalidScientificProblem("an UNKNOWN history value must not carry a value")


@dataclass(frozen=True)
class QuantityHistory:
    """Usage or exposure of one quantity over time.

    Entries are non-overlapping; gaps are allowed and mean *no declared value*.
    A query in a gap is UNKNOWN; an integral over a gap is UNKNOWN.
    """

    history_id: str
    kind: HistoryKind
    quantity_id: str
    unit: str
    entries: tuple[HistoryEntry, ...]
    representation: HistoryRepresentation = HistoryRepresentation.PIECEWISE_CONSTANT

    def __post_init__(self) -> None:
        object.__setattr__(self, "history_id", _identifier(self.history_id, "history_id"))
        try:
            object.__setattr__(self, "kind", HistoryKind(self.kind))
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported history kind {self.kind!r}") from exc
        try:
            object.__setattr__(self, "representation", HistoryRepresentation(self.representation))
        except ValueError as exc:
            raise InvalidScientificProblem(
                f"unsupported history representation {self.representation!r}; only "
                f"piecewise_constant is executable"
            ) from exc
        object.__setattr__(self, "quantity_id", _identifier(self.quantity_id, "history quantity_id"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        entries = tuple(self.entries)
        if not entries or any(not isinstance(item, HistoryEntry) for item in entries):
            raise InvalidScientificProblem("history requires at least one HistoryEntry")
        basis = entries[0].window.basis_id
        for item in entries:
            if item.window.basis_id != basis:
                raise InvalidScientificProblem("history entries must share one time basis")
            if item.value.quantity_id != self.quantity_id:
                raise InvalidScientificProblem(
                    f"history {self.history_id!r} entry names {item.value.quantity_id!r}, "
                    f"not {self.quantity_id!r}"
                )
            item.value.value.require_compatible(self.unit, context=f"history {self.history_id!r}")
        ordered = tuple(sorted(entries, key=lambda item: item.window.start.seconds))
        for previous, current in zip(ordered, ordered[1:]):
            if current.window.start.seconds < previous.window.end.seconds:
                raise InvalidScientificProblem(
                    f"history {self.history_id!r} has overlapping entries at "
                    f"{current.window.start.seconds} second; two declared values for one instant"
                )
        object.__setattr__(self, "entries", ordered)

    @property
    def basis_id(self) -> str:
        return self.entries[0].window.basis_id

    @property
    def span(self) -> TimeWindow:
        return TimeWindow(self.entries[0].window.start, self.entries[-1].window.end)

    def value_at(self, point: TimePoint) -> HistoryValue:
        for item in self.entries:
            if item.window.contains(point):
                return HistoryValue(ValueStatus.KNOWN, item.value)
        return HistoryValue(
            ValueStatus.UNKNOWN, None,
            f"history {self.history_id!r} declares no value at {point.seconds} second",
        )

    def gaps_within(self, window: TimeWindow) -> tuple[tuple[float, float], ...]:
        cursor = window.start.seconds
        gaps: list[tuple[float, float]] = []
        for item in self.entries:
            if item.window.end.seconds <= cursor:
                continue
            if item.window.start.seconds >= window.end.seconds:
                break
            if item.window.start.seconds > cursor:
                gaps.append((cursor, item.window.start.seconds))
            cursor = max(cursor, item.window.end.seconds)
        if cursor < window.end.seconds:
            gaps.append((cursor, window.end.seconds))
        return tuple(gaps)

    def integrate(self, window: TimeWindow) -> HistoryValue:
        """Time integral (dose / accumulated usage) over ``window``.

        UNKNOWN if any part of the window has no declared value, or the unit
        is an affine coordinate whose integral has no meaning (degC*s).

        Uncertainty is propagated without inventing a correlation model: if
        every contributing entry has STANDARD uncertainty, the result carries
        ``sum(sigma_i * dt_i)``, which bounds the standard deviation of the sum
        under *any* correlation (triangle inequality).  Any UNKNOWN or INTERVAL
        contribution leaves the integral's uncertainty UNKNOWN.
        """
        window.start._require_same_basis(TimePoint(self.basis_id, Quantity(0, "second")))
        gaps = self.gaps_within(window)
        if gaps:
            return HistoryValue(
                ValueStatus.UNKNOWN, None,
                f"history {self.history_id!r} has no declared value over {list(gaps)} second",
            )
        if not is_ratio_scale(self.unit):
            return HistoryValue(
                ValueStatus.UNKNOWN, None,
                f"unit {self.unit!r} is an affine coordinate; its time integral is undefined",
            )
        total = 0.0
        sigma = 0.0
        standard = True
        for item in self.entries:
            dt = item.window.intersection_seconds(window)
            if dt <= 0.0:
                continue
            total += item.value.value.magnitude_in(self.unit) * dt
            unc = item.value.uncertainty
            if unc.kind is UncertaintyKind.STANDARD:
                sigma += unc.standard_uncertainty.magnitude_as_spread_in(self.unit) * dt
            else:
                standard = False
        unit = normalize_unit(f"({self.unit}) * second")
        if standard:
            uncertainty = Uncertainty(
                kind=UncertaintyKind.STANDARD,
                standard_uncertainty=Quantity(sigma, unit),
                method="sum of sigma_i*dt_i: upper bound on the standard deviation "
                       "of the integral for any correlation between entries",
                source_kind=UncertaintySource.COMBINED,
            )
        else:
            uncertainty = Uncertainty.unknown(
                f"integral of history {self.history_id!r} includes entries without "
                f"standard uncertainty; no correlation model is declared"
            )
        return HistoryValue(
            ValueStatus.KNOWN,
            NamedQuantity(f"{self.quantity_id}.integral", Quantity(total, unit), uncertainty),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HISTORY_SCHEMA, "history_id": self.history_id, "kind": self.kind.value, "quantity_id": self.quantity_id, "unit": self.unit, "representation": self.representation.value, "entries": [item.to_dict() for item in self.entries]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityHistory":
        require_schema(payload, HISTORY_SCHEMA)
        _strict_keys(payload, {"schema", "history_id", "kind", "quantity_id", "unit", "representation", "entries"}, "quantity history")
        return cls(payload["history_id"], payload["kind"], payload["quantity_id"], payload["unit"], tuple(HistoryEntry.from_dict(item) for item in payload["entries"]), payload["representation"])


# --------------------------------------------------------------------------
# Cycle histories
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleRecord:
    """One declared, completed cycle with an integer index and its window."""

    cycle_id: str
    index: int
    window: TimeWindow
    attributes: tuple[NamedQuantity, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle_id", _identifier(self.cycle_id, "cycle_id"))
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise InvalidScientificProblem("cycle index must be a non-negative integer")
        if not isinstance(self.window, TimeWindow) or self.window.closure is not WindowClosure.HALF_OPEN:
            raise InvalidScientificProblem("a cycle owns a half-open window")
        attributes = tuple(self.attributes)
        if any(not isinstance(item, NamedQuantity) for item in attributes):
            raise InvalidScientificProblem("cycle attributes must be NamedQuantity records")
        if len({item.quantity_id for item in attributes}) != len(attributes):
            raise InvalidScientificProblem("cycle attributes contain duplicate quantity ids")
        object.__setattr__(self, "attributes", tuple(sorted(attributes)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CYCLE_RECORD_SCHEMA, "cycle_id": self.cycle_id, "index": self.index, "window": self.window.to_dict(), "attributes": [item.to_dict() for item in self.attributes]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CycleRecord":
        require_schema(payload, CYCLE_RECORD_SCHEMA)
        _strict_keys(payload, {"schema", "cycle_id", "index", "window", "attributes"}, "cycle record")
        return cls(payload["cycle_id"], payload["index"], TimeWindow.from_dict(payload["window"]), tuple(NamedQuantity.from_dict(item) for item in payload["attributes"]))


@dataclass(frozen=True)
class CycleCount:
    """Complete cycles inside a window.  Partial cycles are listed, never fractionally counted."""

    complete: int
    partial_cycle_ids: tuple[str, ...]


@dataclass(frozen=True)
class CycleHistory:
    history_id: str
    cycle_kind: str
    cycles: tuple[CycleRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "history_id", _identifier(self.history_id, "cycle history_id"))
        object.__setattr__(self, "cycle_kind", _identifier(self.cycle_kind, "cycle_kind"))
        cycles = tuple(self.cycles)
        if not cycles or any(not isinstance(item, CycleRecord) for item in cycles):
            raise InvalidScientificProblem("cycle history requires CycleRecord entries")
        if len({item.cycle_id for item in cycles}) != len(cycles):
            raise InvalidScientificProblem("cycle history contains duplicate cycle ids")
        ordered = tuple(sorted(cycles, key=lambda item: item.index))
        basis = ordered[0].window.basis_id
        for previous, current in zip(ordered, ordered[1:]):
            if current.window.basis_id != basis:
                raise InvalidScientificProblem("cycles must share one time basis")
            if current.index != previous.index + 1:
                raise InvalidScientificProblem(
                    f"cycle history {self.history_id!r} skips from index {previous.index} "
                    f"to {current.index}; a missing cycle is not a zero-damage cycle"
                )
            if current.window.start.seconds < previous.window.end.seconds:
                raise InvalidScientificProblem(
                    f"cycle {current.cycle_id!r} starts before cycle {previous.cycle_id!r} "
                    f"ends; cycle order and time order disagree"
                )
        object.__setattr__(self, "cycles", ordered)

    @property
    def basis_id(self) -> str:
        return self.cycles[0].window.basis_id

    def count_within(self, window: TimeWindow) -> CycleCount:
        complete = 0
        partial: list[str] = []
        for item in self.cycles:
            if window.covers(item.window):
                complete += 1
            elif window.overlaps(item.window):
                partial.append(item.cycle_id)
        return CycleCount(complete, tuple(partial))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CYCLE_HISTORY_SCHEMA, "history_id": self.history_id, "cycle_kind": self.cycle_kind, "cycles": [item.to_dict() for item in self.cycles]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CycleHistory":
        require_schema(payload, CYCLE_HISTORY_SCHEMA)
        _strict_keys(payload, {"schema", "history_id", "cycle_kind", "cycles"}, "cycle history")
        return cls(payload["history_id"], payload["cycle_kind"], tuple(CycleRecord.from_dict(item) for item in payload["cycles"]))


# --------------------------------------------------------------------------
# Checkpoints
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TimelineCheckpoint:
    """A replay anchor: the timeline prefix digest at ``at`` plus participant checkpoints.

    ``prefix_digest`` binds everything the timeline recorded up to and
    including ``at``; a replay that diverges before ``at`` cannot present this
    checkpoint as its own.
    """

    checkpoint_id: str
    at: TimePoint
    prefix_digest: str
    participant_checkpoints: tuple[CheckpointRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint_id", _identifier(self.checkpoint_id, "checkpoint_id"))
        if not isinstance(self.at, TimePoint):
            raise InvalidScientificProblem("timeline checkpoint requires a TimePoint")
        object.__setattr__(self, "prefix_digest", require_digest(self.prefix_digest, "checkpoint prefix_digest"))
        records = tuple(self.participant_checkpoints)
        if any(not isinstance(item, CheckpointRecord) for item in records):
            raise InvalidScientificProblem("participant checkpoints must be CheckpointRecord records")
        if len({item.participant_id for item in records}) != len(records):
            raise InvalidScientificProblem("timeline checkpoint holds two checkpoints for one participant")
        for item in records:
            if item.instant.magnitude_in("second") != self.at.seconds:
                raise InvalidScientificProblem(
                    f"participant {item.participant_id!r} checkpoint is at "
                    f"{item.instant.magnitude_in('second')} second, not at the timeline checkpoint"
                )
        object.__setattr__(self, "participant_checkpoints", tuple(sorted(records, key=lambda item: item.participant_id)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIMELINE_CHECKPOINT_SCHEMA, "checkpoint_id": self.checkpoint_id, "at": self.at.to_dict(), "prefix_digest": self.prefix_digest, "participant_checkpoints": [item.to_dict() for item in self.participant_checkpoints]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimelineCheckpoint":
        require_schema(payload, TIMELINE_CHECKPOINT_SCHEMA)
        _strict_keys(payload, {"schema", "checkpoint_id", "at", "prefix_digest", "participant_checkpoints"}, "timeline checkpoint")
        return cls(payload["checkpoint_id"], TimePoint.from_dict(payload["at"]), payload["prefix_digest"], tuple(CheckpointRecord.from_dict(item) for item in payload["participant_checkpoints"]))


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StateIdentity:
    """A participant's state identity at an instant, or UNKNOWN."""

    status: ValueStatus
    state_digest: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Timeline:
    """One deterministic, replayable record of what happened on one time basis.

    The timeline owns no scientific authority: scheduled events come from a
    scenario, transitions come from execution receipts, histories from declared
    sources.  It enforces that those records agree about time.
    """

    timeline_id: str
    basis: TimeBasis
    horizon: TimeWindow
    scenario_digest: str = ""
    events: tuple[TimelineEvent, ...] = ()
    histories: tuple[QuantityHistory, ...] = ()
    cycle_histories: tuple[CycleHistory, ...] = ()
    initial_state_digests: tuple[tuple[str, str], ...] = ()
    state_transitions: tuple[StateTransitionReceipt, ...] = ()
    checkpoints: tuple[TimelineCheckpoint, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeline_id", _identifier(self.timeline_id, "timeline_id"))
        if not isinstance(self.basis, TimeBasis):
            raise InvalidScientificProblem("timeline requires a declared TimeBasis; there is no default clock")
        if not isinstance(self.horizon, TimeWindow) or self.horizon.closure is not WindowClosure.CLOSED:
            raise InvalidScientificProblem("timeline horizon must be a CLOSED TimeWindow")
        basis_id = self.basis.basis_id
        if self.horizon.basis_id != basis_id:
            raise InvalidScientificProblem("timeline horizon is not on the timeline basis")
        digest = str(self.scenario_digest or "").strip().lower()
        object.__setattr__(self, "scenario_digest", require_digest(digest, "timeline scenario_digest") if digest else "")

        events = order_events(self.events)
        for item in events:
            self._require_inside(item.at, f"event {item.event_id!r}")
        object.__setattr__(self, "events", events)

        histories = tuple(self.histories)
        if any(not isinstance(item, QuantityHistory) for item in histories):
            raise InvalidScientificProblem("timeline histories must be QuantityHistory records")
        if len({item.history_id for item in histories}) != len(histories):
            raise InvalidScientificProblem("timeline contains duplicate history ids")
        for item in histories:
            if item.basis_id != basis_id or not self.horizon.covers(item.span):
                raise InvalidScientificProblem(
                    f"history {item.history_id!r} is not inside the timeline horizon on its basis"
                )
        object.__setattr__(self, "histories", tuple(sorted(histories, key=lambda item: item.history_id)))

        cycles = tuple(self.cycle_histories)
        if any(not isinstance(item, CycleHistory) for item in cycles):
            raise InvalidScientificProblem("timeline cycle histories must be CycleHistory records")
        if len({item.history_id for item in cycles}) != len(cycles):
            raise InvalidScientificProblem("timeline contains duplicate cycle history ids")
        for item in cycles:
            span = TimeWindow(item.cycles[0].window.start, item.cycles[-1].window.end) if item.basis_id == basis_id else None
            if span is None or not self.horizon.covers(span):
                raise InvalidScientificProblem(
                    f"cycle history {item.history_id!r} is not inside the timeline horizon on its basis"
                )
        object.__setattr__(self, "cycle_histories", tuple(sorted(cycles, key=lambda item: item.history_id)))

        initial = tuple((str(pid), require_digest(d, "initial state digest")) for pid, d in self.initial_state_digests)
        if len({pid for pid, _ in initial}) != len(initial):
            raise InvalidScientificProblem("timeline declares two initial states for one participant")
        object.__setattr__(self, "initial_state_digests", tuple(sorted(initial)))
        object.__setattr__(self, "state_transitions", self._chain_transitions(tuple(self.state_transitions), dict(initial)))

        checkpoints = tuple(self.checkpoints)
        if any(not isinstance(item, TimelineCheckpoint) for item in checkpoints):
            raise InvalidScientificProblem("timeline checkpoints must be TimelineCheckpoint records")
        if len({item.checkpoint_id for item in checkpoints}) != len(checkpoints):
            raise InvalidScientificProblem("timeline contains duplicate checkpoint ids")
        object.__setattr__(self, "checkpoints", tuple(sorted(checkpoints, key=lambda item: (item.at.seconds, item.checkpoint_id))))
        for item in self.checkpoints:
            self.verify_checkpoint(item)

    # ---- construction helpers --------------------------------------------

    def _require_inside(self, point: TimePoint, label: str) -> None:
        if point.basis_id != self.basis.basis_id:
            raise InvalidScientificProblem(
                f"{label} is on basis {point.basis_id!r}, not the timeline basis "
                f"{self.basis.basis_id!r}"
            )
        if not self.horizon.contains(point):
            raise InvalidScientificProblem(f"{label} lies outside the timeline horizon")

    def _point(self, seconds: float) -> TimePoint:
        return TimePoint(self.basis.basis_id, Quantity(seconds, "second"))

    def _chain_transitions(
        self, transitions: tuple[StateTransitionReceipt, ...], initial: Mapping[str, str]
    ) -> tuple[StateTransitionReceipt, ...]:
        if any(not isinstance(item, StateTransitionReceipt) for item in transitions):
            raise InvalidScientificProblem("timeline state transitions must be StateTransitionReceipt records")
        by_participant: dict[str, list[StateTransitionReceipt]] = {}
        for item in transitions:
            if self.scenario_digest and item.scenario_digest and item.scenario_digest != self.scenario_digest:
                raise InvalidScientificProblem(
                    f"state transition for {item.participant_id!r} was produced for a "
                    f"different scenario; evidence must stay bound to its context"
                )
            for bound, label in ((item.start, "start"), (item.end, "end")):
                self._require_inside(self._point(bound.magnitude_in("second")), f"state transition {label}")
            by_participant.setdefault(item.participant_id, []).append(item)
        for participant, items in by_participant.items():
            items.sort(key=lambda item: item.window_index)
            if len({item.window_index for item in items}) != len(items):
                raise InvalidScientificProblem(f"participant {participant!r} has two transitions for one window")
            if participant in initial and items[0].start_state_digest != initial[participant]:
                raise InvalidScientificProblem(
                    f"participant {participant!r} first transition does not start from its declared initial state"
                )
            for previous, current in zip(items, items[1:]):
                if current.start != previous.end:
                    raise InvalidScientificProblem(
                        f"participant {participant!r} state history has a time gap or overlap "
                        f"between windows {previous.window_index} and {current.window_index}"
                    )
                if current.start_state_digest != previous.end_state_digest:
                    raise InvalidScientificProblem(
                        f"participant {participant!r} state discontinuity: window "
                        f"{current.window_index} does not start from the state window "
                        f"{previous.window_index} ended in"
                    )
        return tuple(sorted(transitions, key=lambda item: item.key))

    @classmethod
    def from_scenario(
        cls,
        scenario: ScenarioSpecification,
        *,
        timeline_id: str,
        basis: TimeBasis,
        histories: tuple[QuantityHistory, ...] = (),
        cycle_histories: tuple[CycleHistory, ...] = (),
        extra_events: tuple[TimelineEvent, ...] = (),
    ) -> "Timeline":
        """Bind a timeline to a scenario, which stays the authority for horizon and scheduled events."""
        if not isinstance(scenario, ScenarioSpecification):
            raise InvalidScientificProblem("from_scenario requires a ScenarioSpecification")
        if not isinstance(basis, TimeBasis):
            raise InvalidScientificProblem("from_scenario requires an explicit TimeBasis")
        if basis.kind is not TimeBasisKind.ELAPSED:
            raise InvalidScientificProblem(
                "scenario instants are elapsed offsets; bind them to an ELAPSED basis"
            )
        point = lambda q: TimePoint(basis.basis_id, q)  # noqa: E731
        horizon = TimeWindow(point(scenario.start), point(scenario.end), WindowClosure.CLOSED)
        scheduled = tuple(
            TimelineEvent(f"scheduled:{item.event_id}", TimelineEventKind.SCHEDULED_SYNCHRONIZATION, point(item.instant), item.event_id)
            for item in scenario.events
        )
        return cls(
            timeline_id, basis, horizon, scenario.digest,
            events=scheduled + tuple(extra_events),
            histories=histories, cycle_histories=cycle_histories,
        )

    def bind_run(self, run: Any) -> "Timeline":
        """Add a multiphysics run's receipts: reached events, state transitions, termination.

        The run must carry this timeline's scenario digest.  Its receipts are
        copied verbatim; nothing is synthesized for a participant that did not
        report a transition.
        """
        from ..scientific.multiphysics.report import MultiphysicsRunRecord

        if not isinstance(run, MultiphysicsRunRecord):
            raise InvalidScientificProblem("bind_run requires a MultiphysicsRunRecord")
        if not self.scenario_digest:
            raise InvalidScientificProblem("only a scenario-bound timeline can bind a run")
        if run.scenario_digest != self.scenario_digest:
            raise InvalidScientificProblem(
                "run was executed for a different scenario; evidence must stay bound "
                "to the exact context it was produced for"
            )
        if self.state_transitions:
            raise InvalidScientificProblem("timeline already holds state transitions from a run")
        scheduled = {item.subject_id for item in self.events if item.kind is TimelineEventKind.SCHEDULED_SYNCHRONIZATION}
        reached_ids = {item.event_id for item in run.reached_scheduled_events}
        unknown = reached_ids - scheduled
        if unknown:
            raise InvalidScientificProblem(f"run reached events the scenario never scheduled: {sorted(unknown)}")
        events = list(self.events)
        for item in run.reached_scheduled_events:
            events.append(TimelineEvent(
                f"reached:{item.event_id}", TimelineEventKind.REACHED_SYNCHRONIZATION,
                self._point(item.instant.magnitude_in("second")), item.event_id,
            ))
        if run.termination is not None:
            events.append(TimelineEvent(
                f"termination:{run.termination.condition_id}", TimelineEventKind.TERMINATION,
                self._point(run.termination.instant.magnitude_in("second")), run.termination.condition_id,
            ))
        return Timeline(
            self.timeline_id, self.basis, self.horizon, self.scenario_digest,
            events=tuple(events), histories=self.histories, cycle_histories=self.cycle_histories,
            initial_state_digests=self.initial_state_digests,
            state_transitions=tuple(run.state_transitions), checkpoints=self.checkpoints,
        )

    # ---- queries -----------------------------------------------------------

    def history(self, history_id: str) -> QuantityHistory:
        for item in self.histories:
            if item.history_id == history_id:
                return item
        raise InvalidScientificProblem(f"timeline has no history {history_id!r}")

    def discontinuities(self, quantity_id: str) -> tuple[TimelineEvent, ...]:
        return tuple(item for item in self.events if item.kind is TimelineEventKind.DISCONTINUITY and item.subject_id == quantity_id)

    def state_at(self, participant_id: str, point: TimePoint) -> StateIdentity:
        """A participant's state identity at a window boundary; UNKNOWN between boundaries."""
        self._require_inside(point, "state query")
        items = [item for item in self.state_transitions if item.participant_id == participant_id]
        initial = dict(self.initial_state_digests).get(participant_id)
        if items and point.seconds == items[0].start.magnitude_in("second"):
            return StateIdentity(ValueStatus.KNOWN, items[0].start_state_digest)
        for item in items:
            if point.seconds == item.end.magnitude_in("second"):
                return StateIdentity(ValueStatus.KNOWN, item.end_state_digest)
        if not items and initial is not None and point.seconds == self.horizon.start.seconds:
            return StateIdentity(ValueStatus.KNOWN, initial)
        return StateIdentity(
            ValueStatus.UNKNOWN, "",
            f"no state identity for {participant_id!r} was recorded at {point.seconds} second; "
            f"state between coupling boundaries is not observed",
        )

    def input_value_at(self, series: TimeSeriesInput, point: TimePoint, method: Any) -> Quantity:
        """Evaluate a scenario input with an explicitly requested interpolation.

        Refused: an interpolation method this Core does not implement, a
        query off the series, and LINEAR interpolation across a declared
        discontinuity of the input.
        """
        try:
            kind = InterpolationKind(method)
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported interpolation {method!r}") from exc
        if kind is not series.interpolation:
            raise InvalidScientificProblem(
                f"input {series.input_id!r} declares {series.interpolation.value} "
                f"interpolation; {kind.value} was requested"
            )
        self._require_inside(point, "input query")
        seconds = point.seconds
        instants = [item.instant.magnitude_in("second") for item in series.samples]
        if kind is InterpolationKind.LINEAR and seconds not in instants:
            if instants[0] < seconds < instants[-1]:
                upper = next(i for i, value in enumerate(instants) if value > seconds)
                lower_s, upper_s = instants[upper - 1], instants[upper]
                for event in self.discontinuities(series.input_id):
                    if lower_s < event.at.seconds < upper_s:
                        raise InvalidScientificProblem(
                            f"LINEAR interpolation of {series.input_id!r} would cross the "
                            f"declared discontinuity {event.event_id!r}"
                        )
        return series.value_at(point.offset)

    # ---- serialization, digests, replay -----------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TIMELINE_SCHEMA,
            "timeline_id": self.timeline_id,
            "basis": self.basis.to_dict(),
            "horizon": self.horizon.to_dict(),
            "scenario_digest": self.scenario_digest,
            "events": [item.to_dict() for item in self.events],
            "histories": [item.to_dict() for item in self.histories],
            "cycle_histories": [item.to_dict() for item in self.cycle_histories],
            "initial_state_digests": [[pid, digest] for pid, digest in self.initial_state_digests],
            "state_transitions": [item.to_dict() for item in self.state_transitions],
            "checkpoints": [item.to_dict() for item in self.checkpoints],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Timeline":
        require_schema(payload, TIMELINE_SCHEMA)
        _strict_keys(payload, {"schema", "timeline_id", "basis", "horizon", "scenario_digest", "events", "histories", "cycle_histories", "initial_state_digests", "state_transitions", "checkpoints"}, "timeline")
        return cls(
            payload["timeline_id"], TimeBasis.from_dict(payload["basis"]), TimeWindow.from_dict(payload["horizon"]),
            payload["scenario_digest"],
            events=tuple(TimelineEvent.from_dict(item) for item in payload["events"]),
            histories=tuple(QuantityHistory.from_dict(item) for item in payload["histories"]),
            cycle_histories=tuple(CycleHistory.from_dict(item) for item in payload["cycle_histories"]),
            initial_state_digests=tuple((pid, digest) for pid, digest in payload["initial_state_digests"]),
            state_transitions=tuple(StateTransitionReceipt.from_dict(item) for item in payload["state_transitions"]),
            checkpoints=tuple(TimelineCheckpoint.from_dict(item) for item in payload["checkpoints"]),
        )

    def prefix(self, at: TimePoint) -> dict[str, Any]:
        """Canonical content recorded up to and including ``at``.

        Refused when ``at`` falls strictly inside a history entry, a cycle or a
        state-transition window: a prefix there would have to split a record,
        which is a new record nobody declared.
        """
        self._require_inside(at, "prefix instant")
        s = at.seconds
        for item in self.histories:
            for entry in item.entries:
                if entry.window.start.seconds < s < entry.window.end.seconds:
                    raise InvalidScientificProblem(f"{s} second splits an entry of history {item.history_id!r}")
        for item in self.cycle_histories:
            for cycle in item.cycles:
                if cycle.window.start.seconds < s < cycle.window.end.seconds:
                    raise InvalidScientificProblem(f"{s} second splits cycle {cycle.cycle_id!r}")
        for item in self.state_transitions:
            if item.start.magnitude_in("second") < s < item.end.magnitude_in("second"):
                raise InvalidScientificProblem(f"{s} second splits a state-transition window of {item.participant_id!r}")
        return {
            "timeline_id": self.timeline_id,
            "basis": self.basis.to_dict(),
            "horizon_start": self.horizon.start.to_dict(),
            "scenario_digest": self.scenario_digest,
            "through": at.to_dict(),
            "events": [item.to_dict() for item in self.events if item.at.seconds <= s],
            "histories": [
                {"history_id": item.history_id, "entries": [e.to_dict() for e in item.entries if e.window.end.seconds <= s]}
                for item in self.histories
            ],
            "cycle_histories": [
                {"history_id": item.history_id, "cycles": [c.to_dict() for c in item.cycles if c.window.end.seconds <= s]}
                for item in self.cycle_histories
            ],
            "initial_state_digests": [[pid, digest] for pid, digest in self.initial_state_digests],
            "state_transitions": [item.to_dict() for item in self.state_transitions if item.end.magnitude_in("second") <= s],
        }

    def prefix_digest(self, at: TimePoint) -> str:
        return canonical_digest(self.prefix(at))

    def checkpoint(self, checkpoint_id: str, at: TimePoint, participant_checkpoints: tuple[CheckpointRecord, ...] = ()) -> TimelineCheckpoint:
        """Create a checkpoint whose participant records agree with recorded state."""
        for event in self.events:
            if event.at.seconds == at.seconds and event.order_sensitive:
                raise InvalidScientificProblem(
                    f"checkpoint at {at.seconds} second coincides with order-sensitive event "
                    f"{event.event_id!r}; before/after is ambiguous"
                )
        checkpoint = TimelineCheckpoint(checkpoint_id, at, self.prefix_digest(at), tuple(participant_checkpoints))
        self.verify_checkpoint(checkpoint)
        return checkpoint

    def verify_checkpoint(self, checkpoint: TimelineCheckpoint) -> None:
        if checkpoint.prefix_digest != self.prefix_digest(checkpoint.at):
            raise InvalidScientificProblem(
                f"checkpoint {checkpoint.checkpoint_id!r} does not match this timeline's prefix"
            )
        for record in checkpoint.participant_checkpoints:
            identity = self.state_at(record.participant_id, checkpoint.at)
            if identity.status is ValueStatus.KNOWN and identity.state_digest != record.state_digest:
                raise InvalidScientificProblem(
                    f"participant {record.participant_id!r} checkpoint state differs from "
                    f"the recorded state identity at {checkpoint.at.seconds} second"
                )

    def with_checkpoint(self, checkpoint: TimelineCheckpoint) -> "Timeline":
        return Timeline(
            self.timeline_id, self.basis, self.horizon, self.scenario_digest,
            events=self.events, histories=self.histories, cycle_histories=self.cycle_histories,
            initial_state_digests=self.initial_state_digests,
            state_transitions=self.state_transitions, checkpoints=self.checkpoints + (checkpoint,),
        )


@dataclass(frozen=True)
class ReplayComparison:
    """Whether a replay reproduced a recorded timeline prefix.

    Classification is fixed: replay consistency is a reproducibility fact,
    never validation.
    """

    consistent: bool
    through: TimePoint
    original_digest: str
    replayed_digest: str
    compared_records: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REPLAY_COMPARISON_SCHEMA, "classification": "replay_consistency_not_validation", "consistent": self.consistent, "through": self.through.to_dict(), "original_digest": self.original_digest, "replayed_digest": self.replayed_digest, "compared_records": self.compared_records, "reason": self.reason}


def _prefix_record_count(prefix: Mapping[str, Any]) -> int:
    return (
        len(prefix["events"]) + len(prefix["state_transitions"])
        + sum(len(item["entries"]) for item in prefix["histories"])
        + sum(len(item["cycles"]) for item in prefix["cycle_histories"])
    )


def compare_replay(original: Timeline, replayed: Timeline, *, through: TimePoint | None = None) -> ReplayComparison:
    """Compare a replayed timeline to the original up to ``through`` (default: horizon end).

    A prefix with no recorded content cannot pass: an empty comparison proves
    nothing was compared, not that anything was reproduced.
    """
    if not isinstance(original, Timeline) or not isinstance(replayed, Timeline):
        raise InvalidScientificProblem("compare_replay requires two Timeline records")
    point = original.horizon.end if through is None else through
    first = original.prefix(point)
    count = _prefix_record_count(first)
    if count == 0:
        raise InvalidScientificProblem(
            "replay comparison over an empty prefix is refused; nothing would be compared"
        )
    try:
        second = replayed.prefix(point)
    except InvalidScientificProblem as exc:
        return ReplayComparison(False, point, canonical_digest(first), "0" * 64, count, f"replay cannot produce the prefix: {exc}")
    a, b = canonical_digest(first), canonical_digest(second)
    reason = ""
    if a != b:
        for key in sorted(first):
            if first[key] != second.get(key):
                reason = f"first divergence in {key!r}"
                break
    return ReplayComparison(a == b, point, a, b, count, reason)
