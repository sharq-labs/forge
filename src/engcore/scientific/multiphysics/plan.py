"""Execution policy for a PhysicsGraph.

Topology and execution policy are separate records. The same graph may be
executed explicitly or implicitly, serially or Jacobi-style, with different
time windows and convergence policies without changing its scientific wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import (
    Quantity,
    dimensionality,
    require_spread_unit,
)
from .graph import PhysicsGraph

TIME_POLICY_SCHEMA = schema_string("multiphysics_time_policy")
CONVERGENCE_CRITERION_SCHEMA = schema_string("multiphysics_convergence_criterion")
RELAXATION_POLICY_SCHEMA = schema_string("multiphysics_relaxation_policy")
COUPLING_PLAN_SCHEMA = schema_string("multiphysics_coupling_plan")


class CouplingScheme(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class IterationSemantics(str, Enum):
    SERIAL = "serial"
    JACOBI = "jacobi"


class ResidualNorm(str, Enum):
    LINF = "linf"
    L2 = "l2"


class RelaxationKind(str, Enum):
    NONE = "none"
    CONSTANT = "constant"
    AITKEN = "aitken"


def _time(value: Quantity, *, label: str, allow_zero: bool = False) -> Quantity:
    if not isinstance(value, Quantity) or dimensionality(value.units) != dimensionality("second"):
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    seconds = value.magnitude_in("second")
    if seconds < 0.0 or (seconds == 0.0 and not allow_zero):
        raise InvalidScientificProblem(f"{label} must be {'non-negative' if allow_zero else 'positive'}")
    return value.to("second")


@dataclass(frozen=True)
class TimePolicy:
    start: Quantity
    end: Quantity
    coupling_window: Quantity
    align_events: bool = True
    max_windows: int = 100000

    def __post_init__(self) -> None:
        start = _time(self.start, label="start", allow_zero=True)
        end = _time(self.end, label="end", allow_zero=True)
        window = _time(self.coupling_window, label="coupling_window")
        if end.magnitude_in("second") <= start.magnitude_in("second"):
            raise InvalidScientificProblem("time policy end must be after start")
        if not isinstance(self.align_events, bool):
            raise InvalidScientificProblem("align_events must be boolean")
        if isinstance(self.max_windows, bool) or not isinstance(self.max_windows, int) or self.max_windows < 1:
            raise InvalidScientificProblem("max_windows must be a positive int")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "coupling_window", window)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TIME_POLICY_SCHEMA,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "coupling_window": self.coupling_window.to_dict(),
            "align_events": self.align_events,
            "max_windows": self.max_windows,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimePolicy":
        require_schema(payload, TIME_POLICY_SCHEMA)
        return cls(
            start=Quantity.from_dict(payload["start"]),
            end=Quantity.from_dict(payload["end"]),
            coupling_window=Quantity.from_dict(payload["coupling_window"]),
            align_events=payload.get("align_events", True),
            max_windows=payload.get("max_windows", 100000),
        )


@dataclass(frozen=True)
class ConvergenceCriterion:
    edge_id: str
    relative_tolerance: float
    absolute_tolerance: Quantity
    norm: ResidualNorm = ResidualNorm.LINF

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id:
            raise InvalidScientificProblem("convergence criterion requires edge_id")
        object.__setattr__(self, "edge_id", edge_id)
        relative = float(self.relative_tolerance)
        if not math.isfinite(relative) or relative < 0.0:
            raise InvalidScientificProblem(
                "relative_tolerance must be finite and non-negative"
            )
        object.__setattr__(self, "relative_tolerance", relative)
        if (
            not isinstance(self.absolute_tolerance, Quantity)
            or self.absolute_tolerance.magnitude < 0.0
        ):
            raise InvalidScientificProblem(
                "absolute_tolerance must be a non-negative Quantity"
            )
        require_spread_unit(
            self.absolute_tolerance.units,
            context=f"coupling criterion {edge_id!r}",
        )
        object.__setattr__(self, "norm", ResidualNorm(self.norm))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONVERGENCE_CRITERION_SCHEMA,
            "edge_id": self.edge_id,
            "relative_tolerance": self.relative_tolerance,
            "absolute_tolerance": self.absolute_tolerance.to_dict(),
            "norm": self.norm.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConvergenceCriterion":
        require_schema(payload, CONVERGENCE_CRITERION_SCHEMA)
        return cls(
            edge_id=payload["edge_id"],
            relative_tolerance=payload["relative_tolerance"],
            absolute_tolerance=Quantity.from_dict(payload["absolute_tolerance"]),
            norm=ResidualNorm(payload.get("norm", "linf")),
        )


@dataclass(frozen=True)
class RelaxationPolicy:
    kind: RelaxationKind = RelaxationKind.NONE
    factor: float = 1.0
    minimum_factor: float = 0.05
    maximum_factor: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", RelaxationKind(self.kind))
        factor = float(self.factor)
        minimum = float(self.minimum_factor)
        maximum = float(self.maximum_factor)
        if not all(
            math.isfinite(value)
            for value in (factor, minimum, maximum)
        ):
            raise InvalidScientificProblem(
                "relaxation factor and bounds must be finite"
            )
        if not 0.0 < minimum <= maximum:
            raise InvalidScientificProblem(
                "relaxation bounds must satisfy 0 < min <= max"
            )
        if not minimum <= factor <= maximum:
            raise InvalidScientificProblem("relaxation factor must lie inside its bounds")
        if self.kind is RelaxationKind.NONE and factor != 1.0:
            raise InvalidScientificProblem("NONE relaxation has factor 1")
        object.__setattr__(self, "factor", factor)
        object.__setattr__(self, "minimum_factor", minimum)
        object.__setattr__(self, "maximum_factor", maximum)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RELAXATION_POLICY_SCHEMA,
            "kind": self.kind.value,
            "factor": self.factor,
            "minimum_factor": self.minimum_factor,
            "maximum_factor": self.maximum_factor,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RelaxationPolicy":
        require_schema(payload, RELAXATION_POLICY_SCHEMA)
        return cls(
            kind=RelaxationKind(payload.get("kind", "none")),
            factor=payload.get("factor", 1.0),
            minimum_factor=payload.get("minimum_factor", 0.05),
            maximum_factor=payload.get("maximum_factor", 1.0),
        )


@dataclass(frozen=True)
class CouplingPlan:
    plan_id: str
    scheme: CouplingScheme
    iteration_semantics: IterationSemantics
    time: TimePolicy
    participant_order: tuple[str, ...] = ()
    criteria: tuple[ConvergenceCriterion, ...] = ()
    relaxation: RelaxationPolicy = RelaxationPolicy()
    max_iterations: int = 1
    fail_on_nonconvergence: bool = True

    def __post_init__(self) -> None:
        plan_id = str(self.plan_id).strip()
        if not plan_id:
            raise InvalidScientificProblem("coupling plan requires plan_id")
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "scheme", CouplingScheme(self.scheme))
        object.__setattr__(self, "iteration_semantics", IterationSemantics(self.iteration_semantics))
        if not isinstance(self.time, TimePolicy):
            raise InvalidScientificProblem("coupling plan requires TimePolicy")
        order = tuple(str(item).strip() for item in self.participant_order)
        if any(not item for item in order) or len(order) != len(set(order)):
            raise InvalidScientificProblem("participant_order must contain unique non-empty ids")
        object.__setattr__(self, "participant_order", order)
        criteria = tuple(self.criteria)
        if any(not isinstance(c, ConvergenceCriterion) for c in criteria):
            raise InvalidScientificProblem("criteria must be ConvergenceCriterion records")
        if len({c.edge_id for c in criteria}) != len(criteria):
            raise InvalidScientificProblem("one convergence criterion per edge")
        object.__setattr__(self, "criteria", tuple(sorted(criteria, key=lambda c: c.edge_id)))
        if not isinstance(self.relaxation, RelaxationPolicy):
            raise InvalidScientificProblem("coupling plan requires RelaxationPolicy")
        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or self.max_iterations < 1:
            raise InvalidScientificProblem("max_iterations must be a positive int")
        if not isinstance(self.fail_on_nonconvergence, bool):
            raise InvalidScientificProblem("fail_on_nonconvergence must be boolean")
        if self.scheme is CouplingScheme.EXPLICIT:
            if self.max_iterations != 1:
                raise InvalidScientificProblem("explicit coupling executes one coupling iteration")
            if criteria:
                raise InvalidScientificProblem("explicit coupling has no coupling-convergence criteria")
            if self.relaxation.kind is not RelaxationKind.NONE:
                raise InvalidScientificProblem("explicit coupling does not relax an iteration")
        elif not criteria:
            raise InvalidScientificProblem("implicit coupling requires convergence criteria")

    def resolved_order(self, graph: PhysicsGraph) -> tuple[str, ...]:
        declared = tuple(self.participant_order)
        ids = {participant.participant_id for participant in graph.participants}
        if declared:
            if set(declared) != ids or len(declared) != len(ids):
                raise InvalidScientificProblem(
                    f"participant_order must name every graph participant exactly once; "
                    f"declared={list(declared)}, graph={sorted(ids)}"
                )
            return declared
        if self.iteration_semantics is IterationSemantics.JACOBI:
            return tuple(sorted(ids))
        if graph.cyclic:
            raise InvalidScientificProblem(
                "serial coupling over a cyclic PhysicsGraph requires explicit participant_order; "
                "Gauss-Seidel order changes the numerical method and cannot be hidden"
            )
        indegree = {pid: 0 for pid in ids}
        adjacency = {pid: set() for pid in ids}
        for edge in graph.edges:
            source = edge.source.participant_id
            target = edge.target.participant_id
            if source == target or target in adjacency[source]:
                continue
            adjacency[source].add(target)
            indegree[target] += 1
        ready = sorted(pid for pid, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for target in sorted(adjacency[node]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
                    ready.sort()
        if len(order) != len(ids):
            raise InvalidScientificProblem("failed to derive serial order from graph")
        return tuple(order)

    def validate_against(self, graph: PhysicsGraph) -> None:
        self.resolved_order(graph)
        for criterion in self.criteria:
            edge = graph.edge(criterion.edge_id)
            source = graph.participant(edge.source.participant_id).port(edge.source.port_id)
            if criterion.absolute_tolerance.dimensionality != source.dimension:
                raise InvalidScientificProblem(
                    f"criterion for {edge.edge_id!r} has "
                    f"[{criterion.absolute_tolerance.dimensionality}] but edge transports "
                    f"[{source.dimension}]"
                )
        if self.scheme is CouplingScheme.IMPLICIT:
            bad = [
                participant.participant_id
                for participant in graph.participants
                if not participant.checkpointable or not participant.deterministic_restore
            ]
            if bad:
                raise InvalidScientificProblem(
                    f"implicit coupling replays a time window and requires deterministic "
                    f"checkpoint/restore on every participant; missing on {bad}"
                )
        if self.time.align_events and any(p.event_capable for p in graph.participants):
            bad = [
                participant.participant_id
                for participant in graph.participants
                if not participant.checkpointable or not participant.deterministic_restore
            ]
            if bad:
                raise InvalidScientificProblem(
                    f"event alignment can roll back participants that already advanced; "
                    f"deterministic checkpoint/restore is required on all participants: {bad}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLING_PLAN_SCHEMA,
            "plan_id": self.plan_id,
            "scheme": self.scheme.value,
            "iteration_semantics": self.iteration_semantics.value,
            "time": self.time.to_dict(),
            "participant_order": list(self.participant_order),
            "criteria": [c.to_dict() for c in self.criteria],
            "relaxation": self.relaxation.to_dict(),
            "max_iterations": self.max_iterations,
            "fail_on_nonconvergence": self.fail_on_nonconvergence,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CouplingPlan":
        require_schema(payload, COUPLING_PLAN_SCHEMA)
        return cls(
            plan_id=payload["plan_id"],
            scheme=CouplingScheme(payload["scheme"]),
            iteration_semantics=IterationSemantics(payload["iteration_semantics"]),
            time=TimePolicy.from_dict(payload["time"]),
            participant_order=tuple(payload.get("participant_order", ())),
            criteria=tuple(ConvergenceCriterion.from_dict(c) for c in payload.get("criteria", ())),
            relaxation=RelaxationPolicy.from_dict(payload["relaxation"]),
            max_iterations=payload.get("max_iterations", 1),
            fail_on_nonconvergence=payload.get("fail_on_nonconvergence", True),
        )
