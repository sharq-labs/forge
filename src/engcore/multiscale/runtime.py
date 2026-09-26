"""Multi-timescale runtime: macro windows over BIG 2 time, fast physics only where resolved.

Per macro window::

    stop at a declared TERMINATION; refuse an unapplied STATE_CHANGE_REQUEST
    select size (explicit policy; every change recorded)
      -> split at / refuse on BIG 2 events inside the window
      -> refuse if any environment/usage input is UNKNOWN inside the window
      -> representative fast windows (declared approximation contract; the
         repeated inputs are MEASURED against the resolved period and a
         repetition beyond the declared tolerance is rejected and refined)
      -> FastSystem executions (real coupled physics; exact reuse only for a
         declared-pure system and an identical request)
      -> explicit aggregation records (information loss stated)
      -> BIG 4 degradation steps (model declares accepted forms/features)
      -> state-change limit / threshold localization (reject + refine, recorded)
      -> accept: new SLOW state (immutable snapshot), checkpoint
    next macro window: the fast system re-resolves materials from the new state

This is an orchestration layer.  Time, events and histories are BIG 2's;
environment is BIG 3's; degradation and state change are BIG 4's
(:func:`~engcore.scenarios.lifecycle.evaluate_degradation_step`); material
resolution is BIG 5's; the fast physics is a BIG 9 ``MultiphysicsRuntime``
run behind :class:`~engcore.multiscale.fast.FastSystem`.  A fast solver never
changes SLOW state: it receives read-only snapshots, and only an APPLIED
degradation step changes slow state.

Nothing produced here is evidence or validation: representative repetition is
an approximation contract, replay/resume agreement is reproducibility, and
every approximation component without a quantification is UNKNOWN.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field, replace
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Mapping

from ..scenarios.environment import ChannelRepresentation, EnvironmentTimeline
from ..scenarios.lifecycle import (
    MACRO_STEP_RUN_PREFIX, DegradationModel, DegradationStepRecord, InputBinding, InputSource, StepStatus,
    evaluate_degradation_step,
)
from ..scenarios.timeline import HistoryKind, TimelineEventKind, TimePoint, TimeWindow, ValueStatus, canonical_digest
from ..scientific.errors import InvalidScientificProblem, ScientificCoreError
from ..scientific.multiphysics.receipts import StateVariableValue
from ..scientific.multiphysics.state import InitialStateValue
from ..scientific.units.quantity import Quantity
from ._common import fraction_text, identifier, time_seconds, window_seconds
from .aggregation import AggregationRecord, AggregationSpec, aggregate
from .approximation import ApproximationEntry, ApproximationLedger, ComponentStatus, ErrorComponent
from .checkpoint import MacroCheckpoint, state_to_list
from .fast import FastExecutionRequest, FastExecutionResult, FastSystem, check_material_reresolution, slow_state_digest
from .scales import ScaleHierarchy, ScaleRole
from .windows import AdaptationDecision, AdaptationTrigger, MacroStepPolicy, RefinementDecision, RepresentativeWindow, SelectionMethod

RUN_SCHEMA = "engcore.multiscale.run_record/1"
REFINING_EVENT_KINDS = frozenset({
    TimelineEventKind.DISCONTINUITY, TimelineEventKind.STATE_CHANGE_REQUEST,
    TimelineEventKind.TERMINATION, TimelineEventKind.SCHEDULED_SYNCHRONIZATION,
})

State = Mapping[str, Mapping[str, StateVariableValue]]


def freeze(state: Mapping[str, Mapping[str, StateVariableValue]]) -> State:
    """An immutable snapshot (StateVariableValue is itself frozen)."""
    return MappingProxyType({p: MappingProxyType(dict(v)) for p, v in state.items()})


def thaw(state: State) -> dict[str, dict[str, StateVariableValue]]:
    return {p: dict(v) for p, v in state.items()}


class MultiTimescaleRefusal(InvalidScientificProblem):
    """The multi-timescale approximation or step was refused."""


class RepresentativityRejected(MultiTimescaleRefusal):
    """A repeated period's inputs deviate from the resolved period beyond the declared tolerance."""


class ResumeRefused(InvalidScientificProblem):
    """A checkpoint cannot be resumed without inventing or losing state."""


class FastStateAtMacroStart(str, Enum):
    #: Carry the fast state at the end of the resolved window (only valid when
    #: every tile of the macro window is resolved, weight 1).
    CARRY_RESOLVED_END = "carry_resolved_end"
    #: Every macro window's fast physics starts from the declared initial fast state.
    DECLARED_INITIAL = "declared_initial"


@dataclass(frozen=True)
class LifecycleBinding:
    participant_id: str
    model: DegradationModel
    bindings: tuple[InputBinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "model": self.model.identity.to_dict(),
                "state_variables": [d.variable_id for d in self.model.state_variables],
                "requirements": [[r.input_id, r.source.value, r.subject] for r in self.model.requirements],
                "aggregate_requirements": [r.to_dict() for r in getattr(self.model, "aggregate_requirements", ())],
                "bindings": sorted([b.input_id, b.record_id] for b in self.bindings)}


@dataclass(frozen=True)
class RepresentativeExecution:
    representative: RepresentativeWindow
    request_identity: str
    result_digest: str
    coupled_windows: int
    coupling_iterations: int
    material_state_digests: tuple[str, ...]
    resolved_properties: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"representative": self.representative.to_dict(), "request_identity": self.request_identity,
                "result_digest": self.result_digest, "coupled_windows": self.coupled_windows,
                "coupling_iterations": self.coupling_iterations, "material_state_digests": list(self.material_state_digests),
                "resolved_properties": list(self.resolved_properties)}


