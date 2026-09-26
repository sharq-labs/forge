"""Macro windows, representative fast windows and the explicit macro-step policy.

A representative window is an APPROXIMATION CONTRACT, not a fact: it resolves
an exact BIG 2 ``TimeWindow`` and is declared to stand for a longer
``represented`` window with an exact rational weight.  Nothing assumes "one
day x 365 = one year": the weight is derived from the two exact windows,
recorded, and part of run identity; the assumptions and the applicability
statement travel with it.

Macro-step size is never adapted silently: every change is a recorded
decision naming the rule, trigger, threshold and policy digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import Any, Mapping

from ..scenarios.timeline import TimePoint, TimeWindow, canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from ._common import fraction_text, identifier, time_seconds, window_seconds

POLICY_SCHEMA = "engcore.multiscale.macro_step_policy/1"


class SelectionMethod(str, Enum):
    #: The resolved window IS the macro window (weight 1, no repetition).
    FULLY_RESOLVED = "fully_resolved"
    #: The first ``period`` of the macro window is resolved and declared to
    #: represent the whole macro window.
    LEADING_PERIOD = "leading_period"


class ApproximationStatus(str, Enum):
    #: Resolved and represented windows are the same interval.
    EXACT_COVERAGE = "exact_coverage"
    #: A repetition is declared; its error is UNKNOWN unless quantified.
    DECLARED_APPROXIMATION = "declared_approximation"


@dataclass(frozen=True)
class RepresentativeWindow:
    window_id: str
    resolved: TimeWindow
    represented: TimeWindow
    weight: Fraction
    selection: SelectionMethod
    assumptions: tuple[str, ...]
    applicability: str
    aggregation_semantics: str
    #: Measured max |input(repeated period) - input(resolved period)| per
    #: declared input record, as (record_id, "value unit").  Empty at weight 1.
    input_deviation: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", identifier(self.window_id, "representative window_id"))
        object.__setattr__(self, "selection", SelectionMethod(self.selection))
        if not isinstance(self.weight, Fraction) or self.weight < 1:
            raise InvalidScientificProblem("a representative weight is an exact rational >= 1")
        if not self.represented.covers(self.resolved):
            raise InvalidScientificProblem("a representative window must lie inside the window it represents")
        if self.weight * window_seconds(self.resolved) != window_seconds(self.represented):
            raise InvalidScientificProblem(
                "representative weight x resolved duration must equal the represented duration exactly")
        if self.weight != 1 and not self.assumptions:
            raise InvalidScientificProblem("a repeated representative window must state its approximation assumptions")
        for label in ("applicability", "aggregation_semantics"):
            if not str(getattr(self, label) or "").strip():
                raise InvalidScientificProblem(f"a representative window must declare its {label}")
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

    @property
    def status(self) -> ApproximationStatus:
        return ApproximationStatus.EXACT_COVERAGE if self.weight == 1 else ApproximationStatus.DECLARED_APPROXIMATION

    def to_dict(self) -> dict[str, Any]:
        return {"window_id": self.window_id, "resolved": self.resolved.to_dict(), "represented": self.represented.to_dict(),
                "weight": fraction_text(self.weight), "selection": self.selection.value, "assumptions": list(self.assumptions),
                "applicability": self.applicability, "aggregation_semantics": self.aggregation_semantics,
                "approximation_status": self.status.value, "input_deviation": [list(x) for x in self.input_deviation]}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "RepresentativeWindow":
        return cls(p["window_id"], TimeWindow.from_dict(p["resolved"]), TimeWindow.from_dict(p["represented"]), Fraction(p["weight"]),
                   p["selection"], tuple(p["assumptions"]), p["applicability"], p["aggregation_semantics"],
                   tuple(tuple(x) for x in p["input_deviation"]))


@dataclass(frozen=True)
class RepresentativePolicy:
    policy_id: str
    selection: SelectionMethod
    period: Quantity | None
    assumptions: tuple[str, ...]
    applicability: str
    aggregation_semantics: str
    #: Declared tolerance per input record (environment channel id or usage
    #: history id): how far a repeated period's inputs may deviate from the
    #: resolved period's before the repetition is refused.  Every input must
    #: have one under LEADING_PERIOD; there is no default.
    periodicity_tolerances: tuple[tuple[str, Quantity], ...] = ()
    #: Declared tolerance per FAST state variable ("participant.variable"): a
    #: repeated period must end within it of the state it started from.
    fast_state_tolerances: tuple[tuple[str, Quantity], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", identifier(self.policy_id, "representative policy_id"))
        tolerances = tuple(self.periodicity_tolerances)
        if len({k for k, _ in tolerances}) != len(tolerances) or any(not isinstance(q, Quantity) or q.magnitude < 0 for _, q in tolerances):
            raise InvalidScientificProblem("periodicity tolerances are unique, non-negative Quantities per input record")
        object.__setattr__(self, "periodicity_tolerances", tuple(sorted(tolerances, key=lambda x: x[0])))
        fast = tuple(self.fast_state_tolerances)
        if len({k for k, _ in fast}) != len(fast) or any(not isinstance(q, Quantity) or q.magnitude < 0 for _, q in fast):
            raise InvalidScientificProblem("fast-state tolerances are unique, non-negative Quantities")
        object.__setattr__(self, "fast_state_tolerances", tuple(sorted(fast, key=lambda x: x[0])))
        object.__setattr__(self, "selection", SelectionMethod(self.selection))
        if self.selection is SelectionMethod.LEADING_PERIOD:
            if self.period is None or time_seconds(self.period) <= 0:
                raise InvalidScientificProblem("a leading-period representative policy needs a positive period")
            if not self.assumptions:
                raise InvalidScientificProblem("a leading-period representative policy must state its assumptions")
        elif self.period is not None:
            raise InvalidScientificProblem("a fully resolved policy has no representative period")
        object.__setattr__(self, "assumptions", tuple(self.assumptions))

    def tolerance(self, record_id: str) -> Quantity | None:
        return next((q for k, q in self.periodicity_tolerances if k == record_id), None)

    def build(self, macro: TimeWindow, window_id: str) -> tuple[RepresentativeWindow, ...]:
        """Tile ``macro``: the leading period repeated a WHOLE number of times,
        then an exactly resolved remainder (weight 1).  A fractional repetition
        would put the resolved period's phases on the wrong hours."""
        total = window_seconds(macro)
        full = lambda w, wid: RepresentativeWindow(wid, w, w, Fraction(1), SelectionMethod.FULLY_RESOLVED, self.assumptions,  # noqa: E731
                                                   self.applicability, self.aggregation_semantics)
        if self.selection is SelectionMethod.FULLY_RESOLVED:
            return (full(macro, window_id),)
        span = time_seconds(self.period)
        repeats = int(total // span)
        if repeats < 2:
            return (full(macro, window_id),)
        start = macro.start.seconds
        resolved = TimeWindow(macro.start, TimePoint(macro.basis_id, start + span))
        represented = TimeWindow(macro.start, TimePoint(macro.basis_id, start + repeats * span))
        tiles = [RepresentativeWindow(window_id, resolved, represented, Fraction(repeats), SelectionMethod.LEADING_PERIOD,
                                      self.assumptions, self.applicability, self.aggregation_semantics)]
        if start + repeats * span < macro.end.seconds:
            tiles.append(full(TimeWindow(represented.end, macro.end), f"{window_id}-remainder"))
        return tuple(tiles)

    def to_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "selection": self.selection.value,
                "period": None if self.period is None else self.period.to_dict(), "assumptions": list(self.assumptions),
                "applicability": self.applicability, "aggregation_semantics": self.aggregation_semantics,
                "periodicity_tolerances": [[k, q.to_dict()] for k, q in self.periodicity_tolerances],
                "fast_state_tolerances": [[k, q.to_dict()] for k, q in self.fast_state_tolerances]}


