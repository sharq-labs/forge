"""Lifecycle / Degradation Engine: accumulated exposure and usage change future state.

Flow, window by window::

    physics run over [t_k, t_k+1]            (MultiphysicsRuntime, unchanged)
      -> StateTransitionReceipt end values    (existing state authority)
      -> DegradationModel increment over the window, fed ONLY by explicitly
         bound inputs: environment doses / window means (EnvironmentTimeline),
         usage integrals and cycle counts (Timeline histories)
      -> DegradationStepRecord                (this module; digest-bound)
      -> carry_forward -> InitialStateValue   (existing runtime input)
    physics run over [t_k+1, t_k+2] initialized from the degraded state
      -> its InitialStateReceipt must acknowledge exactly those values

No second timeline, environment, state or provenance authority is created:
state variables are :class:`InitialStateDefinition` records, starting state is
a participant's own :class:`StateTransitionReceipt`, and the next window's
state enters through the runtime's own ``initial_state`` / receipt path.

Scientific stance:

* A degradation model's output is a model prediction under declared
  applicability, never evidence of physical truth, never validation.
* A missing input (exposure gap, point-sample channel, unrecorded cycles,
  partial cycles) makes the step UNKNOWN; nothing is treated as zero.
* Out-of-applicability inputs make the step NOT_APPLICABLE; no state changes.
* Resulting-state uncertainty is UNKNOWN unless it can be computed from
  declared information.  This engine does not propagate uncertainty through
  a model, so it records each component's status and leaves the result
  UNKNOWN.  Missing model discrepancy is UNKNOWN, never zero.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import re
from typing import Any, Callable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics.receipts import StateTransitionReceipt, StateVariableValue, require_digest
from ..scientific.multiphysics.state import InitialStateDefinition, InitialStateValue
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, normalize_unit
from .contracts import NamedQuantity
from .environment import ChannelRepresentation, EnvironmentTimeline, EnvironmentValue
from .timeline import HistoryKind, TimePoint, TimeWindow, ValueStatus, canonical_digest, exact_seconds

MODEL_IDENTITY_SCHEMA = schema_string("degradation_model_identity")
STEP_RECORD_SCHEMA = schema_string("degradation_step_record")
CHAIN_SCHEMA = schema_string("lifecycle_chain")

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


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


def run_digest(run: Any) -> str:
    """Identity of a physics run record (reproducibility identity, not evidence)."""
    return canonical_digest(run.to_dict())


# --------------------------------------------------------------------------
# Model contract
# --------------------------------------------------------------------------


class InputSource(str, Enum):
    #: Time integral of an interval-history environment channel (``EnvironmentTimeline.dose``).
    EXPOSURE_DOSE = "exposure_dose"
    #: Time-weighted mean of an interval-history environment channel.
    EXPOSURE_MEAN = "exposure_mean"
    #: Time integral of a USAGE ``QuantityHistory`` in the timeline.
    USAGE_INTEGRAL = "usage_integral"
    #: Number of complete cycles of a ``CycleHistory`` inside the window.
    CYCLE_COUNT = "cycle_count"


@dataclass(frozen=True)
class InputRequirement:
    """What a model needs.  ``subject`` is the environment kind_id, the usage
    quantity_id or the cycle_kind the bound record must carry."""

    input_id: str
    source: InputSource
    subject: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "input_id"))
        try:
            object.__setattr__(self, "source", InputSource(self.source))
        except ValueError as exc:
            raise InvalidScientificProblem(f"unsupported input source {self.source!r}") from exc
        object.__setattr__(self, "subject", _identifier(self.subject, "input subject"))


@dataclass(frozen=True)
class InputBinding:
    """The caller's explicit choice of record for one requirement.  Never inferred."""

    input_id: str
    record_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "binding input_id"))
        object.__setattr__(self, "record_id", _identifier(self.record_id, "binding record_id"))


