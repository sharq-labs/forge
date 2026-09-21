"""Executable participant contract for the multiphysics runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import (
    CheckpointRecord, InitialStateDefinition, InitialStateReceipt,
    InitialStateValue, ParticipantSpec,
)
from ...scientific.multiphysics.value import (
    CouplingValue,
    validate_port_coupling_value,
    validate_port_uncertainty,
)
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity, dimensionality


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
        checkpoint: Callable[[Quantity], RuntimeCheckpoint] | None = None,
        restore: Callable[[RuntimeCheckpoint], None] | None = None,
        finalize: Callable[[], None] | None = None,
    ) -> None:
        self._spec = spec
        self._initialize = initialize
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
