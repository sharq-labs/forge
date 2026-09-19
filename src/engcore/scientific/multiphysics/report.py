"""Run records for the generic multiphysics coupling runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import schema_string
from ..units.quantity import Quantity

EDGE_RESIDUAL_SCHEMA = schema_string("multiphysics_edge_residual")
PARTICIPANT_STEP_SCHEMA = schema_string("multiphysics_participant_step")
ITERATION_SCHEMA = schema_string("multiphysics_iteration")
WINDOW_SCHEMA = schema_string("multiphysics_window")
RUN_SCHEMA = schema_string("multiphysics_run")


class WindowOutcome(str, Enum):
    EXPLICIT_COMPLETED = "explicit_completed"
    CONVERGED = "converged"
    ITERATION_LIMIT = "iteration_limit"
    EVENT_ALIGNED = "event_aligned"
    PARTICIPANT_REFUSED = "participant_refused"
    TRANSFER_REFUSED = "transfer_refused"


@dataclass(frozen=True)
class EdgeResidual:
    edge_id: str
    absolute: Quantity
    relative: float
    norm: str
    satisfied: bool

    def __post_init__(self) -> None:
        if not str(self.edge_id).strip() or not isinstance(self.absolute, Quantity):
            raise InvalidScientificProblem("edge residual requires edge id and Quantity")
        relative = float(self.relative)
        if relative < 0.0:
            raise InvalidScientificProblem("edge residual relative value must be non-negative")
        if not isinstance(self.satisfied, bool):
            raise InvalidScientificProblem("edge residual satisfied must be boolean")
        object.__setattr__(self, "relative", relative)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EDGE_RESIDUAL_SCHEMA,
            "edge_id": self.edge_id,
            "absolute": self.absolute.to_dict(),
            "relative": self.relative,
            "norm": self.norm,
            "satisfied": self.satisfied,
        }


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
        if isinstance(self.substeps, bool) or not isinstance(self.substeps, int) or self.substeps < 0:
            raise InvalidScientificProblem("participant substeps must be non-negative int")
        if not isinstance(self.internal_converged, bool):
            raise InvalidScientificProblem("internal_converged must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_STEP_SCHEMA,
            "participant_id": self.participant_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "substeps": self.substeps,
            "internal_converged": self.internal_converged,
            "events": [dict(e) for e in self.events],
            "diagnostics": {} if self.diagnostics is None else dict(self.diagnostics),
        }


@dataclass(frozen=True)
class CouplingIterationRecord:
    iteration: int
    participant_steps: tuple[ParticipantStepRecord, ...]
    residuals: tuple[EdgeResidual, ...]
    relaxation_factors: Mapping[str, float]
    mapping_diagnostics: tuple[Mapping[str, Any], ...] = ()
    transfer_diagnostics: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.iteration, bool) or not isinstance(self.iteration, int) or self.iteration < 1:
            raise InvalidScientificProblem("coupling iteration index must be positive")

    @property
    def converged(self) -> bool:
        return bool(self.residuals) and all(r.satisfied for r in self.residuals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ITERATION_SCHEMA,
            "iteration": self.iteration,
            "participant_steps": [s.to_dict() for s in self.participant_steps],
            "residuals": [r.to_dict() for r in self.residuals],
            "relaxation_factors": dict(sorted(self.relaxation_factors.items())),
            "mapping_diagnostics": [dict(d) for d in self.mapping_diagnostics],
            "transfer_diagnostics": [dict(d) for d in self.transfer_diagnostics],
            "converged": self.converged,
        }


@dataclass(frozen=True)
class CouplingWindowRecord:
    index: int
    start: Quantity
    end: Quantity
    outcome: WindowOutcome
    iterations: tuple[CouplingIterationRecord, ...]
    event: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise InvalidScientificProblem("window index must be non-negative")
        object.__setattr__(self, "outcome", WindowOutcome(self.outcome))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WINDOW_SCHEMA,
            "index": self.index,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "outcome": self.outcome.value,
            "iterations": [i.to_dict() for i in self.iterations],
            "event": None if self.event is None else dict(self.event),
        }


@dataclass(frozen=True)
class MultiphysicsRunRecord:
    run_id: str
    graph_id: str
    plan_id: str
    started_at: Quantity
    ended_at: Quantity
    windows: tuple[CouplingWindowRecord, ...]
    final_outputs: Mapping[str, Any]
    coupling_error_bound: float | None = None

    def __post_init__(self) -> None:
        for label in ("run_id", "graph_id", "plan_id"):
            if not str(getattr(self, label)).strip():
                raise InvalidScientificProblem(f"multiphysics run requires {label}")
        if self.coupling_error_bound is not None:
            value = float(self.coupling_error_bound)
            if value < 0.0:
                raise InvalidScientificProblem("coupling_error_bound must be non-negative")
            object.__setattr__(self, "coupling_error_bound", value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA,
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "started_at": self.started_at.to_dict(),
            "ended_at": self.ended_at.to_dict(),
            "windows": [w.to_dict() for w in self.windows],
            "final_outputs": dict(self.final_outputs),
            "coupling_error_bound": self.coupling_error_bound,
        }