class EventHandling(str, Enum):
    #: End the macro window at the event (the next window starts there).
    SPLIT = "split"
    #: Refuse the approximation when an event falls inside a macro window.
    REFUSE = "refuse"


class AdaptationTrigger(str, Enum):
    DEFAULT = "default"
    AFTER_ELAPSED = "after_elapsed"
    NEAR_THRESHOLD = "near_threshold"


@dataclass(frozen=True)
class AdaptationRule:
    rule_id: str
    trigger: AdaptationTrigger
    window: Quantity
    after: Quantity | None = None
    participant_id: str = ""
    variable_id: str = ""
    threshold: Quantity | None = None
    band: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", identifier(self.rule_id, "adaptation rule_id"))
        trigger = AdaptationTrigger(self.trigger)
        object.__setattr__(self, "trigger", trigger)
        if time_seconds(self.window, "rule window") <= 0:
            raise InvalidScientificProblem("an adaptation rule's window must be positive")
        if trigger is AdaptationTrigger.AFTER_ELAPSED and self.after is None:
            raise InvalidScientificProblem("an after-elapsed rule needs its elapsed time")
        if trigger is AdaptationTrigger.NEAR_THRESHOLD:
            if not (self.participant_id and self.variable_id) or self.threshold is None or self.band is None:
                raise InvalidScientificProblem("a near-threshold rule names participant, variable, threshold and band")
            self.band.require_compatible(self.threshold.units, context="threshold band")
            if not self.band.magnitude > 0:
                raise InvalidScientificProblem("a threshold band must be positive")

    def to_dict(self) -> dict[str, Any]:
        q = lambda v: None if v is None else v.to_dict()  # noqa: E731
        return {"rule_id": self.rule_id, "trigger": self.trigger.value, "window": self.window.to_dict(), "after": q(self.after),
                "participant_id": self.participant_id, "variable_id": self.variable_id, "threshold": q(self.threshold), "band": q(self.band)}