@dataclass(frozen=True)
class ApplicabilityBound:
    """Declared range of one gathered input inside which the model is claimed to apply."""

    input_id: str
    lower: Quantity | None = None
    upper: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "applicability input_id"))
        if self.lower is None and self.upper is None:
            raise InvalidScientificProblem("an applicability bound needs a lower or an upper limit")
        if self.lower is not None and self.upper is not None:
            self.upper.require_compatible(self.lower.units, context="applicability bound")
            if self.upper.magnitude_in(self.lower.units) < self.lower.magnitude:
                raise InvalidScientificProblem("applicability upper bound is below lower bound")

    def admits(self, value: Quantity) -> bool:
        if self.lower is not None and value.magnitude_in(self.lower.units) < self.lower.magnitude:
            return False
        if self.upper is not None and value.magnitude_in(self.upper.units) > self.upper.magnitude:
            return False
        return True


@dataclass(frozen=True)
class DegradationModelIdentity:
    model_id: str
    version: str
    parameters: tuple[NamedQuantity, ...]
    #: Model-form discrepancy of the increment.  Default UNKNOWN, never zero.
    model_discrepancy: Uncertainty = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _identifier(self.model_id, "model_id"))
        version = str(self.version or "").strip()
        if not version:
            raise InvalidScientificProblem("degradation model requires a version")
        object.__setattr__(self, "version", version)
        params = tuple(self.parameters)
        if any(not isinstance(p, NamedQuantity) for p in params) or len({p.quantity_id for p in params}) != len(params):
            raise InvalidScientificProblem("model parameters must be unique NamedQuantity records")
        object.__setattr__(self, "parameters", tuple(sorted(params)))
        discrepancy = self.model_discrepancy
        if discrepancy is None:
            discrepancy = Uncertainty.unknown(f"model discrepancy of {self.model_id} was not declared")
        if not isinstance(discrepancy, Uncertainty):
            raise InvalidScientificProblem("model_discrepancy must be an Uncertainty")
        object.__setattr__(self, "model_discrepancy", discrepancy)

    def parameter(self, parameter_id: str) -> Quantity:
        for p in self.parameters:
            if p.quantity_id == parameter_id:
                return p.value
        raise InvalidScientificProblem(f"model {self.model_id} has no parameter {parameter_id!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MODEL_IDENTITY_SCHEMA, "model_id": self.model_id, "version": self.version, "parameters": [p.to_dict() for p in self.parameters], "model_discrepancy": self.model_discrepancy.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DegradationModelIdentity":
        require_schema(payload, MODEL_IDENTITY_SCHEMA)
        _strict_keys(payload, {"schema", "model_id", "version", "parameters", "model_discrepancy"}, "model identity")
        return cls(payload["model_id"], payload["version"], tuple(NamedQuantity.from_dict(p) for p in payload["parameters"]), Uncertainty.from_dict(payload["model_discrepancy"]))


class DegradationModel(ABC):
    """Provider-neutral degradation contract.

    A model owns a declared set of participant state variables, declares the
    inputs it needs and the range it applies to, and computes the new values
    of its state variables over one window.  It never sees raw environment
    channels, never chooses its own inputs and never sets uncertainty.
    """

    identity: DegradationModelIdentity
    state_variables: tuple[InitialStateDefinition, ...]
    requirements: tuple[InputRequirement, ...]
    applicability: tuple[ApplicabilityBound, ...]

    @abstractmethod
    def advance(
        self,
        inputs: Mapping[str, Quantity],
        state: Mapping[str, Quantity],
        duration: Quantity,
    ) -> Mapping[str, Quantity]:
        """New values of every state variable after ``duration``."""


# --------------------------------------------------------------------------
# Step record
# --------------------------------------------------------------------------


class StepStatus(str, Enum):
    APPLIED = "applied"
    UNKNOWN_INPUT = "unknown_input"
    UNKNOWN_STATE = "unknown_state"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class GatheredInput:
    """One model input with the full identity of where it came from."""

    input_id: str
    source: InputSource
    record_id: str
    status: ValueStatus
    value: NamedQuantity | None
    reason: str
    #: Environment inputs only: context, source and source classification/digest.
    context_id: str = ""
    source_id: str = ""
    source_classification: str = ""
    source_content_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"input_id": self.input_id, "source": self.source.value, "record_id": self.record_id, "status": self.status.value, "value": None if self.value is None else self.value.to_dict(), "reason": self.reason, "context_id": self.context_id, "source_id": self.source_id, "source_classification": self.source_classification, "source_content_digest": self.source_content_digest}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "GatheredInput":
        _strict_keys(p, {"input_id", "source", "record_id", "status", "value", "reason", "context_id", "source_id", "source_classification", "source_content_digest"}, "gathered input")
        return cls(p["input_id"], InputSource(p["source"]), p["record_id"], ValueStatus(p["status"]), None if p["value"] is None else NamedQuantity.from_dict(p["value"]), p["reason"], p["context_id"], p["source_id"], p["source_classification"], p["source_content_digest"])


