"""Executable participant contract for the multiphysics runtime.

Participants own domain physics and solver-specific state. The runtime owns
global scheduling, coupling, rollback, transfers and scientific records.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields.result import FieldRecord
from ...scientific.multiphysics import CheckpointRecord, ParticipantSpec, PortKind
from ...scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ...scientific.units.quantity import Quantity, dimensionality

CouplingValue = Quantity | FieldRecord
_TIME_DIMENSION = dimensionality("second")
_TIME_RTOL = 1e-12


@dataclass(frozen=True)
class ParticipantEvent:
    event_id: str
    instant: Quantity
    terminal: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        event_id = str(self.event_id).strip()
        if not event_id:
            raise InvalidScientificProblem("participant event requires event_id")
        if not isinstance(self.instant, Quantity) or self.instant.dimensionality != _TIME_DIMENSION:
            raise InvalidScientificProblem("participant event instant must be time")
        if not isinstance(self.terminal, bool):
            raise InvalidScientificProblem("participant event terminal must be boolean")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "instant", self.instant.to("second"))
        object.__setattr__(self, "detail", str(self.detail).strip())

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
            if not isinstance(value, Quantity) or value.dimensionality != _TIME_DIMENSION:
                raise InvalidScientificProblem(f"advance {label} must be time")
        start = self.start.to("second")
        end = self.end.to("second")
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem("advance end must be after start")
        maximum = self.maximum_step
        if maximum is not None:
            if not isinstance(maximum, Quantity) or maximum.dimensionality != _TIME_DIMENSION or maximum.magnitude_in("second") <= 0.0:
                raise InvalidScientificProblem("maximum_step must be a positive time Quantity")
            maximum = maximum.to("second")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "maximum_step", maximum)


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
        if not isinstance(self.end, Quantity) or self.end.dimensionality != _TIME_DIMENSION:
            raise InvalidScientificProblem("advance result end must be time")
        if isinstance(self.substeps, bool) or not isinstance(self.substeps, int) or self.substeps < 0:
            raise InvalidScientificProblem("advance result substeps must be a non-negative int")
        if not isinstance(self.internal_converged, bool):
            raise InvalidScientificProblem("internal_converged must be boolean")
        maximum = self.max_internal_step
        if maximum is not None:
            if not isinstance(maximum, Quantity) or maximum.dimensionality != _TIME_DIMENSION or maximum.magnitude_in("second") < 0.0:
                raise InvalidScientificProblem("max_internal_step must be a non-negative time Quantity")
            maximum = maximum.to("second")
        events = tuple(self.events)
        if any(not isinstance(event, ParticipantEvent) for event in events):
            raise InvalidScientificProblem("advance result events must be ParticipantEvent records")
        if self.diagnostics is not None and not isinstance(self.diagnostics, Mapping):
            raise InvalidScientificProblem("advance diagnostics must be a mapping")
        object.__setattr__(self, "end", self.end.to("second"))
        object.__setattr__(self, "max_internal_step", maximum)
        object.__setattr__(self, "events", events)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    record: CheckpointRecord
    token: Any

    def __post_init__(self) -> None:
        if not isinstance(self.record, CheckpointRecord):
            raise InvalidScientificProblem("runtime checkpoint requires CheckpointRecord")


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
            f"participant {spec.participant_id!r} port {port_id!r} is {port.direction.value}, not {wanted}"
        )
    if port.kind is PortKind.SCALAR:
        if not isinstance(value, Quantity):
            raise InvalidScientificProblem(
                f"{spec.participant_id}.{port_id} expects Quantity, got {type(value).__name__}"
            )
        if value.dimensionality != port.dimension:
            raise InvalidScientificProblem(
                f"{spec.participant_id}.{port_id} expects [{port.dimension}], got [{value.dimensionality}]"
            )
        return
    if not isinstance(value, FieldRecord):
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} expects FieldRecord, got {type(value).__name__}"
        )
    assert port.field is not None
    if value.definition.components != port.field.components:
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} expects {port.field.components} field components, got {value.definition.components}"
        )
    if dimensionality(value.definition.unit) != port.dimension:
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} field dimension mismatch"
        )


def validate_uncertainty(
    spec: ParticipantSpec,
    port_id: str,
    uncertainty: Uncertainty,
    *,
    output: bool,
) -> None:
    if not isinstance(uncertainty, Uncertainty):
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} uncertainty must be Uncertainty"
        )
    port = spec.port(port_id)
    wanted = "output" if output else "input"
    if port.direction.value != wanted:
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} is not an {wanted} port"
        )
    if port.kind is PortKind.FIELD:
        if uncertainty.kind is not UncertaintyKind.UNKNOWN:
            raise InvalidScientificProblem(
                f"{spec.participant_id}.{port_id} is spatial field data; the current core has no spatial uncertainty-field record"
            )
        return
    if uncertainty.kind is UncertaintyKind.STANDARD:
        spread = uncertainty.standard_uncertainty
        assert spread is not None
        if spread.dimensionality != port.dimension:
            raise InvalidScientificProblem(
                f"{spec.participant_id}.{port_id} uncertainty dimension mismatch"
            )
    elif uncertainty.kind is UncertaintyKind.INTERVAL:
        assert uncertainty.lower is not None and uncertainty.upper is not None
        if uncertainty.lower.dimensionality != port.dimension or uncertainty.upper.dimensionality != port.dimension:
            raise InvalidScientificProblem(
                f"{spec.participant_id}.{port_id} interval dimension mismatch"
            )
    if uncertainty.is_quantified and not str(uncertainty.source).strip():
        raise InvalidScientificProblem(
            f"{spec.participant_id}.{port_id} quantified uncertainty has no source attribution"
        )


def validate_inputs(
    spec: ParticipantSpec,
    inputs: Mapping[str, CouplingValue],
    uncertainty: Mapping[str, Uncertainty],
) -> None:
    declared = {port.port_id for port in spec.inputs}
    if set(inputs) != declared:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} input keys mismatch; "
            f"missing={sorted(declared-set(inputs))}, unknown={sorted(set(inputs)-declared)}"
        )
    if set(uncertainty) != declared:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} must state uncertainty for every input"
        )
    for port_id, value in inputs.items():
        validate_port_value(spec, port_id, value, output=False)
        validate_uncertainty(spec, port_id, uncertainty[port_id], output=False)


def validate_outputs(
    spec: ParticipantSpec,
    outputs: Mapping[str, CouplingValue],
    uncertainty: Mapping[str, Uncertainty],
) -> None:
    declared = {port.port_id for port in spec.outputs}
    if set(outputs) != declared:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} outputs mismatch; "
            f"missing={sorted(declared-set(outputs))}, unknown={sorted(set(outputs)-declared)}"
        )
    if set(uncertainty) != declared:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} must state uncertainty for every output"
        )
    for port_id, value in outputs.items():
        validate_port_value(spec, port_id, value, output=True)
        validate_uncertainty(spec, port_id, uncertainty[port_id], output=True)


def validate_advance_result(
    spec: ParticipantSpec,
    request: AdvanceRequest,
    result: AdvanceResult,
) -> None:
    if not isinstance(result, AdvanceResult):
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} returned {type(result).__name__}, expected AdvanceResult"
        )
    validate_outputs(spec, result.outputs, result.uncertainty)
    start = request.start.magnitude_in("second")
    requested_end = request.end.magnitude_in("second")
    actual_end = result.end.magnitude_in("second")
    scale = max(1.0, abs(start), abs(requested_end), abs(actual_end))
    tolerance = _TIME_RTOL * scale
    if actual_end < start - tolerance or actual_end > requested_end + tolerance:
        raise InvalidScientificProblem(
            f"participant {spec.participant_id!r} ended at {actual_end:g}s outside requested [{start:g}, {requested_end:g}]s"
        )
    for event in result.events:
        instant = event.instant.magnitude_in("second")
        if instant < start - tolerance or instant > actual_end + tolerance:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} reported event {event.event_id!r} outside executed interval"
            )
    duration = max(0.0, actual_end - start)
    if spec.transient and duration > tolerance and result.substeps < 1:
        raise InvalidScientificProblem(
            f"transient participant {spec.participant_id!r} advanced time but reports zero local substeps"
        )
    if not spec.transient and result.max_internal_step is not None:
        raise InvalidScientificProblem(
            f"steady participant {spec.participant_id!r} reports a local time step"
        )
    if spec.transient and request.maximum_step is not None and duration > tolerance:
        limit = request.maximum_step.magnitude_in("second")
        if result.max_internal_step is None:
            raise InvalidScientificProblem(
                f"transient participant {spec.participant_id!r} was constrained to dt <= {limit:g}s but did not report max_internal_step"
            )
        observed = result.max_internal_step.magnitude_in("second")
        if observed > limit + _TIME_RTOL * max(1.0, abs(limit)):
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} used local dt {observed:g}s > requested {limit:g}s"
            )
        required = max(1, math.ceil((duration - tolerance) / limit))
        if result.substeps < required:
            raise InvalidScientificProblem(
                f"participant {spec.participant_id!r} reports {result.substeps} substeps; at least {required} are required"
            )


class CallbackParticipant:
    """Native callback adapter retaining the complete participant lifecycle."""

    def __init__(
        self,
        spec: ParticipantSpec,
        *,
        initialize: Callable[
            [Quantity, Mapping[str, CouplingValue], Mapping[str, Uncertainty]],
            InitializationResult,
        ],
        advance: Callable[[AdvanceRequest], AdvanceResult],
        checkpoint: Callable[[Quantity], RuntimeCheckpoint] | None = None,
        restore: Callable[[RuntimeCheckpoint], None] | None = None,
        finalize: Callable[[], None] | None = None,
    ) -> None:
        self._spec = spec
        self._initialize = initialize
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
                f"participant {spec.participant_id!r} exposes undeclared checkpointing"
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
                f"participant {self.spec.participant_id!r} initialize returned {type(result).__name__}"
            )
        validate_outputs(self.spec, result.outputs, result.uncertainty)
        return result

    def advance(self, request: AdvanceRequest) -> AdvanceResult:
        validate_inputs(self.spec, request.inputs, request.input_uncertainty)
        result = self._advance(request)
        validate_advance_result(self.spec, request, result)
        return result

    def checkpoint(self, instant: Quantity) -> RuntimeCheckpoint:
        if self._checkpoint is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        checkpoint = self._checkpoint(instant)
        if checkpoint.record.participant_id != self.spec.participant_id:
            raise InvalidScientificProblem("checkpoint belongs to another participant")
        return checkpoint

    def restore(self, checkpoint: RuntimeCheckpoint) -> None:
        if self._restore is None:
            raise InvalidScientificProblem(
                f"participant {self.spec.participant_id!r} is not checkpointable"
            )
        if checkpoint.record.participant_id != self.spec.participant_id:
            raise InvalidScientificProblem("cannot restore another participant checkpoint")
        self._restore(checkpoint)

    def finalize(self) -> None:
        self._finalize()