@dataclass(frozen=True)
class StateChangeLimit:
    """Reject a macro step when ``|new - old| / scale > allowed``.

    ``scale`` is the explicitly declared normalization; there is no default
    denominator.  A numerical/orchestration safeguard, never validation.
    """

    participant_id: str
    variable_id: str
    scale: Quantity
    allowed: float

    def __post_init__(self) -> None:
        if not isinstance(self.scale, Quantity) or not self.scale.magnitude > 0:
            raise InvalidScientificProblem("a state-change limit needs an explicit positive normalization scale")
        if not float(self.allowed) > 0:
            raise InvalidScientificProblem("allowed normalized change must be positive")

    def normalized(self, old: Quantity, new: Quantity) -> float:
        return abs(new.magnitude_in(self.scale.units) - old.magnitude_in(self.scale.units)) / self.scale.magnitude

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "variable_id": self.variable_id, "scale": self.scale.to_dict(), "allowed": float(self.allowed)}


@dataclass(frozen=True)
class ThresholdWatch:
    """A lifecycle threshold: a step that crosses it must be at most ``localization`` long."""

    watch_id: str
    participant_id: str
    variable_id: str
    threshold: Quantity
    localization: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "watch_id", identifier(self.watch_id, "threshold watch_id"))
        if time_seconds(self.localization, "localization") <= 0:
            raise InvalidScientificProblem("threshold localization must be a positive duration")

    def crossed(self, old: Quantity, new: Quantity) -> bool:
        t = self.threshold.magnitude_in(old.units)
        a, b = old.magnitude, new.magnitude_in(old.units)
        return (a - t) * (b - t) < 0 or (a != t and b == t)

    def to_dict(self) -> dict[str, Any]:
        return {"watch_id": self.watch_id, "participant_id": self.participant_id, "variable_id": self.variable_id,
                "threshold": self.threshold.to_dict(), "localization": self.localization.to_dict()}