@dataclass(frozen=True)
class DegradationStepRecord:
    """One window's degradation, bound to everything that produced it."""

    participant_id: str
    scenario_digest: str
    environment_digest: str
    run_id: str
    run_digest: str
    window: TimeWindow
    prior_state_digest: str
    prior_values: tuple[StateVariableValue, ...]
    inputs: tuple[GatheredInput, ...]
    model: DegradationModelIdentity
    status: StepStatus
    resulting_values: tuple[StateVariableValue, ...]
    uncertainty_status: tuple[tuple[str, str], ...]
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", _identifier(self.participant_id, "participant_id"))
        for label in ("scenario_digest", "environment_digest", "run_digest", "prior_state_digest"):
            object.__setattr__(self, label, require_digest(getattr(self, label), label))
        object.__setattr__(self, "status", StepStatus(self.status))
        if self.status is StepStatus.APPLIED:
            if not self.resulting_values:
                raise InvalidScientificProblem("an applied degradation step must carry resulting values")
        elif self.resulting_values:
            raise InvalidScientificProblem("a step that was not applied carries no resulting state")
        object.__setattr__(self, "prior_values", tuple(sorted(self.prior_values)))
        object.__setattr__(self, "resulting_values", tuple(sorted(self.resulting_values)))
        object.__setattr__(self, "inputs", tuple(sorted(self.inputs, key=lambda i: i.input_id)))
        object.__setattr__(self, "uncertainty_status", tuple(sorted(tuple(x) for x in self.uncertainty_status)))

    @property
    def applied(self) -> bool:
        return self.status is StepStatus.APPLIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STEP_RECORD_SCHEMA, "classification": "degradation_model_output_not_evidence",
            "participant_id": self.participant_id, "scenario_digest": self.scenario_digest,
            "environment_digest": self.environment_digest, "run_id": self.run_id, "run_digest": self.run_digest,
            "window": self.window.to_dict(), "prior_state_digest": self.prior_state_digest,
            "prior_values": [v.to_dict() for v in self.prior_values],
            "inputs": [i.to_dict() for i in self.inputs], "model": self.model.to_dict(),
            "status": self.status.value, "resulting_values": [v.to_dict() for v in self.resulting_values],
            "uncertainty_status": [list(x) for x in self.uncertainty_status], "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "DegradationStepRecord":
        require_schema(p, STEP_RECORD_SCHEMA)
        _strict_keys(p, {"schema", "classification", "participant_id", "scenario_digest", "environment_digest", "run_id", "run_digest", "window", "prior_state_digest", "prior_values", "inputs", "model", "status", "resulting_values", "uncertainty_status", "reason"}, "degradation step")
        if p["classification"] != "degradation_model_output_not_evidence":
            raise InvalidScientificProblem("degradation step classification mismatch")
        return cls(
            p["participant_id"], p["scenario_digest"], p["environment_digest"], p["run_id"], p["run_digest"],
            TimeWindow.from_dict(p["window"]), p["prior_state_digest"],
            tuple(StateVariableValue.from_dict(v) for v in p["prior_values"]),
            tuple(GatheredInput.from_dict(i) for i in p["inputs"]), DegradationModelIdentity.from_dict(p["model"]),
            p["status"], tuple(StateVariableValue.from_dict(v) for v in p["resulting_values"]),
            tuple((a, b) for a, b in p["uncertainty_status"]), p["reason"],
        )


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


