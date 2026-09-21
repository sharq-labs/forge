"""Executable participant contract for the multiphysics runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import (
    CheckpointRecord, InitialStateDefinition, InitialStateReceipt,
    InitialStateValue, ParticipantSpec, StateVariableValue,
)
from ...scientific.multiphysics.receipts import require_digest
from ...scientific.multiphysics.value import (
    CouplingValue,
    validate_port_coupling_value,
    validate_port_uncertainty,
)
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity, dimensionality, normalize_unit


@dataclass(frozen=True)
class ParticipantEvent:
    event_id: str
    instant: Quantity
    terminal: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        if not str(self.event_id).strip():
            raise InvalidScientificProblem("participant event requires event_id")
        if not isinstance(self.instant, Quantity) or dimensionality(self.instant.units) != dimensionality("second"):
            raise InvalidScientificProblem("participant event instant must be time")
        if not isinstance(self.terminal, bool):
            raise InvalidScientificProblem("participant event terminal must be boolean")
        object.__setattr__(self, "instant", self.instant.to("second"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "instant": self.instant.to_dict(),
            "terminal": self.terminal,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class InitializationResult:
    outputs: Mapping[str, CouplingValue]
    uncertainty: Mapping[str, Uncertainty]
    diagnostics: Mapping[str, Any] | None = None
    initial_state_receipt: InitialStateReceipt | None = None


@dataclass(frozen=True)
class AdvanceRequest:
    start: Quantity
    end: Quantity
    inputs: Mapping[str, CouplingValue]
    input_uncertainty: Mapping[str, Uncertainty]
    maximum_step: Quantity | None = None

    def __post_init__(self) -> None:
        for label in ("start", "end"):
            value = getattr(self, label)
            if not isinstance(value, Quantity) or dimensionality(value.units) != dimensionality("second"):
                raise InvalidScientificProblem(f"advance {label} must be time")
        if self.end.magnitude_in("second") <= self.start.magnitude_in("second"):
            raise InvalidScientificProblem("advance end must be after start")
        if self.maximum_step is not None:
            if dimensionality(self.maximum_step.units) != dimensionality("second"):
                raise InvalidScientificProblem("maximum_step must be time")
            if self.maximum_step.magnitude_in("second") <= 0.0:
                raise InvalidScientificProblem("maximum_step must be positive")


@dataclass(frozen=True)
class AdvanceResult:
    end: Quantity
    outputs: Mapping[str, CouplingValue]
    uncertainty: Mapping[str, Uncertainty]
    substeps: int
    internal_converged: bool
    max_internal_step: Quantity | None = None
    events: tuple[ParticipantEvent, ...] = ()
    diagnostics: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.end, Quantity) or dimensionality(self.end.units) != dimensionality("second"):
            raise InvalidScientificProblem("advance result end must be time")
        if isinstance(self.substeps, bool) or not isinstance(self.substeps, int) or self.substeps < 0:
            raise InvalidScientificProblem("advance result substeps must be non-negative int")
        if not isinstance(self.internal_converged, bool):
            raise InvalidScientificProblem("internal_converged must be boolean")
        if self.max_internal_step is not None:
            if dimensionality(self.max_internal_step.units) != dimensionality("second"):
                raise InvalidScientificProblem("max_internal_step must be time")
            if self.max_internal_step.magnitude_in("second") < 0.0:
                raise InvalidScientificProblem("max_internal_step must be non-negative")
        if any(not isinstance(e, ParticipantEvent) for e in self.events):
            raise InvalidScientificProblem("events must be ParticipantEvent records")


@dataclass(frozen=True, order=True)
class OperatingConditionDefinition:
    """An operating condition a participant declares that it consumes.

    Core transports declared, unit-bearing operating conditions; it never
    decides what one means.  A participant that does not declare a condition
    does not receive it, and a scenario condition nobody declares is refused
    rather than quietly dropped.
    """

    condition_id: str
    unit: str

    def __post_init__(self) -> None:
        condition_id = str(self.condition_id).strip()
        if not condition_id:
            raise InvalidScientificProblem(
                "operating condition definition requires condition_id"
            )
        object.__setattr__(self, "condition_id", condition_id)
        object.__setattr__(self, "unit", normalize_unit(self.unit))


@dataclass(frozen=True, order=True)
class OperatingConditionValue:
    condition_id: str
    value: Quantity
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        condition_id = str(self.condition_id).strip()
        if not condition_id or not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "operating condition value requires condition_id and a Quantity"
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "operating condition value requires an Uncertainty record"
            )
        for label in ("standard_uncertainty", "lower", "upper"):
            bound = getattr(self.uncertainty, label)
            if bound is not None:
                bound.require_compatible(
                    self.value.units,
                    context=f"operating condition {condition_id!r} {label}",
                )
        object.__setattr__(self, "condition_id", condition_id)


@dataclass(frozen=True, order=True)
class ParameterDefinition:
    """A participant parameter a topology ParameterBinding may bind to."""

    target_path: str
    unit: str

    def __post_init__(self) -> None:
        target = str(self.target_path).strip()
        if not target:
            raise InvalidScientificProblem("parameter definition requires target_path")
        object.__setattr__(self, "target_path", target)
        object.__setattr__(self, "unit", normalize_unit(self.unit))


@dataclass(frozen=True, order=True)
class ParameterValue:
    target_path: str
    value: Quantity

    def __post_init__(self) -> None:
        target = str(self.target_path).strip()
        if not target or not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "parameter value requires target_path and a Quantity"
            )
        object.__setattr__(self, "target_path", target)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    record: CheckpointRecord
    token: Any


@runtime_checkable
class ExecutableParticipant(Protocol):
    @property
    def spec(self) -> ParticipantSpec: ...

    def initialize(
        self,
        instant: Quantity,
        external_inputs: Mapping[str, CouplingValue],
        external_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult: ...

    def advance(self, request: AdvanceRequest) -> AdvanceResult: ...

    def checkpoint(self, instant: Quantity) -> RuntimeCheckpoint: ...

    def restore(self, checkpoint: RuntimeCheckpoint) -> None: ...

    def finalize(self) -> None: ...


# =====================================================================
# Declared optional capabilities.
#
# Support is DECLARED, never inferred. Each helper below asks a participant
# what it accepts and refuses to route anything it did not declare; a
# participant that declares nothing simply receives nothing, which is a
# different statement from "the runtime assumed it could cope".
# =====================================================================

def operating_condition_definitions(
    participant: "ExecutableParticipant",
) -> tuple[OperatingConditionDefinition, ...]:
    declared = tuple(getattr(participant, "operating_condition_definitions", ()) or ())
    if any(not isinstance(item, OperatingConditionDefinition) for item in declared):
        raise InvalidScientificProblem(
            f"participant {participant.spec.participant_id!r} declares operating "
            f"conditions that are not OperatingConditionDefinition records"
        )
    return tuple(sorted(declared))


def apply_operating_conditions(
    participant: "ExecutableParticipant",
    instant: Quantity,
    values: Mapping[str, OperatingConditionValue],
) -> tuple[OperatingConditionValue, ...]:
    """Deliver declared operating conditions and take the acknowledgement back."""
    declared = {item.condition_id: item for item in operating_condition_definitions(participant)}
    participant_id = participant.spec.participant_id
    if not declared and not values:
        return ()
    if set(values) != set(declared):
        raise InvalidScientificProblem(
            f"participant {participant_id!r} operating conditions do not exactly "
            f"cover its declaration; missing={sorted(set(declared) - set(values))}, "
            f"unknown={sorted(set(values) - set(declared))}"
        )
    for key, item in values.items():
        if not isinstance(item, OperatingConditionValue):
            raise InvalidScientificProblem(
                "operating conditions must be OperatingConditionValue records"
            )
        item.value.require_compatible(
            declared[key].unit,
            context=f"operating condition {key!r} for {participant_id!r}",
        )
    apply = getattr(participant, "apply_operating_conditions", None)
    if apply is None:
        raise InvalidScientificProblem(
            f"participant {participant_id!r} declares operating conditions but "
            f"exposes no way to consume them"
        )
    acknowledged = tuple(apply(instant, dict(values)))
    if acknowledged != tuple(sorted(values.values())):
        raise InvalidScientificProblem(
            f"participant {participant_id!r} did not acknowledge the exact "
            f"operating conditions and uncertainty it was given"
        )
    return acknowledged


def parameter_definitions(
    participant: "ExecutableParticipant",
) -> tuple[ParameterDefinition, ...]:
    declared = tuple(getattr(participant, "parameter_definitions", ()) or ())
    if any(not isinstance(item, ParameterDefinition) for item in declared):
        raise InvalidScientificProblem(
            f"participant {participant.spec.participant_id!r} declares parameters "
            f"that are not ParameterDefinition records"
        )
    return tuple(sorted(declared))


def apply_parameters(
    participant: "ExecutableParticipant",
    values: Mapping[str, ParameterValue],
) -> tuple[ParameterValue, ...]:
    """Bind topology-declared parameters onto a participant that accepts them."""
    declared = {item.target_path: item for item in parameter_definitions(participant)}
    participant_id = participant.spec.participant_id
    if not values:
        return ()
    unknown = sorted(set(values) - set(declared))
    if unknown:
        raise InvalidScientificProblem(
            f"participant {participant_id!r} does not accept parameter bindings "
            f"for {unknown}"
        )
    for key, item in values.items():
        if not isinstance(item, ParameterValue):
            raise InvalidScientificProblem(
                "parameter bindings must be ParameterValue records"
            )
        item.value.require_compatible(
            declared[key].unit,
            context=f"parameter {key!r} for {participant_id!r}",
        )
    apply = getattr(participant, "apply_parameters", None)
    if apply is None:
        raise InvalidScientificProblem(
            f"participant {participant_id!r} declares parameters but exposes no "
            f"way to bind them"
        )
    acknowledged = tuple(apply(dict(values)))
    if acknowledged != tuple(sorted(values.values())):
        raise InvalidScientificProblem(
            f"participant {participant_id!r} did not acknowledge the exact "
            f"parameter values it was bound to"
        )
    return acknowledged


def state_identity(
    participant: "ExecutableParticipant", instant: Quantity
) -> str | None:
    """The participant's own digest of its state, or ``None`` if it exposes none.

    Two ways a participant can answer, and no third: an explicit
    ``state_identity`` callback, or the ``state_digest`` of the checkpoint it
    already declares itself able to take.  A participant that does neither gets
    no state-transition receipt, because the alternative is inventing one.
    """
    explicit = getattr(participant, "state_identity", None)
    if explicit is not None:
        declared = explicit(instant)
        if declared is not None:
            return require_digest(
                declared,
                f"participant {participant.spec.participant_id!r} state identity",
            )
    if participant.spec.checkpointable:
        return participant.checkpoint(instant).record.state_digest
    return None


def public_state(
    participant: "ExecutableParticipant", instant: Quantity
) -> tuple[StateVariableValue, ...]:
    """State values a participant publishes. Private solver internals stay private."""
    expose = getattr(participant, "public_state", None)
    if expose is None:
        return ()
    values = tuple(expose(instant))
    if any(not isinstance(item, StateVariableValue) for item in values):
        raise InvalidScientificProblem(
            f"participant {participant.spec.participant_id!r} public state must be "
            f"StateVariableValue records"
        )
    return tuple(sorted(values))


def validate_port_value(
    spec: ParticipantSpec,
    port_id: str,
    value: CouplingValue,
    *,
    output: bool,
) -> None:
    port = spec.port(port_id)
    wanted = "output" if output else "input"
    if port.direction.value != wanted:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} port {port_id!r} is "
            f"{port.direction.value}, not {wanted}"
        )
    validate_port_coupling_value(port, value)


def validate_uncertainty(
    spec: ParticipantSpec,
    port_id: str,
    uncertainty: Uncertainty,
    *,
    output: bool,
) -> None:
    port = spec.port(port_id)
    wanted = "output" if output else "input"
    if port.direction.value != wanted:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} port {port_id!r} is "
            f"{port.direction.value}, not {wanted}"
        )
    validate_port_uncertainty(port, uncertainty)

def validate_inputs(
    spec: ParticipantSpec,
    inputs: Mapping[str, CouplingValue],
    uncertainty: Mapping[str, Uncertainty],
) -> None:
    if set(inputs) != set(uncertainty):
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} input uncertainty keys must "
            f"exactly match input values"
        )
    for port_id, value in inputs.items():
        validate_port_value(spec, port_id, value, output=False)
        validate_uncertainty(spec, port_id, uncertainty[port_id], output=False)


def validate_outputs(
    spec: ParticipantSpec,
    outputs: Mapping[str, CouplingValue],
    uncertainty: Mapping[str, Uncertainty],
) -> None:
    declared = {p.port_id for p in spec.outputs}
    unknown = sorted(set(outputs) - declared)
    missing = sorted(declared - set(outputs))
    if unknown or missing:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} outputs mismatch; "
            f"missing={missing}, unknown={unknown}"
        )
    if set(uncertainty) != declared:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} must state uncertainty for "
            f"every output; missing={sorted(declared-set(uncertainty))}, "
            f"unknown={sorted(set(uncertainty)-declared)}"
        )
    for port_id, value in outputs.items():
        validate_port_value(spec, port_id, value, output=True)
        validate_uncertainty(spec, port_id, uncertainty[port_id], output=True)


class CallbackParticipant:
    """Full participant adapter for native functions or external-solver wrappers.

    The callbacks own solver-specific state. The runtime owns orchestration,
    rollback requirements, typed coupling, convergence and records.
    """

    def __init__(
        self,
        spec: ParticipantSpec,
        *,
        initialize: Callable[
            [Quantity, Mapping[str, CouplingValue], Mapping[str, Uncertainty]],
            InitializationResult,
        ],
        initial_state_definitions: tuple[InitialStateDefinition, ...] = (),
        initialize_state: Callable[
            [Quantity, Mapping[str, InitialStateValue], Mapping[str, CouplingValue], Mapping[str, Uncertainty]],
            InitializationResult,
        ] | None = None,
        advance: Callable[[AdvanceRequest], AdvanceResult],
        operating_condition_definitions: tuple[OperatingConditionDefinition, ...] = (),
        apply_operating_conditions: Callable[
            [Quantity, Mapping[str, OperatingConditionValue]],
            tuple[OperatingConditionValue, ...],
        ] | None = None,
        parameter_definitions: tuple[ParameterDefinition, ...] = (),
        apply_parameters: Callable[
            [Mapping[str, ParameterValue]], tuple[ParameterValue, ...]
        ] | None = None,
        state_identity: Callable[[Quantity], str] | None = None,
        public_state: Callable[[Quantity], tuple[StateVariableValue, ...]] | None = None,
        checkpoint: Callable[[Quantity], RuntimeCheckpoint] | None = None,
        restore: Callable[[RuntimeCheckpoint], None] | None = None,
        finalize: Callable[[], None] | None = None,
    ) -> None:
        self._spec = spec
        self._initialize = initialize
        conditions = tuple(operating_condition_definitions)
        if any(
            not isinstance(item, OperatingConditionDefinition) for item in conditions
        ) or len({item.condition_id for item in conditions}) != len(conditions):
            raise InvalidScientificProblem(
                "operating condition definitions must be unique typed records"
            )
        if bool(conditions) != (apply_operating_conditions is not None):
            raise InvalidScientificProblem(
                "operating condition definitions and their consumer must be "
                "declared together"
            )
        self._operating_condition_definitions = tuple(sorted(conditions))
        self._apply_operating_conditions = apply_operating_conditions
        parameters = tuple(parameter_definitions)
        if any(
            not isinstance(item, ParameterDefinition) for item in parameters
        ) or len({item.target_path for item in parameters}) != len(parameters):
            raise InvalidScientificProblem(
                "parameter definitions must be unique typed records"
            )
        if bool(parameters) != (apply_parameters is not None):
            raise InvalidScientificProblem(
                "parameter definitions and their binder must be declared together"
            )
        self._parameter_definitions = tuple(sorted(parameters))
        self._apply_parameters = apply_parameters
        self._state_identity = state_identity
        self._public_state = public_state
        definitions = tuple(initial_state_definitions)
        if any(not isinstance(item, InitialStateDefinition) for item in definitions) or len({item.variable_id for item in definitions}) != len(definitions):
            raise InvalidScientificProblem("initial state definitions must be unique typed records")
        if bool(definitions) != (initialize_state is not None):
            raise InvalidScientificProblem("state definitions and state initializer must be declared together")
        self._initial_state_definitions = tuple(sorted(definitions))
        self._initialize_state = initialize_state
        self._advance = advance
        self._checkpoint = checkpoint
        self._restore = restore
        self._finalize = finalize or (lambda: None)
        if spec.checkpointable and (checkpoint is None or restore is None):
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} declares checkpointable but adapter lacks checkpoint/restore"
            )
        if not spec.checkpointable and (checkpoint is not None or restore is not None):
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} adapter exposes checkpointing not declared by its spec"
            )

    @property
    def spec(self) -> ParticipantSpec:
        return self._spec

    def initialize(
        self,
        instant: Quantity,
        external_inputs: Mapping[str, CouplingValue],
        external_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult:
        validate_inputs(self.spec, external_inputs, external_uncertainty)
        result = self._initialize(instant, external_inputs, external_uncertainty)
        if not isinstance(result, InitializationResult):
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} initialize returned "
                f"{type(result).__name__}, expected InitializationResult"
            )
        if result.initial_state_receipt is not None:
            raise InvalidScientificProblem(
                "ordinary initialization must not return an initial-state receipt"
            )
        validate_outputs(self.spec, result.outputs, result.uncertainty)
        return result

    @property
    def initial_state_definitions(self) -> tuple[InitialStateDefinition, ...]:
        return self._initial_state_definitions

    @property
    def operating_condition_definitions(
        self,
    ) -> tuple[OperatingConditionDefinition, ...]:
        return self._operating_condition_definitions

    @property
    def parameter_definitions(self) -> tuple[ParameterDefinition, ...]:
        return self._parameter_definitions

    def apply_operating_conditions(
        self, instant: Quantity, values: Mapping[str, OperatingConditionValue]
    ) -> tuple[OperatingConditionValue, ...]:
        if self._apply_operating_conditions is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} does not consume "
                f"operating conditions"
            )
        return tuple(self._apply_operating_conditions(instant, dict(values)))

    def apply_parameters(
        self, values: Mapping[str, ParameterValue]
    ) -> tuple[ParameterValue, ...]:
        if self._apply_parameters is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} does not accept "
                f"parameter bindings"
            )
        return tuple(self._apply_parameters(dict(values)))

    def state_identity(self, instant: Quantity) -> str | None:
        """This adapter's declared state digest, or ``None`` if it declares none."""
        if self._state_identity is None:
            return None
        return self._state_identity(instant)

    def public_state(self, instant: Quantity) -> tuple[StateVariableValue, ...]:
        if self._public_state is None:
            return ()
        return tuple(self._public_state(instant))

    def initialize_state(
        self, instant: Quantity, state: Mapping[str, InitialStateValue],
        external_inputs: Mapping[str, CouplingValue],
        external_uncertainty: Mapping[str, Uncertainty],
    ) -> InitializationResult:
        if self._initialize_state is None:
            raise InvalidScientificProblem(f"participant {self.spec.participant_id!r} does not accept explicit initial state")
        expected = {item.variable_id: item for item in self._initial_state_definitions}
        if set(state) != set(expected):
            raise InvalidScientificProblem("initial state does not exactly cover participant state schema")
        for key, item in state.items():
            if not isinstance(item, InitialStateValue):
                raise InvalidScientificProblem("initial state must contain InitialStateValue records")
            item.value.require_compatible(expected[key].unit, context=f"initial state {key!r}")
        validate_inputs(self.spec, external_inputs, external_uncertainty)
        result = self._initialize_state(instant, state, external_inputs, external_uncertainty)
        if not isinstance(result, InitializationResult) or not isinstance(result.initial_state_receipt, InitialStateReceipt):
            raise InvalidScientificProblem("state initializer must return InitializationResult with InitialStateReceipt")
        receipt = result.initial_state_receipt
        if receipt.participant_id != self.spec.participant_id or receipt.instant != instant.to("second"):
            raise InvalidScientificProblem("initial state receipt participant or instant mismatch")
        requested = tuple(sorted(state.values()))
        if receipt.values != requested:
            raise InvalidScientificProblem("initial state receipt does not acknowledge exact requested values and uncertainty")
        validate_outputs(self.spec, result.outputs, result.uncertainty)
        return result

    def advance(self, request: AdvanceRequest) -> AdvanceResult:
        validate_inputs(self.spec, request.inputs, request.input_uncertainty)
        result = self._advance(request)
        if not isinstance(result, AdvanceResult):
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} advance returned {type(result).__name__}"
            )
        validate_outputs(self.spec, result.outputs, result.uncertainty)
        if result.max_internal_step is not None and request.maximum_step is not None:
            if result.max_internal_step.magnitude_in("second") > request.maximum_step.magnitude_in("second") * (1.0 + 1e-12):
                raise InvalidScientificProblem(
                    f"participant {self.spec.participant_id!r} exceeded requested maximum step: "
                    f"{result.max_internal_step} > {request.maximum_step}"
                )
        return result

    def checkpoint(self, instant: Quantity) -> RuntimeCheckpoint:
        if self._checkpoint is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        checkpoint = self._checkpoint(instant)
        if checkpoint.record.participant_id != self.spec.participant_id:
            raise InvalidScientificProblem("checkpoint belongs to a different participant")
        return checkpoint

    def restore(self, checkpoint: RuntimeCheckpoint) -> None:
        if self._restore is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        if checkpoint.record.participant_id != self.spec.participant_id:
            raise InvalidScientificProblem("cannot restore another participant's checkpoint")
        self._restore(checkpoint)

    def finalize(self) -> None:
        self._finalize()