@dataclass(frozen=True)
class MacroStepPolicy:
    policy_id: str
    version: str
    rules: tuple[AdaptationRule, ...]
    minimum_window: Quantity
    event_handling: EventHandling
    representative: RepresentativePolicy
    state_change_limits: tuple[StateChangeLimit, ...] = ()
    threshold_watches: tuple[ThresholdWatch, ...] = ()
    #: On rejection the attempted window is divided by this integer.
    rejection_divisor: int = 2
    max_rejections_per_step: int = 12

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", identifier(self.policy_id, "policy_id"))
        if not str(self.version or "").strip():
            raise InvalidScientificProblem("a macro-step policy requires a version")
        rules = tuple(self.rules)
        if [r.trigger for r in rules].count(AdaptationTrigger.DEFAULT) != 1:
            raise InvalidScientificProblem("a macro-step policy has exactly one DEFAULT rule")
        if len({r.rule_id for r in rules}) != len(rules):
            raise InvalidScientificProblem("adaptation rule ids must be unique")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "event_handling", EventHandling(self.event_handling))
        if time_seconds(self.minimum_window, "minimum window") <= 0:
            raise InvalidScientificProblem("minimum macro window must be positive")
        if isinstance(self.rejection_divisor, bool) or not isinstance(self.rejection_divisor, int) or self.rejection_divisor < 2:
            raise InvalidScientificProblem("rejection divisor must be an integer >= 2")

    def select(self, elapsed: Fraction, slow_state: Mapping[tuple[str, str], Quantity]) -> tuple[Fraction, AdaptationRule, str]:
        """(window seconds, rule, reason) for a step starting ``elapsed`` seconds into the run."""
        near = []
        for r in self.rules:
            if r.trigger is AdaptationTrigger.NEAR_THRESHOLD:
                value = slow_state.get((r.participant_id, r.variable_id))
                if value is None:
                    raise InvalidScientificProblem(f"near-threshold rule {r.rule_id!r} watches unknown state {r.participant_id}.{r.variable_id}")
                distance = abs(value.magnitude_in(r.threshold.units) - r.threshold.magnitude)
                if distance <= r.band.magnitude_in(r.threshold.units):
                    near.append((time_seconds(r.window), r, f"{r.variable_id} within {r.band.magnitude:g} {r.band.units} of threshold "
                                                              f"{r.threshold.magnitude:g} {r.threshold.units} (distance {distance:.6g})"))
        if near:
            return min(near, key=lambda x: (x[0], x[1].rule_id))
        after = [(time_seconds(r.after), r) for r in self.rules if r.trigger is AdaptationTrigger.AFTER_ELAPSED and time_seconds(r.after) <= elapsed]
        if after:
            _, r = max(after, key=lambda x: (x[0], x[1].rule_id))
            return time_seconds(r.window), r, f"elapsed {float(elapsed):g} s >= {float(time_seconds(r.after)):g} s"
        default = next(r for r in self.rules if r.trigger is AdaptationTrigger.DEFAULT)
        return time_seconds(default.window), default, "default macro window"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": POLICY_SCHEMA, "policy_id": self.policy_id, "version": self.version, "rules": [r.to_dict() for r in self.rules],
                "minimum_window": self.minimum_window.to_dict(), "event_handling": self.event_handling.value,
                "representative": self.representative.to_dict(), "state_change_limits": [x.to_dict() for x in self.state_change_limits],
                "threshold_watches": [x.to_dict() for x in self.threshold_watches], "rejection_divisor": self.rejection_divisor,
                "max_rejections_per_step": self.max_rejections_per_step}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class AdaptationDecision:
    """A recorded change of the macro step size (never silent)."""

    at: TimePoint
    old_seconds: Fraction | None
    new_seconds: Fraction
    trigger: str
    rule_id: str
    threshold: str
    policy_digest: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at.to_dict(), "old_seconds": None if self.old_seconds is None else fraction_text(self.old_seconds),
                "new_seconds": fraction_text(self.new_seconds), "trigger": self.trigger, "rule_id": self.rule_id,
                "threshold": self.threshold, "policy_digest": self.policy_digest, "reason": self.reason}


@dataclass(frozen=True)
class RefinementDecision:
    """An event, rejection or threshold that shortened or refused a macro window."""

    kind: str  # "event_split" | "state_change_rejected" | "threshold_localization" | "representativity_rejected"
    at: TimePoint
    attempted_end: TimePoint
    new_end: TimePoint | None
    subject: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "at": self.at.to_dict(), "attempted_end": self.attempted_end.to_dict(),
                "new_end": None if self.new_end is None else self.new_end.to_dict(), "subject": self.subject, "detail": self.detail}