def _gather(requirement: InputRequirement, record_id: str, environment: EnvironmentTimeline, window: TimeWindow) -> GatheredInput:
    source = requirement.source
    if source in (InputSource.EXPOSURE_DOSE, InputSource.EXPOSURE_MEAN):
        channel = environment.channel(record_id)
        if channel.kind_id != requirement.subject:
            raise InvalidScientificProblem(
                f"input {requirement.input_id!r} needs environment kind {requirement.subject!r}; "
                f"channel {record_id!r} carries {channel.kind_id!r}"
            )
        value: EnvironmentValue = (environment.dose if source is InputSource.EXPOSURE_DOSE else environment.window_mean)(record_id, window)
        src = environment.source(channel.source_id)
        return GatheredInput(requirement.input_id, source, record_id, value.status, value.value, value.reason,
                             channel.context.context_id, src.source_id, src.classification, src.content_digest)
    timeline = environment.timeline
    if source is InputSource.USAGE_INTEGRAL:
        history = timeline.history(record_id)
        if history.kind is not HistoryKind.USAGE or history.quantity_id != requirement.subject:
            raise InvalidScientificProblem(f"input {requirement.input_id!r} needs USAGE history of {requirement.subject!r}")
        result = history.integrate(window)
        return GatheredInput(requirement.input_id, source, record_id, result.status, result.value, result.reason)
    matches = [h for h in timeline.cycle_histories if h.history_id == record_id]
    if not matches or matches[0].cycle_kind != requirement.subject:
        raise InvalidScientificProblem(f"input {requirement.input_id!r} needs a cycle history of kind {requirement.subject!r}")
    count = matches[0].count_within(window)
    if count.status is not ValueStatus.KNOWN:
        return GatheredInput(requirement.input_id, source, record_id, ValueStatus.UNKNOWN, None, count.reason)
    if count.partial_cycle_ids:
        return GatheredInput(requirement.input_id, source, record_id, ValueStatus.UNKNOWN, None,
                             f"cycles {list(count.partial_cycle_ids)} straddle the window; their share is not declared")
    return GatheredInput(requirement.input_id, source, record_id, ValueStatus.KNOWN,
                         NamedQuantity(f"{requirement.input_id}", Quantity(count.complete, "dimensionless"),
                                       Uncertainty.unknown("cycle count is a declared record; its uncertainty is not stated")), "")