@dataclass(frozen=True)
class MacroStepRecord:
    index: int
    window: TimeWindow
    previous_digest: str
    executions: tuple[RepresentativeExecution, ...]
    aggregations: tuple[AggregationRecord, ...]
    degradation: tuple[DegradationStepRecord, ...]
    slow_before: State
    slow_after: State
    adaptation: AdaptationDecision | None
    refinements: tuple[RefinementDecision, ...]
    threshold_crossings: tuple[str, ...]
    #: The fast results themselves (their digests are in ``executions``).
    results: tuple[FastExecutionResult, ...] = field(default=(), compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "window": self.window.to_dict(), "previous_digest": self.previous_digest,
                "executions": [e.to_dict() for e in self.executions], "aggregations": [a.digest for a in self.aggregations],
                "degradation": [d.digest for d in self.degradation], "slow_before": state_to_list(self.slow_before),
                "slow_after": state_to_list(self.slow_after),
                "adaptation": None if self.adaptation is None else self.adaptation.to_dict(),
                "refinements": [r.to_dict() for r in self.refinements], "threshold_crossings": list(self.threshold_crossings)}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def represented_seconds(self) -> Fraction:
        return window_seconds(self.window)

    @property
    def resolved_seconds(self) -> Fraction:
        return sum((window_seconds(e.representative.resolved) for e in self.executions), Fraction(0))


_COUNTERS = ("represented_seconds", "resolved_seconds", "executed_fast_seconds", "macro_windows", "representative_windows",
             "repeated_windows", "fast_executions", "coupled_solve_windows", "coupling_iterations", "cache_reuses",
             "event_splits", "rejections", "representativity_rejections", "threshold_localizations", "adaptation_changes")


def _new_accounting() -> dict[str, Any]:
    return {k: ("0/1" if k.endswith("_seconds") else 0) for k in _COUNTERS}


@dataclass
class MultiTimescaleRunRecord:
    run_id: str
    status: str  # completed | paused | terminated | stopped | refused
    reason: str
    identities: Mapping[str, str]
    start: TimePoint
    reached: TimePoint
    steps: tuple[MacroStepRecord, ...]
    checkpoints: tuple[MacroCheckpoint, ...]
    accounting: Mapping[str, Any]
    ledger: ApproximationLedger
    resumed_from: str
    final_slow_state: State
    final_fast_state: State
    wall_seconds: float = 0.0

    @property
    def last_valid_checkpoint(self) -> MacroCheckpoint | None:
        return self.checkpoints[-1] if self.checkpoints else None

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RUN_SCHEMA, "classification": "multi_timescale_execution_not_evidence", "run_id": self.run_id,
                "status": self.status, "reason": self.reason, "identities": dict(sorted(self.identities.items())),
                "start": self.start.to_dict(), "reached": self.reached.to_dict(), "steps": [s.digest for s in self.steps],
                "checkpoints": [c.digest for c in self.checkpoints], "accounting": dict(sorted(self.accounting.items())),
                "ledger": self.ledger.to_dict(), "resumed_from": self.resumed_from,
                "final_slow_state": state_to_list(self.final_slow_state), "final_fast_state": state_to_list(self.final_fast_state)}

    @property
    def digest(self) -> str:
        """Long-run identity (wall time excluded: it is a diagnostic, not identity)."""
        return canonical_digest(self.to_dict())


def _state_digest(values) -> str:
    return canonical_digest([v.to_dict() for v in sorted(values, key=lambda v: v.variable_id)])


def _add(acc: dict[str, Any], key: str, amount) -> None:
    if key.endswith("_seconds"):
        acc[key] = fraction_text(Fraction(acc[key]) + Fraction(amount))
    else:
        acc[key] = int(acc[key]) + int(amount)


