"""Auditable records emitted by the multiphysics runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..fields import (
    MeshSupport,
    StructuredMesh,
    UnstructuredMesh,
    read_mesh_support,
)
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from .graph import PhysicsGraph
from .plan import CouplingPlan

EDGE_RESIDUAL_SCHEMA = schema_string("multiphysics_edge_residual")
PARTICIPANT_STEP_SCHEMA = schema_string("multiphysics_participant_step")
ITERATION_SCHEMA = schema_string("multiphysics_iteration")
WINDOW_SCHEMA = schema_string("multiphysics_window")
RUN_SCHEMA = schema_string("multiphysics_run")

_TIME_DIMENSION = dimensionality("second")


class WindowOutcome(str, Enum):
    EXPLICIT_COMPLETED = "explicit_completed"
    CONVERGED = "converged"
    ITERATION_LIMIT = "iteration_limit"
    EVENT_ALIGNED = "event_aligned"
    PARTICIPANT_REFUSED = "participant_refused"
    TRANSFER_REFUSED = "transfer_refused"


def _time(value: Quantity, *, label: str) -> Quantity:
    if (
        not isinstance(value, Quantity)
        or value.dimensionality != _TIME_DIMENSION
    ):
        raise InvalidScientificProblem(
            f"{label} must be a time Quantity"
        )
    return value.to("second")


def _same_time(left: Quantity, right: Quantity) -> bool:
    a = left.magnitude_in("second")
    b = right.magnitude_in("second")
    return math.isclose(
        a, b, rel_tol=1e-12, abs_tol=1e-15
    )


@dataclass(frozen=True)
class EdgeResidual:
    edge_id: str
    absolute: Quantity
    relative: float
    norm: str
    satisfied: bool

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id or not isinstance(
            self.absolute, Quantity
        ):
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
                f"edge residual has unsupported norm {norm!r}"
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
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "EdgeResidual":
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
        start = _time(
            self.start, label="participant step start"
        )
        end = _time(
            self.end, label="participant step end"
        )
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
        if any(
            not isinstance(event, Mapping)
            for event in events
        ):
            raise InvalidScientificProblem(
                "participant step events must be mappings"
            )
        if (
            self.diagnostics is not None
            and not isinstance(self.diagnostics, Mapping)
        ):
            raise InvalidScientificProblem(
                "participant diagnostics must be mapping"
            )
        object.__setattr__(
            self, "participant_id", participant_id
        )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "events", events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_STEP_SCHEMA,
            "participant_id": self.participant_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "substeps": self.substeps,
            "internal_converged": self.internal_converged,
            "events": [
                dict(event) for event in self.events
            ],
            "diagnostics": (
                {}
                if self.diagnostics is None
                else dict(self.diagnostics)
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
            internal_converged=payload[
                "internal_converged"
            ],
            events=tuple(payload.get("events", ())),
            diagnostics=(
                None
                if diagnostics is None
                else dict(diagnostics)
            ),
        )


@dataclass(frozen=True)
class CouplingIterationRecord:
    iteration: int
    participant_steps: tuple[
        ParticipantStepRecord, ...
    ]
    residuals: tuple[EdgeResidual, ...]
    relaxation_factors: Mapping[str, float]
    mapping_diagnostics: tuple[
        Mapping[str, Any], ...
    ] = ()
    transfer_diagnostics: tuple[
        Mapping[str, Any], ...
    ] = ()

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
            not isinstance(
                step, ParticipantStepRecord
            )
            for step in steps
        ):
            raise InvalidScientificProblem(
                "coupling iteration requires participant steps"
            )
        participant_ids = [
            step.participant_id for step in steps
        ]
        if len(participant_ids) != len(
            set(participant_ids)
        ):
            raise InvalidScientificProblem(
                "participant may execute only once per iteration"
            )
        if any(
            not isinstance(residual, EdgeResidual)
            for residual in residuals
        ):
            raise InvalidScientificProblem(
                "iteration residuals must be EdgeResidual"
            )
        residual_ids = [
            residual.edge_id for residual in residuals
        ]
        if len(residual_ids) != len(
            set(residual_ids)
        ):
            raise InvalidScientificProblem(
                "one residual per edge per iteration"
            )

        factors: dict[str, float] = {}
        for raw_id, raw_factor in dict(
            self.relaxation_factors
        ).items():
            edge_id = str(raw_id).strip()
            factor = float(raw_factor)
            if (
                not edge_id
                or not math.isfinite(factor)
                or factor <= 0.0
            ):
                raise InvalidScientificProblem(
                    "relaxation factors require edge id and finite positive value"
                )
            factors[edge_id] = factor

        mappings = tuple(self.mapping_diagnostics)
        transfers = tuple(self.transfer_diagnostics)
        if any(
            not isinstance(item, Mapping)
            for item in mappings + transfers
        ):
            raise InvalidScientificProblem(
                "coupling diagnostics must be mappings"
            )
        object.__setattr__(
            self, "participant_steps", steps
        )
        object.__setattr__(self, "residuals", residuals)
        object.__setattr__(
            self, "relaxation_factors", factors
        )
        object.__setattr__(
            self, "mapping_diagnostics", mappings
        )
        object.__setattr__(
            self, "transfer_diagnostics", transfers
        )

    @property
    def converged(self) -> bool:
        return bool(self.residuals) and all(
            residual.satisfied
            for residual in self.residuals
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ITERATION_SCHEMA,
            "iteration": self.iteration,
            "participant_steps": [
                step.to_dict()
                for step in self.participant_steps
            ],
            "residuals": [
                residual.to_dict()
                for residual in self.residuals
            ],
            "relaxation_factors": dict(
                sorted(
                    self.relaxation_factors.items()
                )
            ),
            "mapping_diagnostics": [
                dict(item)
                for item in self.mapping_diagnostics
            ],
            "transfer_diagnostics": [
                dict(item)
                for item in self.transfer_diagnostics
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
                for item in payload[
                    "participant_steps"
                ]
            ),
            residuals=tuple(
                EdgeResidual.from_dict(item)
                for item in payload.get(
                    "residuals", ()
                )
            ),
            relaxation_factors=dict(
                payload.get(
                    "relaxation_factors", {}
                )
            ),
            mapping_diagnostics=tuple(
                payload.get(
                    "mapping_diagnostics", ()
                )
            ),
            transfer_diagnostics=tuple(
                payload.get(
                    "transfer_diagnostics", ()
                )
            ),
        )
        if (
            "converged" in payload
            and payload["converged"] != made.converged
        ):
            raise InvalidScientificProblem(
                "serialized iteration convergence flag "
                "disagrees with residuals"
            )
        return made


@dataclass(frozen=True)
class CouplingWindowRecord:
    index: int
    start: Quantity
    end: Quantity
    outcome: WindowOutcome
    iterations: tuple[
        CouplingIterationRecord, ...
    ]
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
        start = _time(
            self.start, label="coupling window start"
        )
        end = _time(
            self.end, label="coupling window end"
        )
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem(
                "coupling window end must be after start"
            )
        iterations = tuple(self.iterations)
        if not iterations or any(
            not isinstance(
                item, CouplingIterationRecord
            )
            for item in iterations
        ):
            raise InvalidScientificProblem(
                "coupling window requires iterations"
            )
        expected = tuple(
            range(1, len(iterations) + 1)
        )
        actual = tuple(
            item.iteration for item in iterations
        )
        if actual != expected:
            raise InvalidScientificProblem(
                f"iteration indices must be contiguous; "
                f"expected {expected}, got {actual}"
            )
        outcome = WindowOutcome(self.outcome)
        event = self.event
        if (
            event is not None
            and not isinstance(event, Mapping)
        ):
            raise InvalidScientificProblem(
                "coupling window event must be mapping"
            )
        if (
            outcome is WindowOutcome.EVENT_ALIGNED
            and event is None
        ):
            raise InvalidScientificProblem(
                "EVENT_ALIGNED window must carry event"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(
            self, "iterations", iterations
        )
        object.__setattr__(self, "outcome", outcome)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WINDOW_SCHEMA,
            "index": self.index,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "outcome": self.outcome.value,
            "iterations": [
                item.to_dict()
                for item in self.iterations
            ],
            "event": (
                None
                if self.event is None
                else dict(self.event)
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "CouplingWindowRecord":
        require_schema(payload, WINDOW_SCHEMA)
        return cls(
            index=payload["index"],
            start=Quantity.from_dict(
                payload["start"]
            ),
            end=Quantity.from_dict(payload["end"]),
            outcome=WindowOutcome(
                payload["outcome"]
            ),
            iterations=tuple(
                CouplingIterationRecord.from_dict(item)
                for item in payload["iterations"]
            ),
            event=payload.get("event"),
        )


@dataclass(frozen=True)
class MultiphysicsRunRecord:
    run_id: str
    graph: PhysicsGraph
    plan: CouplingPlan
    meshes: tuple[MeshSupport, ...]
    started_at: Quantity
    ended_at: Quantity
    windows: tuple[CouplingWindowRecord, ...]
    final_outputs: Mapping[str, Any]
    coupling_error_indicator: float | None = None

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise InvalidScientificProblem(
                "multiphysics run requires run_id"
            )
        object.__setattr__(self, "run_id", run_id)
        if not isinstance(self.graph, PhysicsGraph):
            raise InvalidScientificProblem(
                "multiphysics run requires PhysicsGraph"
            )
        if not isinstance(self.plan, CouplingPlan):
            raise InvalidScientificProblem(
                "multiphysics run requires CouplingPlan"
            )
        self.plan.validate_against(self.graph)
        meshes = tuple(self.meshes)
        if any(
            not isinstance(mesh, (StructuredMesh, UnstructuredMesh))
            for mesh in meshes
        ):
            raise InvalidScientificProblem(
                "multiphysics run meshes must be declared mesh supports"
            )
        mesh_ids = [mesh.mesh_id for mesh in meshes]
        if len(mesh_ids) != len(set(mesh_ids)):
            raise InvalidScientificProblem(
                "multiphysics run mesh ids must be unique"
            )
        required_mesh_ids = {
            port.field.mesh_id
            for participant in self.graph.participants
            for port in participant.ports
            if port.field is not None
        }
        if set(mesh_ids) != required_mesh_ids:
            raise InvalidScientificProblem(
                f"multiphysics run mesh bindings mismatch graph; "
                f"missing={sorted(required_mesh_ids-set(mesh_ids))}, "
                f"extra={sorted(set(mesh_ids)-required_mesh_ids)}"
            )
        by_mesh = {mesh.mesh_id: mesh for mesh in meshes}
        for participant in self.graph.participants:
            for port in participant.ports:
                if port.field is not None:
                    port.field.require_support(
                        by_mesh[port.field.mesh_id]
                    )
        object.__setattr__(
            self,
            "meshes",
            tuple(sorted(meshes, key=lambda mesh: mesh.mesh_id)),
        )

        started = _time(
            self.started_at, label="run started_at"
        )
        ended = _time(
            self.ended_at, label="run ended_at"
        )
        if ended.magnitude <= started.magnitude:
            raise InvalidScientificProblem(
                "run ended_at must be after started_at"
            )
        if not _same_time(
            started, self.plan.time.start
        ):
            raise InvalidScientificProblem(
                "run started_at disagrees with CouplingPlan"
            )
        if not _same_time(
            ended, self.plan.time.end
        ):
            raise InvalidScientificProblem(
                "run ended_at disagrees with CouplingPlan"
            )

        windows = tuple(self.windows)
        if not windows or any(
            not isinstance(
                window, CouplingWindowRecord
            )
            for window in windows
        ):
            raise InvalidScientificProblem(
                "multiphysics run requires coupling windows"
            )
        indices = tuple(
            window.index for window in windows
        )
        expected_indices = tuple(
            range(len(windows))
        )
        if indices != expected_indices:
            raise InvalidScientificProblem(
                f"window indices must be "
                f"{expected_indices}, got {indices}"
            )
        if not _same_time(
            windows[0].start, started
        ):
            raise InvalidScientificProblem(
                "first window does not start at run start"
            )
        if not _same_time(
            windows[-1].end, ended
        ):
            raise InvalidScientificProblem(
                "last window does not end at run end"
            )
        for left, right in zip(
            windows, windows[1:]
        ):
            if not _same_time(left.end, right.start):
                raise InvalidScientificProblem(
                    f"windows {left.index} and "
                    f"{right.index} are not contiguous"
                )

        if not isinstance(
            self.final_outputs, Mapping
        ):
            raise InvalidScientificProblem(
                "final_outputs must be mapping"
            )
        if self.coupling_error_indicator is not None:
            indicator = float(
                self.coupling_error_indicator
            )
            if (
                not math.isfinite(indicator)
                or indicator < 0.0
            ):
                raise InvalidScientificProblem(
                    "coupling_error_indicator must be "
                    "finite and non-negative"
                )
            object.__setattr__(
                self,
                "coupling_error_indicator",
                indicator,
            )
        object.__setattr__(
            self, "started_at", started
        )
        object.__setattr__(self, "ended_at", ended)
        object.__setattr__(self, "windows", windows)

    @property
    def graph_id(self) -> str:
        return self.graph.graph_id

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA,
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "graph": self.graph.to_dict(),
            "plan": self.plan.to_dict(),
            "meshes": [mesh.to_dict() for mesh in self.meshes],
            "started_at": self.started_at.to_dict(),
            "ended_at": self.ended_at.to_dict(),
            "windows": [
                window.to_dict()
                for window in self.windows
            ],
            "final_outputs": dict(
                self.final_outputs
            ),
            "coupling_error_indicator": (
                self.coupling_error_indicator
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "MultiphysicsRunRecord":
        require_schema(payload, RUN_SCHEMA)
        made = cls(
            run_id=payload["run_id"],
            graph=PhysicsGraph.from_dict(
                payload["graph"]
            ),
            plan=CouplingPlan.from_dict(
                payload["plan"]
            ),
            meshes=tuple(
                read_mesh_support(item)
                for item in payload.get("meshes", ())
            ),
            started_at=Quantity.from_dict(
                payload["started_at"]
            ),
            ended_at=Quantity.from_dict(
                payload["ended_at"]
            ),
            windows=tuple(
                CouplingWindowRecord.from_dict(item)
                for item in payload["windows"]
            ),
            final_outputs=dict(
                payload["final_outputs"]
            ),
            coupling_error_indicator=payload.get(
                "coupling_error_indicator"
            ),
        )
        if payload.get("graph_id") != made.graph_id:
            raise InvalidScientificProblem(
                "serialized graph_id disagrees with embedded PhysicsGraph"
            )
        if payload.get("plan_id") != made.plan_id:
            raise InvalidScientificProblem(
                "serialized plan_id disagrees with embedded CouplingPlan"
            )
        return made