def evaluate_degradation(
    model: DegradationModel,
    *,
    environment: EnvironmentTimeline,
    run: Any,
    participant_id: str,
    bindings: tuple[InputBinding, ...],
) -> DegradationStepRecord:
    """Degrade one participant's state over the window a physics run just covered."""
    from ..scientific.multiphysics.report import MultiphysicsRunRecord

    if not isinstance(model, DegradationModel):
        raise InvalidScientificProblem("evaluate_degradation requires a DegradationModel")
    if not isinstance(environment, EnvironmentTimeline):
        raise InvalidScientificProblem("evaluate_degradation requires an EnvironmentTimeline")
    if not isinstance(run, MultiphysicsRunRecord):
        raise InvalidScientificProblem("evaluate_degradation requires a MultiphysicsRunRecord")
    timeline = environment.timeline
    if run.scenario_digest != timeline.scenario_digest:
        raise InvalidScientificProblem("the physics run was executed for a different scenario than the environment")
    basis = timeline.basis.basis_id
    window = TimeWindow(TimePoint(basis, run.started_at), TimePoint(basis, run.ended_at))
    if not timeline.horizon.covers(window):
        raise InvalidScientificProblem("the physics run window lies outside the scenario horizon")

    required = {r.input_id: r for r in model.requirements}
    bound = {b.input_id: b.record_id for b in bindings}
    if len(bound) != len(tuple(bindings)) or set(bound) != set(required):
        raise InvalidScientificProblem(
            f"bindings must name exactly the model's inputs {sorted(required)}; got {sorted(bound)}"
        )

    transitions = [t for t in run.state_transitions if t.participant_id == participant_id]
    variables = {d.variable_id: d for d in model.state_variables}
    base = dict(participant_id=participant_id, scenario_digest=timeline.scenario_digest,
                environment_digest=environment.digest, run_id=run.run_id, run_digest=run_digest(run),
                window=window, model=model.identity)
    if not transitions:
        raise InvalidScientificProblem(f"run records no state transition for participant {participant_id!r}")
    last: StateTransitionReceipt = max(transitions, key=lambda t: t.window_index)
    if exact_seconds(last.end) != window.end.seconds:
        raise InvalidScientificProblem("participant's last recorded state is not at the end of the run window")
    prior = {v.variable_id: v for v in last.end_values}
    gathered = tuple(_gather(required[i], bound[i], environment, window) for i in sorted(required))
    missing_state = sorted(set(variables) - set(prior))
    if missing_state:
        return DegradationStepRecord(**base, prior_state_digest=last.end_state_digest, prior_values=tuple(prior.values()),
                                     inputs=gathered, status=StepStatus.UNKNOWN_STATE, resulting_values=(), uncertainty_status=(),
                                     reason=f"participant does not publish state {missing_state}; degradation cannot start from an unknown state")
    prior_values = tuple(prior[v] for v in sorted(variables))
    unknown = [g.input_id for g in gathered if g.status is not ValueStatus.KNOWN]
    if unknown:
        return DegradationStepRecord(**base, prior_state_digest=last.end_state_digest, prior_values=prior_values,
                                     inputs=gathered, status=StepStatus.UNKNOWN_INPUT, resulting_values=(), uncertainty_status=(),
                                     reason=f"inputs {unknown} are UNKNOWN; missing exposure or usage is not zero")
    values = {g.input_id: g.value.value for g in gathered}
    outside = []
    for b in model.applicability:
        if b.input_id not in values:
            raise InvalidScientificProblem(f"applicability names unknown input {b.input_id!r}")
        if not b.admits(values[b.input_id]):
            outside.append(b.input_id)
    if outside:
        return DegradationStepRecord(**base, prior_state_digest=last.end_state_digest, prior_values=prior_values,
                                     inputs=gathered, status=StepStatus.NOT_APPLICABLE, resulting_values=(), uncertainty_status=(),
                                     reason=f"inputs {outside} lie outside the model's declared applicability")

    new = dict(model.advance(values, {k: prior[k].value for k in variables}, window.duration))
    if set(new) != set(variables):
        raise InvalidScientificProblem(f"model {model.identity.model_id} returned {sorted(new)}, not its declared state {sorted(variables)}")
    components = [("model_discrepancy", model.identity.model_discrepancy.kind.value)]
    components += [(f"input:{g.input_id}", g.value.uncertainty.kind.value) for g in gathered]
    components += [(f"prior:{k}", prior[k].uncertainty.kind.value) for k in sorted(variables)]
    note = (
        "resulting-state uncertainty is not propagated by the lifecycle engine; component statuses: "
        + ", ".join(f"{a}={b}" for a, b in components)
    )
    resulting = []
    for k in sorted(variables):
        value = new[k]
        if not isinstance(value, Quantity):
            raise InvalidScientificProblem(f"model returned a non-Quantity for {k!r}")
        value.require_compatible(variables[k].unit, context=f"degraded state {k!r}")
        resulting.append(StateVariableValue(k, value, Uncertainty.unknown(note)))
    components.append(("resulting_state", UncertaintyKind.UNKNOWN.value))
    return DegradationStepRecord(**base, prior_state_digest=last.end_state_digest, prior_values=prior_values,
                                 inputs=gathered, status=StepStatus.APPLIED, resulting_values=tuple(resulting),
                                 uncertainty_status=tuple(components))


def carry_forward(
    step: DegradationStepRecord,
    run: Any,
    definitions: tuple[InitialStateDefinition, ...],
) -> dict[str, dict[str, InitialStateValue]]:
    """The next window's ``initial_state`` for the participant.

    Degraded variables come from the step; every other declared variable comes
    from the participant's own published end state.  A declared variable with
    neither is refused rather than defaulted.
    """
    if not step.applied:
        raise InvalidScientificProblem(f"step was {step.status.value}; there is no degraded state to carry forward")
    if run_digest(run) != step.run_digest:
        raise InvalidScientificProblem("carry_forward was given a different run than the step was computed from")
    last = max((t for t in run.state_transitions if t.participant_id == step.participant_id), key=lambda t: t.window_index)
    published = {v.variable_id: v for v in last.end_values}
    degraded = {v.variable_id: v for v in step.resulting_values}
    state: dict[str, InitialStateValue] = {}
    for d in definitions:
        source = degraded.get(d.variable_id) or published.get(d.variable_id)
        if source is None:
            raise InvalidScientificProblem(f"declared state {d.variable_id!r} has neither a degraded nor a published value")
        state[d.variable_id] = InitialStateValue(d.variable_id, source.value, source.uncertainty)
    return {step.participant_id: state}