class MultiTimescaleRuntime:
    def __init__(
        self,
        *,
        run_id: str,
        hierarchy: ScaleHierarchy,
        policy: MacroStepPolicy,
        fast_system: FastSystem,
        environment: EnvironmentTimeline,
        aggregations: tuple[AggregationSpec, ...] = (),
        lifecycle: tuple[LifecycleBinding, ...] = (),
        fast_state_policy: FastStateAtMacroStart | None = None,
    ) -> None:
        self.run_id = identifier(run_id, "multi-timescale run_id")
        self.hierarchy, self.policy, self.fast_system, self.environment = hierarchy, policy, fast_system, environment
        self.timeline = environment.timeline
        if not self.timeline.scenario_digest:
            raise InvalidScientificProblem("multi-timescale execution requires a scenario-bound timeline")
        self.aggregations = tuple(sorted(aggregations, key=lambda a: a.aggregate_id))
        if len({a.aggregate_id for a in self.aggregations}) != len(self.aggregations):
            raise InvalidScientificProblem("aggregate ids must be unique")
        for a in self.aggregations:
            fast_system.identity.output_unit(a.quantity_id)
        self.lifecycle = tuple(lifecycle)
        slow = {(s.participant_id, s.variable_id) for s in hierarchy.owned(ScaleRole.SLOW)}
        fast = {(s.participant_id, s.variable_id) for s in hierarchy.owned(ScaleRole.FAST)}
        owned: dict[tuple[str, str], str] = {}
        aggregate_ids = {a.aggregate_id for a in self.aggregations}
        for lb in self.lifecycle:
            for d in lb.model.state_variables:
                key = (lb.participant_id, d.variable_id)
                if key not in slow:
                    raise InvalidScientificProblem(f"degradation model {lb.model.identity.model_id} changes {key}, which is not declared SLOW state")
                if key in owned:
                    raise InvalidScientificProblem(f"slow state {key} is changed by two degradation models")
                owned[key] = lb.model.identity.model_id
            bound = {b.input_id: b.record_id for b in lb.bindings}
            for r in lb.model.requirements:
                if r.source is InputSource.PHYSICS_AGGREGATE and bound.get(r.input_id) not in aggregate_ids:
                    raise InvalidScientificProblem(f"input {r.input_id!r} is bound to an aggregate that is not declared")
        unowned = sorted(slow - set(owned))
        if unowned:
            raise InvalidScientificProblem(f"slow state {unowned} has no degradation authority; it could never change legitimately")
        for c in fast_system.identity.contracts:
            for v in c.evolved_state:
                if (c.participant_id, v) not in fast:
                    raise InvalidScientificProblem(
                        f"fast participant {c.participant_id!r} evolves {v!r}, which is not declared FAST state; "
                        f"a fast solver must not mutate slow authoritative state")
        for lim in policy.state_change_limits:
            if (lim.participant_id, lim.variable_id) not in slow:
                raise InvalidScientificProblem(f"state-change limit names non-slow state {lim.participant_id}.{lim.variable_id}")
        for w in policy.threshold_watches:
            if (w.participant_id, w.variable_id) not in slow:
                raise InvalidScientificProblem(f"threshold watch names non-slow state {w.participant_id}.{w.variable_id}")
            if time_seconds(w.localization) < time_seconds(policy.minimum_window):
                raise InvalidScientificProblem("threshold localization cannot be finer than the minimum macro window")
        for r in policy.rules:
            if r.trigger is AdaptationTrigger.NEAR_THRESHOLD and (r.participant_id, r.variable_id) not in slow:
                raise InvalidScientificProblem(f"near-threshold rule {r.rule_id!r} watches non-slow state {r.participant_id}.{r.variable_id}")
        rep = policy.representative
        if rep.selection is SelectionMethod.LEADING_PERIOD:
            unmeasurable = sorted([c.channel_id for c in environment.channels if c.representation is not ChannelRepresentation.INTERVAL_HISTORY]
                                  + [h.history_id for h in self.timeline.cycle_histories])
            if unmeasurable:
                raise InvalidScientificProblem(
                    f"inputs {unmeasurable} (point-sample channels / cycle histories) cannot yet be compared between a "
                    "resolved and a repeated period; representative repetition is refused while they are present")
            inputs = {c.channel_id for c in environment.channels if c.representation is ChannelRepresentation.INTERVAL_HISTORY}
            inputs |= {h.history_id for h in self.timeline.histories if h.kind is HistoryKind.USAGE}
            declared = {k for k, _ in rep.periodicity_tolerances}
            if inputs - declared or declared - inputs:
                raise InvalidScientificProblem(
                    f"a repeated representative period needs a declared periodicity tolerance for exactly the inputs "
                    f"{sorted(inputs)}; missing {sorted(inputs - declared)}, unknown {sorted(declared - inputs)}")
        ident = fast_system.identity
        contracts = {c.participant_id: c for c in ident.contracts}
        if not ident.participants or set(contracts) != set(ident.participants):
            raise InvalidScientificProblem(
                f"every fast participant {sorted(ident.participants)} needs exactly one state contract "
                f"(got {sorted(contracts)}); completeness is never true by omission")
        uncovered = sorted(k for k in fast if k[0] not in contracts or k[1] not in contracts[k[0]].evolved_state)
        if uncovered:
            raise InvalidScientificProblem(f"FAST state {uncovered} is not evolved by any participant contract")
        declared_out = {q: (f, r) for q, f, r in ident.output_semantics}
        if set(declared_out) != {q for q, _ in ident.outputs}:
            raise InvalidScientificProblem("every fast output declares its preserved history features and resolution")
        from .aggregation import HistoryFeature as _HF
        self._output_semantics = {q: (frozenset(_HF(x) for x in f), Fraction(r)) for q, (f, r) in declared_out.items()}
        use = {(p, v): u for p, v, u, _ in ident.slow_state_use}
        if set(use) != slow:
            raise InvalidScientificProblem(f"every SLOW variable declares whether the fast physics consumes it; "
                                           f"missing {sorted(slow - set(use))}, unknown {sorted(set(use) - slow)}")
        for b in ident.material_bindings:
            if use.get((b.participant_id, b.variable_id)) != "bound":
                raise InvalidScientificProblem(f"material binding {b.participant_id}.{b.variable_id} must be SLOW state declared 'bound'")
        if rep.selection is SelectionMethod.LEADING_PERIOD:
            if not ident.time_inputs_via_request:
                raise InvalidScientificProblem("a repeated period needs the fast system to declare that time enters only "
                                               "through the request (no drive cycle hidden in configuration)")
            fast_tol = {k for k, _ in rep.fast_state_tolerances}
            if fast_tol != {f"{p}.{v}" for p, v in fast}:
                raise InvalidScientificProblem("a repeated period needs a declared end-state tolerance for every FAST variable")
        if fast and fast_state_policy is None:
            raise InvalidScientificProblem("fast state exists; declare how each macro window's fast physics starts")
        self.fast_state_policy = FastStateAtMacroStart(fast_state_policy) if fast_state_policy is not None else None
        self._slow_keys, self._fast_keys = slow, fast
        self._fast_units = {(s.participant_id, s.variable_id): s.unit for s in hierarchy.owned(ScaleRole.FAST)}
        self._declared_fast: State = freeze({})
        self._cache: dict[str, tuple[FastExecutionResult, str]] = {}
        self._identity_digest = ident.digest

    # ---- identity ----------------------------------------------------------

    def identities(self) -> dict[str, str]:
        return {
            "scenario": self.timeline.scenario_digest, "timeline": self.timeline.digest, "environment": self.environment.digest,
            "hierarchy": self.hierarchy.digest, "policy": self.policy.digest, "fast_system": self.fast_system.identity.digest,
            "aggregations": canonical_digest([a.to_dict() for a in self.aggregations]),
            "lifecycle": canonical_digest([lb.to_dict() for lb in self.lifecycle]),
            "fast_state_policy": "" if self.fast_state_policy is None else self.fast_state_policy.value,
            "declared_fast_state": canonical_digest(state_to_list(self._declared_fast)),
        }

    # ---- context -----------------------------------------------------------

    def _environment_context(self, window: TimeWindow) -> tuple[dict[str, Any], ...]:
        items: list[dict[str, Any]] = []
        for c in self.environment.channels:
            if c.representation is ChannelRepresentation.INTERVAL_HISTORY:
                entries = [e.to_dict() for e in self.timeline.history(c.history_id).entries if e.window.overlaps(window)]
            else:
                # interpolated point channels can depend on samples outside the
                # window: bind all of them (over-inclusive identity never reuses wrongly)
                entries = [s.to_dict() for s in c.samples]
            src = self.environment.source(c.source_id)
            items.append({"channel": c.channel_id, "source_digest": src.content_digest, "classification": src.classification,
                          "entries": entries})
        return tuple(items)

    def _usage_context(self, window: TimeWindow) -> tuple[dict[str, Any], ...]:
        items = [{"history": h.history_id, "entries": [e.to_dict() for e in h.entries if e.window.overlaps(window)]}
                 for h in self.timeline.histories if h.kind is HistoryKind.USAGE]
        items += [{"cycles": h.history_id, "records": [c.to_dict() for c in h.cycles if c.window.overlaps(window)]}
                  for h in self.timeline.cycle_histories]
        return tuple(items)

    def _events_inside(self, start: Fraction, end: Fraction):
        return [e for e in self.timeline.events if e.kind in REFINING_EVENT_KINDS and start < e.at.seconds < end]

    def _input_histories(self):
        for c in self.environment.channels:
            if c.representation is ChannelRepresentation.INTERVAL_HISTORY:
                yield c.channel_id, "environment", self.timeline.history(c.history_id)
        for h in self.timeline.histories:
            if h.kind is HistoryKind.USAGE:
                yield h.history_id, "usage", h

    def _require_known_inputs(self, macro: TimeWindow) -> None:
        """A representative window cannot stand for an interval whose inputs are UNKNOWN.

        Every interval-history environment channel and every usage history must
        be declared over the whole macro window: the repetition assumption
        cannot be stated about conditions nobody knows, and missing history is
        never zero exposure.
        """
        unknown = []
        for record_id, kind, history in self._input_histories():
            gaps = history.gaps_within(macro)
            if gaps:
                unknown.append(f"{kind} {record_id!r} over {[(float(a), float(b)) for a, b in gaps]} s")
        if unknown:
            raise MultiTimescaleRefusal(f"inputs are UNKNOWN inside the macro window: {unknown}; the representative "
                                        "approximation is refused rather than assuming them")

    def _measure_representativity(self, rep: RepresentativeWindow) -> RepresentativeWindow:
        """Compare every repeated period's inputs with the resolved period, phase by phase."""
        if rep.weight == 1:
            return rep
        period = window_seconds(rep.resolved)
        start = rep.resolved.start.seconds
        deviations = []
        for record_id, kind, history in self._input_histories():
            tolerance = self.policy.representative.tolerance(record_id)
            worst = 0.0
            # piecewise-constant histories agree over a period iff they agree at the union of
            # both periods' change points (every entry start, from either side, folded to a phase)
            phases = {Fraction(0)}
            for e in history.entries:
                t = e.window.start.seconds
                if start <= t < rep.represented.end.seconds:
                    phases.add((t - start) % period)
            for k in range(1, int(rep.weight)):
                for phase in sorted(phases):
                    ref = history.value_at(TimePoint(rep.resolved.basis_id, start + phase))
                    other = history.value_at(TimePoint(rep.resolved.basis_id, start + k * period + phase))
                    if ref.status is not ValueStatus.KNOWN or other.status is not ValueStatus.KNOWN:
                        raise RepresentativityRejected(f"{kind} {record_id!r} is not declared at phase {float(phase):g} s of repetition {k}")
                    worst = max(worst, abs(other.value.value.magnitude_in(history.unit) - ref.value.value.magnitude_in(history.unit)))
            deviations.append((record_id, f"{worst!r} {history.unit}"))
            if worst > tolerance.magnitude_as_spread_in(history.unit):
                raise RepresentativityRejected(
                    f"{kind} {record_id!r} deviates by {worst:.6g} {history.unit} between the resolved period and a repeated "
                    f"period (declared tolerance {tolerance.magnitude:g} {tolerance.units}); repetition is not representative")
        return replace(rep, input_deviation=tuple(deviations))

    # ---- fast execution ----------------------------------------------------

    def _execute(self, rep: RepresentativeWindow, slow: State, fast: State, acc: dict[str, Any]) -> tuple[RepresentativeExecution, FastExecutionResult]:
        request = FastExecutionRequest(
            f"{self.run_id}:{rep.window_id}", self.fast_system.identity.digest, self.timeline.scenario_digest, self.timeline.digest,
            self.environment.digest, rep.resolved, freeze(slow), freeze(fast), self._environment_context(rep.resolved),
            self._usage_context(rep.resolved))
        key = request.identity
        if self.fast_system.identity.digest != self._identity_digest:
            raise MultiTimescaleRefusal("the fast system's identity changed after the runtime validated it")
        pure = self.fast_system.identity.pure
        if pure and key in self._cache:
            result, recorded = self._cache[key]
            if result.digest != recorded:
                raise MultiTimescaleRefusal("a cached fast result changed after it was recorded; exact reuse refused")
            _add(acc, "cache_reuses", 1)
        else:
            result = self.fast_system.execute(request)
            if request.identity != key:
                raise MultiTimescaleRefusal("the fast system altered its request; its result is not bound to what was asked")
            if not isinstance(result, FastExecutionResult) or result.request_identity != key:
                raise MultiTimescaleRefusal("fast system returned a result for a different request")
            if (result.consumed_environment_digest, result.consumed_timeline_digest) != (self.environment.digest, self.timeline.digest):
                raise MultiTimescaleRefusal("fast system read a different environment/timeline than this run is bound to")
            check_material_reresolution(self.fast_system.identity, request, result)
            if set(result.provider_versions) != set(self.fast_system.identity.providers):
                raise MultiTimescaleRefusal(f"fast execution ran providers {sorted(result.provider_versions)}, identity declares "
                                            f"{sorted(self.fast_system.identity.providers)}")
            if result.consumed_slow_state_digest != slow_state_digest(request.slow_state):
                raise MultiTimescaleRefusal("fast execution did not consume the slow state it was given")
            material_digests = {m.digest for m in result.material_states}
            for prop in result.resolved_properties:
                if "state_digest" in prop and prop["state_digest"] not in material_digests:
                    raise MultiTimescaleRefusal("a resolved property is not bound to a reported material state")
            for q, unit in self.fast_system.identity.outputs:
                s = result.series_for(q)
                if s.unit != unit:
                    raise MultiTimescaleRefusal(f"output {q!r} arrived in {s.unit!r}, declared {unit!r}")
                features, resolution = self._output_semantics[q]
                if not s.preserved_features <= features or any(window_seconds(x.window) > resolution for x in s.samples):
                    raise MultiTimescaleRefusal(f"output {q!r} claims more history (or coarser samples) than the fast system declares")
                if s.gaps_within(rep.resolved):
                    raise MultiTimescaleRefusal(f"fast execution left {q!r} unresolved inside {rep.window_id!r}")
            end_keys = {(p, k) for p in result.end_fast_state for k in result.end_fast_state[p]}
            if self.fast_state_policy is FastStateAtMacroStart.CARRY_RESOLVED_END:
                if end_keys != self._fast_keys:
                    raise MultiTimescaleRefusal(f"fast execution returned fast state {sorted(end_keys)}, declared {sorted(self._fast_keys)}")
                for (p, k) in end_keys:
                    result.end_fast_state[p][k].value.require_compatible(self._fast_units[(p, k)], context=f"fast state {p}.{k}")
            elif end_keys - self._fast_keys:
                raise MultiTimescaleRefusal(f"fast execution returned undeclared state {sorted(end_keys - self._fast_keys)}")
            if pure:
                self._cache[key] = (result, result.digest)
            _add(acc, "fast_executions", 1)
            _add(acc, "executed_fast_seconds", window_seconds(rep.resolved))
            _add(acc, "coupled_solve_windows", result.coupled_windows)
            _add(acc, "coupling_iterations", result.coupling_iterations)
        execution = RepresentativeExecution(rep, key, result.digest, result.coupled_windows, result.coupling_iterations,
                                            tuple(m.digest for m in result.material_states), tuple(result.resolved_properties))
        return execution, result

    # ---- main loop ---------------------------------------------------------

    def run(self, *, initial_slow_state: Mapping[str, Mapping[str, InitialStateValue]],
            initial_fast_state: Mapping[str, Mapping[str, InitialStateValue]] | None = None,
            until: TimePoint | None = None) -> MultiTimescaleRunRecord:
        slow = freeze(self._state_from(initial_slow_state, self._slow_keys, "slow"))
        fast = freeze(self._state_from(initial_fast_state or {}, self._fast_keys, "fast"))
        self._declared_fast = fast
        return self._loop(self.timeline.horizon.start.seconds, slow, fast, None, "", _new_accounting(), 0, until, "")

    def set_declared_fast_state(self, state: Mapping[str, Mapping[str, InitialStateValue]]) -> None:
        """Supply the declared initial fast state before :meth:`resume` (it is part of run identity)."""
        self._declared_fast = freeze(self._state_from(state, self._fast_keys, "fast"))

    def resume(self, checkpoint: MacroCheckpoint, *, until: TimePoint | None = None) -> MultiTimescaleRunRecord:
        """Continue from a verified checkpoint.

        The checkpoint digest detects corruption, not forgery (it is unkeyed);
        what makes a resume trustworthy is that every identity it binds must
        equal this runtime's, and every fast participant declared its state
        complete.
        """
        if not isinstance(checkpoint, MacroCheckpoint):
            raise ResumeRefused("resume takes a MacroCheckpoint (deserialize and verify the payload first)")
        if not checkpoint.resumable:
            raise ResumeRefused(checkpoint.resumable_reason)
        if not self.fast_system.identity.restartable:
            raise ResumeRefused("this fast system does not declare complete participant checkpoint state")
        if checkpoint.run_id != self.run_id:
            raise ResumeRefused(f"checkpoint belongs to run {checkpoint.run_id!r}, not {self.run_id!r}")
        mine = self.identities()
        diff = sorted(k for k in set(mine) | set(checkpoint.identities) if mine.get(k) != checkpoint.identities.get(k))
        if diff:
            raise ResumeRefused(f"checkpoint was produced under different {diff}; evidence stays bound to its context")
        if checkpoint.at.basis_id != self.timeline.basis.basis_id:
            raise ResumeRefused("checkpoint is on another time basis")
        if set(checkpoint.accounting) != set(_COUNTERS):
            raise ResumeRefused("checkpoint accounting does not carry exactly the declared counters")
        slow, fast = freeze(checkpoint.slow_state), freeze(checkpoint.fast_state)
        if {(p, k) for p in slow for k in slow[p]} != self._slow_keys or {(p, k) for p in fast for k in fast[p]} != self._fast_keys:
            raise ResumeRefused("checkpoint state does not cover exactly the declared slow/fast state")
        return self._loop(checkpoint.at.seconds, slow, fast, checkpoint.selected_seconds, checkpoint.chain_digest,
                          dict(checkpoint.accounting), checkpoint.step_index, until, checkpoint.digest)

    @staticmethod
    def _state_from(values, keys, label) -> dict[str, dict[str, StateVariableValue]]:
        out: dict[str, dict[str, StateVariableValue]] = {}
        for pid, vars_ in dict(values).items():
            for k, v in dict(vars_).items():
                out.setdefault(pid, {})[k] = StateVariableValue(k, v.value, v.uncertainty)
        got = {(p, k) for p in out for k in out[p]}
        if got != keys:
            raise InvalidScientificProblem(f"{label} state must supply exactly {sorted(keys)}; missing {sorted(keys - got)}, "
                                           f"extra {sorted(got - keys)} (nothing is defaulted)")
        return out

    def _loop(self, t: Fraction, slow: State, fast: State, prev_size: Fraction | None, chain: str, acc: dict[str, Any],
              index: int, until: TimePoint | None, resumed_from: str) -> MultiTimescaleRunRecord:
        began = _time.perf_counter()
        basis = self.timeline.basis.basis_id
        horizon_start, end = self.timeline.horizon.start.seconds, self.timeline.horizon.end.seconds
        steps: list[MacroStepRecord] = []
        checkpoints: list[MacroCheckpoint] = []
        status, reason = "completed", ""
        start_point = TimePoint(basis, t)
        while t < end:
            try:
                at_t = [e for e in self.timeline.events if e.at.seconds == t]
                term = [e for e in at_t if e.kind is TimelineEventKind.TERMINATION]
                if term:
                    status, reason = "terminated", f"declared TERMINATION event {term[0].event_id!r} ({term[0].subject_id}) at {float(t):g} s"
                    break
                request = [e for e in at_t if e.kind is TimelineEventKind.STATE_CHANGE_REQUEST]
                if request:
                    status = "refused"
                    reason = (f"STATE_CHANGE_REQUEST {request[0].event_id!r} for {request[0].subject_id!r} at {float(t):g} s: "
                              "no declared transition authority applies requested state changes in the multi-timescale runtime")
                    break
                if until is not None and t >= until.seconds:
                    status, reason = "paused", f"paused at the first macro boundary at or after {float(until.seconds):g} s"
                    break
                size, rule, why = self.policy.select(t - horizon_start, {(p, k): v.value for p in slow for k, v in slow[p].items()})
                adaptation = None
                if size != prev_size:
                    adaptation = AdaptationDecision(TimePoint(basis, t), prev_size, size, rule.trigger.value, rule.rule_id,
                                                    "" if rule.threshold is None else f"{rule.threshold.magnitude:g} {rule.threshold.units}",
                                                    self.policy.digest, why)
                    if prev_size is not None:
                        _add(acc, "adaptation_changes", 1)
                prev_size = size
                attempt_end = min(t + size, end)
                refinements: list[RefinementDecision] = []
                inside = self._events_inside(t, attempt_end)
                if inside:
                    ev = inside[0]
                    if self.policy.event_handling.value == "refuse":
                        status = "refused"
                        reason = (f"event {ev.event_id!r} ({ev.kind.value}) at {float(ev.at.seconds):g} s lies inside macro window "
                                  f"[{float(t):g}, {float(attempt_end):g}] s and the policy refuses to approximate across events")
                        break
                    refinements.append(RefinementDecision("event_split", TimePoint(basis, t), TimePoint(basis, attempt_end), ev.at,
                                                          ev.event_id, f"{ev.kind.value} of {ev.subject_id or 'timeline'}; window ends at the event"))
                    _add(acc, "event_splits", 1)
                    attempt_end = ev.at.seconds
                rejections = 0
                outcome = None
                minimum = time_seconds(self.policy.minimum_window)
                while True:
                    macro = TimeWindow(TimePoint(basis, t), TimePoint(basis, attempt_end))
                    duration = attempt_end - t
                    kind, detail = "", ""
                    try:
                        outcome = self._attempt(index, macro, slow, fast, acc)
                    except RepresentativityRejected as exc:
                        kind, detail = "representativity_rejected", str(exc)
                    if not kind:
                        executions, results, aggregates, degradation, new_slow = outcome
                        not_applied = [d for d in degradation if d.status is not StepStatus.APPLIED]
                        if not_applied:
                            d = not_applied[0]
                            status = "stopped"
                            reason = (f"degradation of {d.participant_id} by {d.model.model_id} was {d.status.value}: {d.reason}; "
                                      "no state change is guessed and the run stops at the last valid checkpoint")
                            outcome = None
                            break
                        violations = []
                        for lim in self.policy.state_change_limits:
                            n = lim.normalized(slow[lim.participant_id][lim.variable_id].value, new_slow[lim.participant_id][lim.variable_id].value)
                            if n > float(lim.allowed):
                                violations.append(f"{lim.participant_id}.{lim.variable_id} normalized change {n:.6g} > {float(lim.allowed):g} "
                                                  f"(scale {lim.scale.magnitude:g} {lim.scale.units})")
                        unlocalized = [w for w in self.policy.threshold_watches
                                       if w.crossed(slow[w.participant_id][w.variable_id].value, new_slow[w.participant_id][w.variable_id].value)
                                       and duration > time_seconds(w.localization)]
                        if not violations and not unlocalized:
                            break
                        kind = "state_change_rejected" if violations else "threshold_localization"
                        detail = "; ".join(violations) if violations else ", ".join(
                            f"{w.watch_id} crossed within a {float(duration):g} s step > localization {float(time_seconds(w.localization)):g} s"
                            for w in unlocalized)
                    if duration <= minimum:
                        status, reason = "refused", f"{kind} even at the minimum macro window: {detail}"
                        outcome = None
                        break
                    rejections += 1
                    if rejections > self.policy.max_rejections_per_step:
                        status, reason = "refused", f"macro step exceeded its maximum number of rejections ({detail})"
                        outcome = None
                        break
                    new_duration = max(minimum, duration / self.policy.rejection_divisor)
                    refinements.append(RefinementDecision(kind, TimePoint(basis, t), TimePoint(basis, attempt_end),
                                                          TimePoint(basis, t + new_duration), "slow_state" if kind != "representativity_rejected" else "inputs",
                                                          detail))
                    _add(acc, {"state_change_rejected": "rejections", "threshold_localization": "threshold_localizations",
                               "representativity_rejected": "representativity_rejections"}[kind], 1)
                    attempt_end = t + new_duration
                if outcome is None:
                    break
                executions, results, aggregates, degradation, new_slow = outcome
                crossed = tuple(w.watch_id for w in self.policy.threshold_watches
                                if w.crossed(slow[w.participant_id][w.variable_id].value, new_slow[w.participant_id][w.variable_id].value))
                step = MacroStepRecord(index, macro, chain, executions, aggregates, degradation, slow, new_slow, adaptation,
                                       tuple(refinements), crossed, tuple(results))
                if self.fast_state_policy is FastStateAtMacroStart.CARRY_RESOLVED_END:
                    next_fast = freeze(results[-1].end_fast_state)
                elif self.fast_state_policy is FastStateAtMacroStart.DECLARED_INITIAL:
                    next_fast = self._declared_fast
                else:
                    next_fast = fast
                steps.append(step)
                chain = step.digest
                _add(acc, "macro_windows", 1)
                _add(acc, "representative_windows", len(executions))
                _add(acc, "repeated_windows", sum(1 for e in executions if e.representative.weight != 1))
                _add(acc, "represented_seconds", step.represented_seconds)
                _add(acc, "resolved_seconds", step.resolved_seconds)
                slow, fast = new_slow, next_fast
                index += 1
                t = attempt_end
                checkpoints.append(MacroCheckpoint(
                    f"{self.run_id}:cp-{index}", self.run_id, index, TimePoint(basis, t), self.identities(), slow, fast,
                    tuple(self.fast_system.identity.contracts), tuple(d for e in executions for d in e.material_state_digests),
                    canonical_digest(list(self._environment_context(macro))), tuple(e.representative.to_dict() for e in executions),
                    tuple(a.digest for a in aggregates), tuple(d.digest for d in degradation), chain, prev_size, dict(acc)))
            except ScientificCoreError as exc:
                status, reason = "refused", f"macro step {index} at {float(t):g} s refused: {exc}"
                break
            except Exception as exc:  # a failure is a refusal; valid checkpoints are kept, never discarded
                status, reason = "refused", f"macro step {index} at {float(t):g} s failed with {type(exc).__name__}: {exc}"
                break
        if status == "completed":
            # N4: declared events exactly at the horizon end still act
            at_end = [e for e in self.timeline.events if e.at.seconds == t]
            if any(e.kind is TimelineEventKind.STATE_CHANGE_REQUEST for e in at_end):
                status, reason = "refused", "STATE_CHANGE_REQUEST at the horizon end: no declared transition authority applies it"
            elif any(e.kind is TimelineEventKind.TERMINATION for e in at_end):
                status, reason = "terminated", "declared TERMINATION event at the horizon end"
        return MultiTimescaleRunRecord(self.run_id, status, reason, self.identities(), start_point, TimePoint(basis, t), tuple(steps),
                                       tuple(checkpoints), dict(acc), self._ledger(acc, resumed=bool(resumed_from)), resumed_from, slow, fast,
                                       wall_seconds=_time.perf_counter() - began)

    def _attempt(self, index: int, macro: TimeWindow, slow: State, fast: State, acc: dict[str, Any]):
        self._require_known_inputs(macro)
        reps = tuple(self._measure_representativity(r) for r in self.policy.representative.build(macro, f"macro-{index}-rep-0"))
        if self.fast_state_policy is FastStateAtMacroStart.CARRY_RESOLVED_END and any(r.weight != 1 for r in reps):
            raise MultiTimescaleRefusal("the fast state at the end of a REPEATED representative window is not the state at the "
                                        "macro-window end; carrying it would invent a trajectory")
        executions, results = [], []
        tile_fast = fast
        for rep in reps:
            execution, result = self._execute(rep, slow, tile_fast, acc)
            if rep.weight != 1 and self._fast_keys:
                tolerances = dict(self.policy.representative.fast_state_tolerances)
                for p, k in sorted(self._fast_keys):
                    start_v = tile_fast[p][k].value
                    end_v = result.end_fast_state.get(p, {}).get(k)
                    if end_v is None:
                        raise RepresentativityRejected(f"repeated period did not report its end fast state {p}.{k}")
                    tol = tolerances[f"{p}.{k}"]
                    drift = abs(end_v.value.magnitude_in(start_v.units) - start_v.magnitude)
                    if drift > tol.magnitude_as_spread_in(start_v.units):
                        raise RepresentativityRejected(
                            f"fast state {p}.{k} does not return to its start over the resolved period (drift {drift:.6g} "
                            f"{start_v.units} > tolerance {tol.magnitude:g} {tol.units}); repetition is not periodic")
            executions.append(execution)
            results.append(result)
            if self.fast_state_policy is FastStateAtMacroStart.CARRY_RESOLVED_END:
                tile_fast = freeze(result.end_fast_state)
        aggregates = tuple(aggregate(spec, [(e.representative, r.series_for(spec.quantity_id)) for e, r in zip(executions, results)], macro)
                           for spec in self.aggregations)
        by_id = {a.aggregate_id: a for a in aggregates}
        execution_digest = canonical_digest([e.to_dict() for e in executions])
        degradation = []
        new_slow = thaw(slow)
        for lb in self.lifecycle:
            prior = tuple(slow[lb.participant_id][d.variable_id] for d in lb.model.state_variables)
            step = evaluate_degradation_step(
                lb.model, environment=self.environment, window=macro, participant_id=lb.participant_id, prior_values=prior,
                prior_state_digest=_state_digest(prior), bindings=lb.bindings, run_id=f"{MACRO_STEP_RUN_PREFIX}{self.run_id}.{index}",
                run_digest_value=execution_digest, aggregates=by_id)
            degradation.append(step)
            if step.applied:
                for v in step.resulting_values:
                    new_slow[lb.participant_id][v.variable_id] = v
        return tuple(executions), tuple(results), aggregates, tuple(degradation), freeze(new_slow)

    def _ledger(self, acc: Mapping[str, Any], *, resumed: bool = False) -> ApproximationLedger:
        """Built from the CUMULATIVE accounting, which a checkpoint carries across resume.

        After a resume the pre-resume work is attested only by the (unkeyed) checkpoint
        accounting, so the representative-window component can never be NOT_APPLICABLE:
        a caller-edited counter must not turn into a no-approximation claim.
        """
        repeated = int(acc["repeated_windows"]) > 0 or resumed
        models = sorted(lb.model.identity.model_id for lb in self.lifecycle)
        entries = (
            ApproximationEntry(ErrorComponent.NUMERICAL_SOLVER, ComponentStatus.UNKNOWN,
                               "provider solves met their declared convergence criteria; discretization and solver error are not bounded"),
            ApproximationEntry(ErrorComponent.TIME_INTEGRATION, ComponentStatus.UNKNOWN,
                               "fast outputs are resolved per coupling window and held constant across it; time-integration error not quantified"),
            ApproximationEntry(ErrorComponent.MAPPING,
                               ComponentStatus.NOT_APPLICABLE if self.fast_system.identity.field_mapping is False else ComponentStatus.UNKNOWN,
                               f"the fast system declares no field mapping: {self.fast_system.identity.field_mapping_basis}"
                               if self.fast_system.identity.field_mapping is False else
                               ("field mapping inside the fast system is not bounded" if self.fast_system.identity.field_mapping
                                else "field mapping was not declared; its error is UNKNOWN")),
            ApproximationEntry(ErrorComponent.AGGREGATION, ComponentStatus.UNKNOWN,
                               "aggregates discard sub-window variation and state what they lose; the effect on degradation is not quantified"),
            ApproximationEntry(ErrorComponent.REPRESENTATIVE_WINDOW,
                               ComponentStatus.UNKNOWN if repeated else ComponentStatus.NOT_APPLICABLE,
                               ("representative repetition is a declared approximation; its error is not quantified" if int(acc["repeated_windows"]) > 0
                                else "work before the resume is attested only by the checkpoint's accounting") if repeated
                               else "every represented interval of this run was resolved (weight 1)"),
            ApproximationEntry(ErrorComponent.MODEL_UNCERTAINTY, ComponentStatus.UNKNOWN,
                               "degradation inputs, parameters and resulting state carry UNKNOWN uncertainty"),
            ApproximationEntry(ErrorComponent.MODEL_DISCREPANCY, ComponentStatus.UNKNOWN,
                               f"model discrepancy of {models} is declared UNKNOWN or not combinable; never zero"),
        )
        return ApproximationLedger(entries)


