"""Auditable run records for the generic multiphysics coupling runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..fields import FieldRecord
from ..results.immutable import freeze
from ..results.uncertainty import Uncertainty
from ..serialization import require_schema, require_schema_any, schema_string
from ..units.quantity import Quantity, dimensionality
from .graph import PhysicsGraph
from .plan import CouplingPlan
from .receipts import (
    OperatingConditionReceipt,
    QuantityOfInterestRecord,
    ScenarioInputReceipt,
    StateTransitionReceipt,
    TerminationReceipt,
)
from .state import InitialStateReceipt, ReachedScheduledEvent, ScheduledEventRecord
from .ports import PortDirection, PortRef
from .value import (
    CouplingValue,
    coupling_value_from_dict,
    coupling_value_to_dict,
    validate_port_coupling_value,
    validate_port_uncertainty,
)

EDGE_RESIDUAL_SCHEMA = schema_string("multiphysics_edge_residual")
PARTICIPANT_STEP_SCHEMA = schema_string("multiphysics_participant_step")
ITERATION_SCHEMA = schema_string("multiphysics_iteration")
WINDOW_SCHEMA = schema_string("multiphysics_window")
EXTERNAL_INPUT_SCHEMA = schema_string("multiphysics_external_input")
INITIAL_COUPLING_SCHEMA = schema_string("multiphysics_initial_coupling")
RUN_SCHEMA_V1 = schema_string("multiphysics_run")
RUN_SCHEMA_V2 = schema_string("multiphysics_run", 2)
#: V3 adds the typed scenario evidence the World Runtime round made executable:
#: consumed scenario inputs, delivered operating conditions, participant state
#: transitions, the condition that stopped a run and the requested quantities of
#: interest.  V2 records read back with those tuples empty, which is what they
#: meant: that runtime produced none of them.  What V3 does NOT do is admit a V2
#: record that stored consumed inputs in `final_outputs` -- see
#: `_LEGACY_INPUT_KEY` below.
RUN_SCHEMA = schema_string("multiphysics_run", 3)

#: Consumed time-varying inputs once lived here, in the map of scientific
#: outputs.  They are execution evidence, so they moved to
#: `scenario_input_receipts`.  A payload still carrying the key is ambiguous --
#: it is either a pre-V3 writer or a tampered record asserting outputs it did
#: not compute -- and is refused rather than migrated.
_LEGACY_INPUT_KEY = "_time_varying_external_inputs"

_TIME_DIMENSION = dimensionality("second")


class WindowOutcome(str, Enum):
    EXPLICIT_COMPLETED = "explicit_completed"
    CONVERGED = "converged"
    ITERATION_LIMIT = "iteration_limit"
    EVENT_ALIGNED = "event_aligned"
    PARTICIPANT_REFUSED = "participant_refused"
    TRANSFER_REFUSED = "transfer_refused"


def _time(value: Quantity, *, label: str) -> Quantity:
    if not isinstance(value, Quantity) or value.dimensionality != _TIME_DIMENSION:
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    return value.to("second")


def _same_time(left: Quantity, right: Quantity) -> bool:
    a = left.magnitude_in("second")
    b = right.magnitude_in("second")
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15)


@dataclass(frozen=True)
class EdgeResidual:
    edge_id: str
    absolute: Quantity
    relative: float
    norm: str
    satisfied: bool

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id or not isinstance(self.absolute, Quantity):
            raise InvalidScientificProblem(
                "edge residual requires edge id and Quantity"
            )
        if self.absolute.magnitude < 0.0:
            raise InvalidScientificProblem(
                "edge residual absolute value must be non-negative"
            )
        relative = float(self.relative)
        if not math.isfinite(relative) or relative < 0.0:
            raise InvalidScientificProblem(
                "edge residual relative value must be finite and non-negative"
            )
        norm = str(self.norm).strip()
        if norm not in {"linf", "l2"}:
            raise InvalidScientificProblem(
                f"edge residual norm must be 'linf' or 'l2', got {norm!r}"
            )
        if not isinstance(self.satisfied, bool):
            raise InvalidScientificProblem(
                "edge residual satisfied must be boolean"
            )
        object.__setattr__(self, "edge_id", edge_id)
        object.__setattr__(self, "relative", relative)
        object.__setattr__(self, "norm", norm)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EDGE_RESIDUAL_SCHEMA,
            "edge_id": self.edge_id,
            "absolute": self.absolute.to_dict(),
            "relative": self.relative,
            "norm": self.norm,
            "satisfied": self.satisfied,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EdgeResidual":
        require_schema(payload, EDGE_RESIDUAL_SCHEMA)
        return cls(
            edge_id=payload["edge_id"],
            absolute=Quantity.from_dict(payload["absolute"]),
            relative=payload["relative"],
            norm=payload["norm"],
            satisfied=payload["satisfied"],
        )


@dataclass(frozen=True)
class ParticipantStepRecord:
    participant_id: str
    start: Quantity
    end: Quantity
    substeps: int
    internal_converged: bool
    events: tuple[Mapping[str, Any], ...] = ()
    diagnostics: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        participant_id = str(self.participant_id).strip()
        if not participant_id:
            raise InvalidScientificProblem(
                "participant step requires participant_id"
            )
        start = _time(self.start, label="participant step start")
        end = _time(self.end, label="participant step end")
        if end.magnitude < start.magnitude:
            raise InvalidScientificProblem(
                "participant step end cannot precede start"
            )
        if (
            isinstance(self.substeps, bool)
            or not isinstance(self.substeps, int)
            or self.substeps < 0
        ):
            raise InvalidScientificProblem(
                "participant substeps must be non-negative int"
            )
        if not isinstance(self.internal_converged, bool):
            raise InvalidScientificProblem(
                "internal_converged must be boolean"
            )
        events = tuple(self.events)
        if any(not isinstance(event, Mapping) for event in events):
            raise InvalidScientificProblem(
                "participant step events must be mappings"
            )
        if self.diagnostics is not None and not isinstance(
            self.diagnostics, Mapping
        ):
            raise InvalidScientificProblem(
                "participant diagnostics must be a mapping"
            )
        object.__setattr__(self, "participant_id", participant_id)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "events", events)
        object.__setattr__(
            self,
            "diagnostics",
            freeze(None if self.diagnostics is None else dict(self.diagnostics)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_STEP_SCHEMA,
            "participant_id": self.participant_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "substeps": self.substeps,
            "internal_converged": self.internal_converged,
            "events": [dict(event) for event in self.events],
            "diagnostics": (
                {} if self.diagnostics is None else dict(self.diagnostics)
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ParticipantStepRecord":
        require_schema(payload, PARTICIPANT_STEP_SCHEMA)
        diagnostics = payload.get("diagnostics")
        return cls(
            participant_id=payload["participant_id"],
            start=Quantity.from_dict(payload["start"]),
            end=Quantity.from_dict(payload["end"]),
            substeps=payload["substeps"],
            internal_converged=payload["internal_converged"],
            events=tuple(payload.get("events", ())),
            diagnostics=(
                None if diagnostics is None else dict(diagnostics)
            ),
        )


@dataclass(frozen=True)
class CouplingIterationRecord:
    iteration: int
    participant_steps: tuple[ParticipantStepRecord, ...]
    residuals: tuple[EdgeResidual, ...]
    relaxation_factors: Mapping[str, float]
    mapping_diagnostics: tuple[Mapping[str, Any], ...] = ()
    transfer_diagnostics: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.iteration, bool)
            or not isinstance(self.iteration, int)
            or self.iteration < 1
        ):
            raise InvalidScientificProblem(
                "coupling iteration index must be positive"
            )
        steps = tuple(self.participant_steps)
        residuals = tuple(self.residuals)
        if not steps or any(
            not isinstance(step, ParticipantStepRecord) for step in steps
        ):
            raise InvalidScientificProblem(
                "coupling iteration requires participant step records"
            )
        if any(not isinstance(item, EdgeResidual) for item in residuals):
            raise InvalidScientificProblem(
                "coupling iteration residuals must be EdgeResidual records"
            )
        participants = [step.participant_id for step in steps]
        if len(participants) != len(set(participants)):
            raise InvalidScientificProblem(
                "participant may execute only once per coupling iteration"
            )
        edge_ids = [item.edge_id for item in residuals]
        if len(edge_ids) != len(set(edge_ids)):
            raise InvalidScientificProblem(
                "one residual per edge per iteration"
            )

        factors: dict[str, float] = {}
        for edge_id, raw in dict(self.relaxation_factors).items():
            edge_id = str(edge_id).strip()
            factor = float(raw)
            if not edge_id or not math.isfinite(factor) or factor <= 0.0:
                raise InvalidScientificProblem(
                    "relaxation factors require edge id and finite positive value"
                )
            factors[edge_id] = factor

        mapping_diagnostics = tuple(self.mapping_diagnostics)
        transfer_diagnostics = tuple(self.transfer_diagnostics)
        if any(not isinstance(item, Mapping) for item in mapping_diagnostics):
            raise InvalidScientificProblem(
                "mapping diagnostics must be mappings"
            )
        if any(not isinstance(item, Mapping) for item in transfer_diagnostics):
            raise InvalidScientificProblem(
                "transfer diagnostics must be mappings"
            )
        object.__setattr__(self, "participant_steps", steps)
        object.__setattr__(self, "residuals", residuals)
        object.__setattr__(self, "relaxation_factors", freeze(factors))
        object.__setattr__(
            self, "mapping_diagnostics", mapping_diagnostics
        )
        object.__setattr__(
            self, "transfer_diagnostics", transfer_diagnostics
        )

    @property
    def converged(self) -> bool:
        return bool(self.residuals) and all(
            residual.satisfied for residual in self.residuals
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ITERATION_SCHEMA,
            "iteration": self.iteration,
            "participant_steps": [
                step.to_dict() for step in self.participant_steps
            ],
            "residuals": [
                residual.to_dict() for residual in self.residuals
            ],
            "relaxation_factors": dict(
                sorted(self.relaxation_factors.items())
            ),
            "mapping_diagnostics": [
                dict(item) for item in self.mapping_diagnostics
            ],
            "transfer_diagnostics": [
                dict(item) for item in self.transfer_diagnostics
            ],
            "converged": self.converged,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "CouplingIterationRecord":
        require_schema(payload, ITERATION_SCHEMA)
        made = cls(
            iteration=payload["iteration"],
            participant_steps=tuple(
                ParticipantStepRecord.from_dict(item)
                for item in payload["participant_steps"]
            ),
            residuals=tuple(
                EdgeResidual.from_dict(item)
                for item in payload.get("residuals", ())
            ),
            relaxation_factors=dict(
                payload.get("relaxation_factors", {})
            ),
            mapping_diagnostics=tuple(
                payload.get("mapping_diagnostics", ())
            ),
            transfer_diagnostics=tuple(
                payload.get("transfer_diagnostics", ())
            ),
        )
        if "converged" in payload and payload["converged"] != made.converged:
            raise InvalidScientificProblem(
                "serialized coupling iteration converged flag disagrees "
                "with its residuals"
            )
        return made


@dataclass(frozen=True)
class CouplingWindowRecord:
    index: int
    start: Quantity
    end: Quantity
    outcome: WindowOutcome
    iterations: tuple[CouplingIterationRecord, ...]
    event: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.index, bool)
            or not isinstance(self.index, int)
            or self.index < 0
        ):
            raise InvalidScientificProblem(
                "window index must be non-negative"
            )
        start = _time(self.start, label="coupling window start")
        end = _time(self.end, label="coupling window end")
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem(
                "coupling window end must be after start"
            )
        iterations = tuple(self.iterations)
        if not iterations or any(
            not isinstance(item, CouplingIterationRecord)
            for item in iterations
        ):
            raise InvalidScientificProblem(
                "coupling window requires iteration records"
            )
        expected = tuple(range(1, len(iterations) + 1))
        actual = tuple(item.iteration for item in iterations)
        if actual != expected:
            raise InvalidScientificProblem(
                f"coupling window iteration indices must be contiguous "
                f"from 1; got {actual}"
            )
        outcome = WindowOutcome(self.outcome)
        event = self.event
        if event is not None and not isinstance(event, Mapping):
            raise InvalidScientificProblem(
                "coupling window event must be a mapping"
            )
        if outcome is WindowOutcome.EVENT_ALIGNED and event is None:
            raise InvalidScientificProblem(
                "EVENT_ALIGNED window must carry the event that shortened it"
            )
        final_converged = iterations[-1].converged
        if outcome is WindowOutcome.CONVERGED and not final_converged:
            raise InvalidScientificProblem(
                "coupling window declares CONVERGED but its final iteration "
                "does not satisfy every recorded residual"
            )
        if outcome is WindowOutcome.ITERATION_LIMIT and final_converged:
            raise InvalidScientificProblem(
                "coupling window declares ITERATION_LIMIT but its final "
                "iteration already satisfies every recorded residual"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "iterations", iterations)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(
            self,
            "event",
            freeze(None if event is None else dict(event)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WINDOW_SCHEMA,
            "index": self.index,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "outcome": self.outcome.value,
            "iterations": [
                iteration.to_dict() for iteration in self.iterations
            ],
            "event": None if self.event is None else dict(self.event),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "CouplingWindowRecord":
        require_schema(payload, WINDOW_SCHEMA)
        return cls(
            index=payload["index"],
            start=Quantity.from_dict(payload["start"]),
            end=Quantity.from_dict(payload["end"]),
            outcome=WindowOutcome(payload["outcome"]),
            iterations=tuple(
                CouplingIterationRecord.from_dict(item)
                for item in payload["iterations"]
            ),
            event=payload.get("event"),
        )


@dataclass(frozen=True)
class ExternalInputRecord:
    port: PortRef
    value: CouplingValue
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        if not isinstance(self.port, PortRef):
            raise InvalidScientificProblem("external input requires PortRef")
        if not isinstance(self.value, (Quantity, FieldRecord)):
            raise InvalidScientificProblem(
                "external input value must be Quantity or FieldRecord"
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "external input uncertainty must be Uncertainty"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXTERNAL_INPUT_SCHEMA,
            "port": self.port.to_dict(),
            "value": coupling_value_to_dict(self.value),
            "uncertainty": self.uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ExternalInputRecord":
        require_schema(payload, EXTERNAL_INPUT_SCHEMA)
        return cls(
            port=PortRef.from_dict(payload["port"]),
            value=coupling_value_from_dict(payload["value"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
        )


@dataclass(frozen=True)
class InitialCouplingRecord:
    edge_id: str
    value: CouplingValue
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id:
            raise InvalidScientificProblem(
                "initial coupling record requires edge_id"
            )
        if not isinstance(self.value, (Quantity, FieldRecord)):
            raise InvalidScientificProblem(
                "initial coupling value must be Quantity or FieldRecord"
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "initial coupling uncertainty must be Uncertainty"
            )
        object.__setattr__(self, "edge_id", edge_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INITIAL_COUPLING_SCHEMA,
            "edge_id": self.edge_id,
            "value": coupling_value_to_dict(self.value),
            "uncertainty": self.uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "InitialCouplingRecord":
        require_schema(payload, INITIAL_COUPLING_SCHEMA)
        return cls(
            edge_id=payload["edge_id"],
            value=coupling_value_from_dict(payload["value"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
        )

@dataclass(frozen=True)
class MultiphysicsRunRecord:
    run_id: str
    graph: PhysicsGraph
    plan: CouplingPlan
    started_at: Quantity
    ended_at: Quantity
    external_inputs: tuple[ExternalInputRecord, ...]
    initial_coupling: tuple[InitialCouplingRecord, ...]
    windows: tuple[CouplingWindowRecord, ...]
    final_outputs: Mapping[str, Any]
    coupling_error_bound: float | None = None
    initial_state_receipts: tuple[InitialStateReceipt, ...] = ()
    scheduled_events: tuple[ScheduledEventRecord, ...] = ()
    reached_scheduled_events: tuple[ReachedScheduledEvent, ...] = ()
    scenario_digest: str = ""
    scenario_input_receipts: tuple[ScenarioInputReceipt, ...] = ()
    operating_condition_receipts: tuple[OperatingConditionReceipt, ...] = ()
    state_transitions: tuple[StateTransitionReceipt, ...] = ()
    termination: TerminationReceipt | None = None
    quantities_of_interest: tuple[QuantityOfInterestRecord, ...] = ()

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise InvalidScientificProblem(
                "multiphysics run requires run_id"
            )
        if not isinstance(self.graph, PhysicsGraph):
            raise InvalidScientificProblem(
                "multiphysics run requires PhysicsGraph"
            )
        if not isinstance(self.plan, CouplingPlan):
            raise InvalidScientificProblem(
                "multiphysics run requires CouplingPlan"
            )
        self.plan.validate_against(self.graph)

        started = _time(self.started_at, label="run started_at")
        ended = _time(self.ended_at, label="run ended_at")
        if not _same_time(started, self.plan.time.start):
            raise InvalidScientificProblem(
                "run started_at disagrees with coupling plan"
            )
        if not isinstance(self.termination, (TerminationReceipt, type(None))):
            raise InvalidScientificProblem(
                "multiphysics run termination must be a TerminationReceipt or None"
            )
        planned_end = self.plan.time.end.magnitude_in("second")
        actual_end = ended.magnitude_in("second")
        if actual_end > planned_end and not _same_time(ended, self.plan.time.end):
            raise InvalidScientificProblem(
                "multiphysics run ended after the coupling plan horizon"
            )
        if not _same_time(ended, self.plan.time.end):
            # An early end is allowed exactly once: when an authoritative
            # termination receipt says why, at the instant the run stopped.
            if self.termination is None:
                raise InvalidScientificProblem(
                    "a multiphysics run that ends before its coupling plan must "
                    "carry the termination receipt that stopped it"
                )
        if self.termination is not None and not _same_time(
            self.termination.instant, ended
        ):
            raise InvalidScientificProblem(
                "run termination receipt instant disagrees with run ended_at; "
                "execution cannot continue after the condition that stopped it"
            )

        external_inputs = tuple(self.external_inputs)
        if any(
            not isinstance(item, ExternalInputRecord)
            for item in external_inputs
        ):
            raise InvalidScientificProblem(
                "external_inputs must be ExternalInputRecord records"
            )
        refs = [item.port for item in external_inputs]
        if len(refs) != len(set(refs)):
            raise InvalidScientificProblem(
                "external input ports must be unique"
            )

        connected = {edge.target for edge in self.graph.edges}
        expected_external: set[PortRef] = set()
        for participant in self.graph.participants:
            for port in participant.inputs:
                ref = PortRef(
                    participant.participant_id, port.port_id
                )
                if ref not in connected:
                    expected_external.add(ref)
        if set(refs) != expected_external:
            raise InvalidScientificProblem(
                "run external inputs do not exactly cover graph inputs "
                "not supplied by coupling edges; expected="
                f"{sorted(ref.key for ref in expected_external)}, got="
                f"{sorted(ref.key for ref in refs)}"
            )
        for item in external_inputs:
            participant = self.graph.participant(
                item.port.participant_id
            )
            port = participant.port(item.port.port_id)
            if port.direction is not PortDirection.INPUT:
                raise InvalidScientificProblem(
                    f"run external input {item.port.key} is not an input"
                )
            validate_port_coupling_value(port, item.value)
            validate_port_uncertainty(port, item.uncertainty)

        initial = tuple(self.initial_coupling)
        if any(
            not isinstance(item, InitialCouplingRecord)
            for item in initial
        ):
            raise InvalidScientificProblem(
                "initial_coupling must be InitialCouplingRecord records"
            )
        edge_ids = [item.edge_id for item in initial]
        if len(edge_ids) != len(set(edge_ids)):
            raise InvalidScientificProblem(
                "initial coupling edge ids must be unique"
            )
        for item in initial:
            edge = self.graph.edge(item.edge_id)
            port = self.graph.participant(
                edge.target.participant_id
            ).port(edge.target.port_id)
            validate_port_coupling_value(port, item.value)
            validate_port_uncertainty(port, item.uncertainty)

        windows = tuple(self.windows)
        if not windows or any(
            not isinstance(window, CouplingWindowRecord)
            for window in windows
        ):
            raise InvalidScientificProblem(
                "multiphysics run requires coupling windows"
            )
        indices = tuple(window.index for window in windows)
        expected_indices = tuple(range(len(windows)))
        if indices != expected_indices:
            raise InvalidScientificProblem(
                f"coupling window indices must be {expected_indices}, "
                f"got {indices}"
            )
        if not _same_time(windows[0].start, started):
            raise InvalidScientificProblem(
                "first coupling window does not start at run started_at"
            )
        if not _same_time(windows[-1].end, ended):
            raise InvalidScientificProblem(
                "last coupling window does not end at run ended_at"
            )
        for left, right in zip(windows, windows[1:]):
            if not _same_time(left.end, right.start):
                raise InvalidScientificProblem(
                    f"coupling windows {left.index} and {right.index} "
                    "are not temporally contiguous"
                )

        graph_participants = {
            participant.participant_id for participant in self.graph.participants
        }
        for window in windows:
            for iteration in window.iterations:
                stepped = {step.participant_id for step in iteration.participant_steps}
                unknown = sorted(stepped - graph_participants)
                if unknown:
                    raise InvalidScientificProblem(
                        f"coupling window {window.index} records unknown "
                        f"participant step(s) {unknown}"
                    )
                if stepped != graph_participants:
                    raise InvalidScientificProblem(
                        f"coupling window {window.index} iteration "
                        f"{iteration.iteration} does not record exactly one step "
                        "for every graph participant"
                    )
                for step in iteration.participant_steps:
                    if (
                        not _same_time(step.start, window.start)
                        or not _same_time(step.end, window.end)
                    ):
                        raise InvalidScientificProblem(
                            f"participant step {step.participant_id!r} does not "
                            f"span coupling window {window.index}"
                        )

        if not isinstance(self.final_outputs, Mapping):
            raise InvalidScientificProblem(
                "multiphysics run final_outputs must be a mapping"
            )
        if _LEGACY_INPUT_KEY in self.final_outputs:
            raise InvalidScientificProblem(
                f"final_outputs carries {_LEGACY_INPUT_KEY!r}: consumed scenario "
                f"inputs are execution evidence and belong in "
                f"scenario_input_receipts, not in the map of computed outputs"
            )
        if self.coupling_error_bound is not None:
            value = float(self.coupling_error_bound)
            if not math.isfinite(value) or value < 0.0:
                raise InvalidScientificProblem(
                    "coupling_error_bound must be finite and non-negative"
                )
            object.__setattr__(self, "coupling_error_bound", value)
        receipts = tuple(self.initial_state_receipts)
        if any(not isinstance(item, InitialStateReceipt) for item in receipts):
            raise InvalidScientificProblem("initial_state_receipts must contain InitialStateReceipt records")
        if len({item.participant_id for item in receipts}) != len(receipts):
            raise InvalidScientificProblem("one initial state receipt is allowed per participant")
        participant_ids = {item.participant_id for item in self.graph.participants}
        if any(item.participant_id not in participant_ids or not _same_time(item.instant, started) for item in receipts):
            raise InvalidScientificProblem("initial state receipt participant/instant differs from run")
        object.__setattr__(self, "initial_state_receipts", tuple(sorted(receipts, key=lambda item: item.participant_id)))

        scheduled = tuple(self.scheduled_events)
        reached = tuple(self.reached_scheduled_events)
        if any(not isinstance(item, ScheduledEventRecord) for item in scheduled):
            raise InvalidScientificProblem("scheduled_events must contain ScheduledEventRecord records")
        if any(not isinstance(item, ReachedScheduledEvent) for item in reached):
            raise InvalidScientificProblem("reached_scheduled_events must contain ReachedScheduledEvent records")
        scheduled_keys = {(item.event_id, item.instant) for item in scheduled}
        reached_keys = {(item.event_id, item.instant) for item in reached}
        if len(scheduled_keys) != len(scheduled) or len(reached_keys) != len(reached):
            raise InvalidScientificProblem("scheduled event ids/instants must be unique")
        if not reached_keys.issubset(scheduled_keys):
            raise InvalidScientificProblem("reached scheduled events must come from the requested schedule")
        for event in scheduled:
            instant = event.instant.magnitude_in("second")
            if (
                instant < started.magnitude_in("second")
                or instant > self.plan.time.end.magnitude_in("second")
            ):
                raise InvalidScientificProblem(
                    f"scheduled event {event.event_id!r} lies outside the run plan"
                )
            if instant <= ended.magnitude_in("second") and (
                event.event_id, event.instant
            ) not in reached_keys:
                raise InvalidScientificProblem(
                    f"scheduled event {event.event_id!r} was inside the executed "
                    "horizon but has no reached-event receipt"
                )
        boundaries = {0: started, **{window.index + 1: window.end for window in windows}}
        if any(item.boundary_index not in boundaries or not _same_time(item.instant, boundaries[item.boundary_index]) for item in reached):
            raise InvalidScientificProblem("reached scheduled event does not match its run boundary")
        object.__setattr__(self, "scheduled_events", tuple(sorted(scheduled)))
        object.__setattr__(self, "reached_scheduled_events", tuple(sorted(reached)))

        # SCENARIO IDENTITY IS NOT CONDITIONAL ON EVENTS.
        #
        # This record used to require the scenario digest when, and only when,
        # the run carried scheduled events -- and to REFUSE one otherwise. A
        # scenario changes execution through its initial state, its
        # time-varying inputs, its operating conditions and its termination
        # conditions just as materially as through an event it may well not
        # declare, so a run driven by any of those was recorded with no way to
        # say which scenario produced it. Every piece of scenario-sourced
        # evidence below now demands the digest, and the digest alone is
        # allowed: a scenario that only fixed the horizon still identifies the
        # world the run executed in.
        #
        # Validated at the END of this constructor, once started_at, ended_at
        # and windows are normalized, because every check below compares an
        # instant against a run boundary.
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "ended_at", ended)
        object.__setattr__(
            self,
            "external_inputs",
            tuple(sorted(external_inputs, key=lambda item: item.port.key)),
        )
        object.__setattr__(
            self,
            "initial_coupling",
            tuple(sorted(initial, key=lambda item: item.edge_id)),
        )
        object.__setattr__(self, "windows", windows)
        object.__setattr__(
            self,
            "final_outputs",
            freeze(dict(self.final_outputs)),
        )
        self._validate_scenario_evidence()

    def _validate_scenario_evidence(self) -> None:
        digest = str(self.scenario_digest).strip().lower()
        if digest and (
            len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise InvalidScientificProblem(
                "run scenario_digest must be a sha256 hex digest"
            )
        object.__setattr__(self, "scenario_digest", digest)

        participant_ids = {item.participant_id for item in self.graph.participants}
        boundaries = {0: self.started_at}
        boundaries.update({window.index + 1: window.end for window in self.windows})

        inputs = tuple(self.scenario_input_receipts)
        conditions = tuple(self.operating_condition_receipts)
        transitions = tuple(self.state_transitions)
        qois = tuple(self.quantities_of_interest)
        for label, values, expected in (
            ("scenario_input_receipts", inputs, ScenarioInputReceipt),
            ("operating_condition_receipts", conditions, OperatingConditionReceipt),
            ("state_transitions", transitions, StateTransitionReceipt),
            ("quantities_of_interest", qois, QuantityOfInterestRecord),
        ):
            if any(not isinstance(item, expected) for item in values):
                raise InvalidScientificProblem(
                    f"{label} must contain {expected.__name__} records"
                )

        for item in inputs:
            if item.port.participant_id not in participant_ids:
                raise InvalidScientificProblem(
                    f"scenario input receipt names participant "
                    f"{item.port.participant_id!r} outside the run graph"
                )
            port = self.graph.participant(item.port.participant_id).port(
                item.port.port_id
            )
            if port.direction is not PortDirection.INPUT:
                raise InvalidScientificProblem(
                    f"scenario input receipt {item.input_id!r} names output port "
                    f"{item.port.key}"
                )
            validate_port_coupling_value(port, item.value)
            validate_port_uncertainty(port, item.uncertainty)
            self._require_boundary(boundaries, item.boundary_index, item.instant,
                                   "scenario input receipt")
        if len({item.key for item in inputs}) != len(inputs):
            raise InvalidScientificProblem(
                "scenario input receipts are not unique per boundary, input and port"
            )

        for item in conditions:
            if item.participant_id not in participant_ids:
                raise InvalidScientificProblem(
                    f"operating condition receipt names participant "
                    f"{item.participant_id!r} outside the run graph"
                )
            self._require_boundary(boundaries, item.boundary_index, item.instant,
                                   "operating condition receipt")
        if len({item.key for item in conditions}) != len(conditions):
            raise InvalidScientificProblem(
                "operating condition receipts are not unique per boundary, "
                "participant and condition"
            )

        for item in transitions:
            if item.participant_id not in participant_ids:
                raise InvalidScientificProblem(
                    f"state transition names participant {item.participant_id!r} "
                    f"outside the run graph"
                )
            window = next(
                (w for w in self.windows if w.index == item.window_index), None
            )
            if (
                window is None
                or not _same_time(window.start, item.start)
                or not _same_time(window.end, item.end)
            ):
                raise InvalidScientificProblem(
                    f"state transition {item.window_index} does not span a "
                    f"coupling window of this run"
                )
        if len({item.key for item in transitions}) != len(transitions):
            raise InvalidScientificProblem(
                "state transitions are not unique per window and participant"
            )

        by_participant: dict[str, list[StateTransitionReceipt]] = {}
        for item in transitions:
            by_participant.setdefault(item.participant_id, []).append(item)
        initial_by_participant = {
            item.participant_id: item for item in self.initial_state_receipts
        }
        for participant_id, records in by_participant.items():
            records.sort(key=lambda item: item.window_index)
            initial_receipt = initial_by_participant.get(participant_id)
            if (
                initial_receipt is not None
                and records
                and records[0].window_index == 0
                and records[0].start_state_digest != initial_receipt.state_digest
            ):
                raise InvalidScientificProblem(
                    f"participant {participant_id!r} first transition does not "
                    "start from its recorded initial state"
                )
            for previous, current in zip(records, records[1:]):
                if current.window_index != previous.window_index + 1:
                    continue
                if current.start_state_digest != previous.end_state_digest:
                    raise InvalidScientificProblem(
                        f"participant {participant_id!r} state chain breaks "
                        f"between windows {previous.window_index} and "
                        f"{current.window_index}"
                    )

        for item in qois:
            if item.port.participant_id not in participant_ids:
                raise InvalidScientificProblem(
                    f"quantity of interest names participant "
                    f"{item.port.participant_id!r} outside the run graph"
                )
            port = self.graph.participant(item.port.participant_id).port(
                item.port.port_id
            )
            if port.direction is not PortDirection.OUTPUT:
                raise InvalidScientificProblem(
                    f"quantity of interest {item.qoi_id!r} is bound to "
                    f"{item.port.key}, which is not a produced output"
                )
            validate_port_coupling_value(port, item.value)
            validate_port_uncertainty(port, item.uncertainty)
            if not _same_time(item.instant, self.ended_at):
                raise InvalidScientificProblem(
                    f"quantity of interest {item.qoi_id!r} is not reported at the "
                    f"instant the run ended"
                )
        if len({item.qoi_id for item in qois}) != len(qois):
            raise InvalidScientificProblem("quantity of interest ids must be unique")

        termination = self.termination
        if termination is not None:
            self._require_boundary(
                boundaries, termination.boundary_index, termination.instant,
                "termination receipt",
            )

        scenario_bound = (
            bool(self.scheduled_events)
            or bool(self.initial_state_receipts)
            or bool(inputs)
            or bool(conditions)
            or bool(qois)
            or termination is not None
        )
        if scenario_bound and not digest:
            raise InvalidScientificProblem(
                "a run carrying scenario evidence must be bound to the sha256 "
                "digest of the exact scenario that produced it"
            )
        for item in (*inputs, *conditions, *qois):
            if item.scenario_digest != digest:
                raise InvalidScientificProblem(
                    "scenario evidence is bound to a different scenario than the run"
                )
        if termination is not None and termination.scenario_digest != digest:
            raise InvalidScientificProblem(
                "termination receipt is bound to a different scenario than the run"
            )
        for item in transitions:
            if item.scenario_digest != digest:
                raise InvalidScientificProblem(
                    "state transition is bound to a different scenario than the run"
                )

        object.__setattr__(
            self, "scenario_input_receipts", tuple(sorted(inputs, key=lambda i: i.key))
        )
        object.__setattr__(
            self,
            "operating_condition_receipts",
            tuple(sorted(conditions, key=lambda i: i.key)),
        )
        object.__setattr__(
            self, "state_transitions", tuple(sorted(transitions, key=lambda i: i.key))
        )
        object.__setattr__(
            self, "quantities_of_interest", tuple(sorted(qois, key=lambda i: i.qoi_id))
        )

    @staticmethod
    def _require_boundary(
        boundaries: Mapping[int, Quantity],
        index: int,
        instant: Quantity,
        label: str,
    ) -> None:
        found = boundaries.get(index)
        if found is None or not _same_time(found, instant):
            raise InvalidScientificProblem(
                f"{label} does not sit on boundary {index} of this run"
            )

    @property
    def graph_id(self) -> str:
        return self.graph.graph_id

    @property
    def graph_fingerprint(self) -> str:
        return self.graph.fingerprint()

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    @property
    def plan_fingerprint(self) -> str:
        return self.plan.fingerprint()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA,
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "graph_fingerprint": self.graph_fingerprint,
            "plan_id": self.plan_id,
            "plan_fingerprint": self.plan_fingerprint,
            "graph": self.graph.to_dict(),
            "plan": self.plan.to_dict(),
            "started_at": self.started_at.to_dict(),
            "ended_at": self.ended_at.to_dict(),
            "external_inputs": [
                item.to_dict() for item in self.external_inputs
            ],
            "initial_coupling": [
                item.to_dict() for item in self.initial_coupling
            ],
            "windows": [
                window.to_dict() for window in self.windows
            ],
            "final_outputs": dict(self.final_outputs),
            "coupling_error_bound": self.coupling_error_bound,
            "initial_state_receipts": [item.to_dict() for item in self.initial_state_receipts],
            "scheduled_events": [item.to_dict() for item in self.scheduled_events],
            "reached_scheduled_events": [item.to_dict() for item in self.reached_scheduled_events],
            "scenario_digest": self.scenario_digest,
            "scenario_input_receipts": [
                item.to_dict() for item in self.scenario_input_receipts
            ],
            "operating_condition_receipts": [
                item.to_dict() for item in self.operating_condition_receipts
            ],
            "state_transitions": [item.to_dict() for item in self.state_transitions],
            "termination": (
                None if self.termination is None else self.termination.to_dict()
            ),
            "quantities_of_interest": [
                item.to_dict() for item in self.quantities_of_interest
            ],
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "MultiphysicsRunRecord":
        schema = require_schema_any(
            payload, (RUN_SCHEMA_V1, RUN_SCHEMA_V2, RUN_SCHEMA)
        )
        graph = PhysicsGraph.from_dict(payload["graph"])
        plan = CouplingPlan.from_dict(payload["plan"])
        made = cls(
            run_id=payload["run_id"],
            graph=graph,
            plan=plan,
            started_at=Quantity.from_dict(payload["started_at"]),
            ended_at=Quantity.from_dict(payload["ended_at"]),
            external_inputs=tuple(
                ExternalInputRecord.from_dict(item)
                for item in payload.get("external_inputs", ())
            ),
            initial_coupling=tuple(
                InitialCouplingRecord.from_dict(item)
                for item in payload.get("initial_coupling", ())
            ),
            windows=tuple(
                CouplingWindowRecord.from_dict(item)
                for item in payload["windows"]
            ),
            final_outputs=dict(payload["final_outputs"]),
            coupling_error_bound=payload.get("coupling_error_bound"),
            initial_state_receipts=(
                () if schema == RUN_SCHEMA_V1 else tuple(
                    InitialStateReceipt.from_dict(item)
                    for item in payload.get("initial_state_receipts", ())
                )
            ),
            scheduled_events=(
                () if schema == RUN_SCHEMA_V1 else tuple(
                    ScheduledEventRecord.from_dict(item)
                    for item in payload.get("scheduled_events", ())
                )
            ),
            reached_scheduled_events=(
                () if schema == RUN_SCHEMA_V1 else tuple(
                    ReachedScheduledEvent.from_dict(item)
                    for item in payload.get("reached_scheduled_events", ())
                )
            ),
            scenario_digest="" if schema == RUN_SCHEMA_V1 else payload.get("scenario_digest", ""),
            scenario_input_receipts=tuple(
                ScenarioInputReceipt.from_dict(item)
                for item in payload.get("scenario_input_receipts", ())
            ),
            operating_condition_receipts=tuple(
                OperatingConditionReceipt.from_dict(item)
                for item in payload.get("operating_condition_receipts", ())
            ),
            state_transitions=tuple(
                StateTransitionReceipt.from_dict(item)
                for item in payload.get("state_transitions", ())
            ),
            termination=(
                None
                if payload.get("termination") is None
                else TerminationReceipt.from_dict(payload["termination"])
            ),
            quantities_of_interest=tuple(
                QuantityOfInterestRecord.from_dict(item)
                for item in payload.get("quantities_of_interest", ())
            ),
        )
        derived = {
            "graph_id": made.graph_id,
            "graph_fingerprint": made.graph_fingerprint,
            "plan_id": made.plan_id,
            "plan_fingerprint": made.plan_fingerprint,
        }
        for key, value in derived.items():
            if payload.get(key) != value:
                raise InvalidScientificProblem(
                    f"serialized multiphysics run {key} "
                    f"{payload.get(key)!r} disagrees with embedded "
                    f"declaration {value!r}"
                )
        return made