# --------------------------------------------------------------------------
# Chain
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleChain:
    """The closed loop, verified: each window starts from the previous degraded state.

    Replay agreement on :attr:`digest` is reproducibility only, never validation.
    """

    participant_id: str
    steps: tuple[DegradationStepRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", _identifier(self.participant_id, "participant_id"))
        steps = tuple(self.steps)
        if not steps or any(not isinstance(s, DegradationStepRecord) for s in steps):
            raise InvalidScientificProblem("lifecycle chain requires DegradationStepRecord entries")
        first = steps[0]
        for s in steps:
            if s.participant_id != self.participant_id:
                raise InvalidScientificProblem("lifecycle chain mixes participants")
            if (s.scenario_digest, s.environment_digest) != (first.scenario_digest, first.environment_digest):
                raise InvalidScientificProblem("lifecycle chain mixes scenarios or environments")
        for a, b in zip(steps, steps[1:]):
            if not a.applied:
                raise InvalidScientificProblem(f"window after a {a.status.value} step has no degraded state to start from")
            if a.window.end != b.window.start:
                raise InvalidScientificProblem("lifecycle windows must be contiguous")
        object.__setattr__(self, "steps", steps)

    def verify(self, runs: tuple[Any, ...]) -> None:
        """Check each run against its step and that run k+1 started from step k's state."""
        if len(runs) != len(self.steps):
            raise InvalidScientificProblem("verify needs exactly one run per step")
        for step, run in zip(self.steps, runs):
            if run_digest(run) != step.run_digest:
                raise InvalidScientificProblem(f"run {run.run_id!r} is not the run step was computed from")
        for step, following in zip(self.steps, runs[1:]):
            receipts = [r for r in following.initial_state_receipts if r.participant_id == self.participant_id]
            if len(receipts) != 1:
                raise InvalidScientificProblem(f"run {following.run_id!r} did not acknowledge an initial state")
            acknowledged = {v.variable_id: v.value for v in receipts[0].values}
            if exact_seconds(receipts[0].instant) != step.window.end.seconds:
                raise InvalidScientificProblem("next window's initial state is not at the degraded instant")
            for v in step.resulting_values:
                got = acknowledged.get(v.variable_id)
                if got is None or got.magnitude_in(v.value.units) != v.value.magnitude:
                    raise InvalidScientificProblem(
                        f"run {following.run_id!r} did not start from the degraded {v.variable_id!r}"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CHAIN_SCHEMA, "classification": "degradation_model_output_not_evidence", "participant_id": self.participant_id, "steps": [s.to_dict() for s in self.steps]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "LifecycleChain":
        require_schema(p, CHAIN_SCHEMA)
        _strict_keys(p, {"schema", "classification", "participant_id", "steps"}, "lifecycle chain")
        if p["classification"] != "degradation_model_output_not_evidence":
            raise InvalidScientificProblem("lifecycle chain classification mismatch")
        return cls(p["participant_id"], tuple(DegradationStepRecord.from_dict(s) for s in p["steps"]))


def run_lifecycle(
    *,
    model: DegradationModel,
    environment: EnvironmentTimeline,
    participant_id: str,
    definitions: tuple[InitialStateDefinition, ...],
    initial_state: Mapping[str, Mapping[str, InitialStateValue]],
    windows: tuple[TimeWindow, ...],
    execute: Callable[[str, TimeWindow, Mapping[str, Mapping[str, InitialStateValue]]], Any],
    bindings: tuple[InputBinding, ...],
) -> tuple[LifecycleChain, tuple[Any, ...]]:
    """Closed loop: physics -> degradation -> state -> physics ... over ``windows``.

    ``execute(run_id, window, initial_state)`` runs the physics for one window
    and returns its ``MultiphysicsRunRecord``.  The loop stops (and the chain
    ends) at the first step that is not APPLIED: UNKNOWN or NOT_APPLICABLE
    degradation is never replaced by "no degradation".
    """
    steps: list[DegradationStepRecord] = []
    runs: list[Any] = []
    state = initial_state
    for index, window in enumerate(windows):
        run = execute(f"{participant_id}-window-{index}", window, state)
        runs.append(run)
        step = evaluate_degradation(model, environment=environment, run=run, participant_id=participant_id, bindings=bindings)
        steps.append(step)
        if not step.applied:
            break
        state = carry_forward(step, run, definitions)
    chain = LifecycleChain(participant_id, tuple(steps))
    chain.verify(tuple(runs))
    return chain, tuple(runs)