@dataclass(frozen=True)
class ResumeComparison:
    """Uninterrupted vs checkpoint-resumed execution: reproducibility, not validation."""

    matched: bool
    compared_steps: int
    first_mismatch: str
    semantics: str

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "reproducibility_not_validation", "matched": self.matched, "compared_steps": self.compared_steps,
                "first_mismatch": self.first_mismatch, "semantics": self.semantics}


def compare_resume(uninterrupted: MultiTimescaleRunRecord, first: MultiTimescaleRunRecord, resumed: MultiTimescaleRunRecord) -> ResumeComparison:
    """Declared semantics: every macro-step digest (windows, representative weights and measured input
    deviations, fast request identities, fast result digests, aggregates, degradation records, slow
    state), the final state, the accounting and the approximation ledger must be IDENTICAL."""
    semantics = ("exact equality of macro-step digests, final slow/fast state, accounting and approximation-ledger "
                 "statuses (the resumed REPRESENTATIVE_WINDOW status may only be weaker: UNKNOWN); wall time excluded")
    if first.last_valid_checkpoint is None or resumed.resumed_from != first.last_valid_checkpoint.digest:
        return ResumeComparison(False, 0, "resumed run does not name the first half's last valid checkpoint", semantics)
    combined = list(first.steps) + list(resumed.steps)
    if len(combined) != len(uninterrupted.steps):
        return ResumeComparison(False, 0, f"{len(combined)} steps vs {len(uninterrupted.steps)} uninterrupted", semantics)
    for i, (a, b) in enumerate(zip(uninterrupted.steps, combined)):
        if a.digest != b.digest:
            return ResumeComparison(False, i, f"macro step {i} differs", semantics)
    if state_to_list(uninterrupted.final_slow_state) != state_to_list(resumed.final_slow_state) or \
            state_to_list(uninterrupted.final_fast_state) != state_to_list(resumed.final_fast_state):
        return ResumeComparison(False, len(combined), "final state differs", semantics)
    if dict(uninterrupted.accounting) != dict(resumed.accounting):
        return ResumeComparison(False, len(combined), "accounting differs", semantics)
    for a, b in zip(uninterrupted.ledger.entries, resumed.ledger.entries):
        if a.status != b.status and not (a.component is ErrorComponent.REPRESENTATIVE_WINDOW and b.status is ComponentStatus.UNKNOWN):
            return ResumeComparison(False, len(combined), f"approximation ledger differs on {a.component.value}", semantics)
    return ResumeComparison(True, len(combined), "", semantics)
