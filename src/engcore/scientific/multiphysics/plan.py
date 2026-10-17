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
WINDOW_CONTROL_SCHEMA = schema_string("multiphysics_window_control")


class CouplingScheme(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class IterationSemantics(str, Enum):
    SERIAL = "serial"
    JACOBI = "jacobi"


class ResidualNorm(str, Enum):
    #: max over stored values
    LINF = "linf"
    #: root mean square over STORED VALUES (every site weighted equally); on a
    #: non-uniform support this is not a measure-weighted L2 norm
    L2 = "l2"
    #: Phase 3 BR13: measure-weighted root mean square,
    #: sqrt(sum_i w_i d_i^2 / sum_i w_i), with w_i the cell measure (cell
    #: fields) or the lumped P1/Q1 nodal measure (node fields) of the support.
    #: Defined only for the supports the runtime can measure; refused elsewhere.
    L2_MEASURE = "l2_measure"


class RelaxationKind(str, Enum):
    NONE = "none"
    CONSTANT = "constant"
    AITKEN = "aitken"
    #: Interface quasi-Newton with inverse least-squares Jacobian over the
    #: joint interface vector of every edge (Jacobi coupling only; history
    #: reset every window).  Its update is not a scalar mix of two iterates, so
    #: no scalar factor is recorded and propagated uncertainty is UNKNOWN.
    IQN_ILS = "iqn_ils"
    #: Phase 3 BR14: interface quasi-Newton with a multi-vector inverse
    #: Jacobian (Bogaers et al. 2014; Lindner, Mehl, Uekermann 2017): the
    #: secant pairs of the current window update the approximation carried
    #: from the previous accepted window, J = J_prev + (W - J_prev V) V^+,
    #: instead of starting from zero.  Jacobi only; the dense approximation is
    #: bounded by ``imvj_max_dimension`` and carried across at most
    #: ``imvj_reuse_windows`` windows before it restarts.  Uncertainty UNKNOWN.
    IQN_IMVJ = "iqn_imvj"


#: Phase 3 BR14: the relaxation kinds that update the joint interface vector
IQN_KINDS = frozenset({RelaxationKind.IQN_ILS, RelaxationKind.IQN_IMVJ})


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
    #: IQN-ILS only: how many secant pairs (iterate differences) the
    #: least-squares Jacobian keeps; 0 for every other kind.
    iqn_columns: int = 0
    #: IQN-ILS only: QR filter threshold.  A secant column whose component
    #: orthogonal to the newer kept columns is below this fraction of its own
    #: norm adds (almost) nothing and is dropped; recorded in the policy.
    iqn_filter: float = 1e-10
    #: Phase 3 BR14, IQN-IMVJ only (0 otherwise): the largest joint interface
    #: dimension n whose dense n x n inverse-Jacobian approximation may be
    #: held; a larger interface is refused, never truncated.
    imvj_max_dimension: int = 0
    #: Phase 3 BR14, IQN-IMVJ only (0 otherwise): how many consecutive accepted
    #: windows may contribute to one carried approximation before it restarts
    #: from zero (bounded reuse of stale secant information).
    imvj_reuse_windows: int = 0

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
        columns = self.iqn_columns
        if isinstance(columns, bool) or not isinstance(columns, int) or columns < 0:
            raise InvalidScientificProblem("iqn_columns must be a non-negative int")
        if self.kind in IQN_KINDS:
            if not 1 <= columns <= 50:
                raise InvalidScientificProblem(f"{self.kind.value} requires iqn_columns in [1, 50]")
        elif columns != 0:
            raise InvalidScientificProblem("iqn_columns applies to IQN-ILS relaxation only (and to IQN-IMVJ)")
        qr_filter = float(self.iqn_filter)
        if not math.isfinite(qr_filter) or not 0.0 <= qr_filter < 1.0:
            raise InvalidScientificProblem("iqn_filter must lie in [0, 1)")
        if self.kind not in IQN_KINDS and qr_filter != 1e-10:
            raise InvalidScientificProblem("iqn_filter applies to IQN-ILS relaxation only (and to IQN-IMVJ)")
        object.__setattr__(self, "iqn_filter", qr_filter)
        for label, low, high in (("imvj_max_dimension", 1, 4096), ("imvj_reuse_windows", 1, 1000)):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidScientificProblem(f"{label} must be an int")
            if self.kind is RelaxationKind.IQN_IMVJ:
                if not low <= value <= high:
                    raise InvalidScientificProblem(
                        f"IQN-IMVJ requires {label} in [{low}, {high}]; it is never defaulted"
                    )
            elif value != 0:
                raise InvalidScientificProblem(f"{label} applies to IQN-IMVJ relaxation only")
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
            # absent for every other kind: existing policies keep their fingerprints
            **(
                {"iqn_columns": self.iqn_columns, "iqn_filter": self.iqn_filter}
                if self.kind in IQN_KINDS
                else {}
            ),
            **(
                {"imvj_max_dimension": self.imvj_max_dimension, "imvj_reuse_windows": self.imvj_reuse_windows}
                if self.kind is RelaxationKind.IQN_IMVJ
                else {}
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RelaxationPolicy":
        require_schema(payload, RELAXATION_POLICY_SCHEMA)
        return cls(
            kind=RelaxationKind(payload.get("kind", "none")),
            factor=payload.get("factor", 1.0),
            minimum_factor=payload.get("minimum_factor", 0.05),
            maximum_factor=payload.get("maximum_factor", 1.0),
            iqn_columns=payload.get("iqn_columns", 0),
            iqn_filter=payload.get("iqn_filter", 1e-10),
            imvj_max_dimension=payload.get("imvj_max_dimension", 0),
            imvj_reuse_windows=payload.get("imvj_reuse_windows", 0),
        )


@dataclass(frozen=True)
class WindowControlPolicy:
    """Bounded subdivision of a coupling window that did not converge.

    When a window ends at its iteration limit, diverges, or a participant
    reports that it did not converge internally, every participant is restored
    to the window start and the window is retried over
    ``reduction_factor`` times its previous width, at most
    ``max_subdivisions`` times and never below ``minimum_window``.  A window
    that still fails is reported exactly as it would be without this policy.

    Nothing here changes what a converged window means: the same criteria are
    applied to the shorter window, and every rejected attempt is recorded.
    ``minimum_window`` has no default -- how short a window may become is a
    numerical decision the plan states, not one the runtime makes.

    ``divergence_factor`` (optional, > 1): an implicit window whose residual on
    some edge grows past this multiple of its first-iteration residual is
    rejected early as diverging instead of exhausting ``max_iterations``.

    ``growth_factor`` (optional, in (1, 10]): step-size memory.  After a
    subdivided window is accepted, the following windows start at the accepted
    width and grow by this factor per accepted window, up to the nominal
    coupling window.  Unset, every window starts again at the nominal width.
    Events and input-change instants still cut windows exactly as before.

    ``stagnation_iterations`` (optional, int in [2, 1000], implicit only): an
    implicit window whose largest edge residual (normalized by its first
    iteration) has not improved on its earlier best for this many consecutive
    iterations is rejected early as stagnating, instead of spending
    ``max_iterations``.
    """

    minimum_window: Quantity
    reduction_factor: float = 0.5
    max_subdivisions: int = 4
    divergence_factor: float | None = None
    growth_factor: float | None = None
    stagnation_iterations: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "minimum_window", _time(self.minimum_window, label="minimum_window")
        )
        factor = float(self.reduction_factor)
        if not math.isfinite(factor) or not 0.0 < factor < 1.0:
            raise InvalidScientificProblem("window reduction_factor must lie in (0, 1)")
        object.__setattr__(self, "reduction_factor", factor)
        if (
            isinstance(self.max_subdivisions, bool)
            or not isinstance(self.max_subdivisions, int)
            or not 1 <= self.max_subdivisions <= 64
        ):
            raise InvalidScientificProblem("max_subdivisions must be an int in [1, 64]")
        if self.divergence_factor is not None:
            divergence = float(self.divergence_factor)
            if not math.isfinite(divergence) or divergence <= 1.0:
                raise InvalidScientificProblem("divergence_factor must be finite and > 1")
            object.__setattr__(self, "divergence_factor", divergence)
        if self.stagnation_iterations is not None and (
            isinstance(self.stagnation_iterations, bool)
            or not isinstance(self.stagnation_iterations, int)
            or not 2 <= self.stagnation_iterations <= 1000
        ):
            raise InvalidScientificProblem("stagnation_iterations must be an int in [2, 1000]")
        if self.growth_factor is not None:
            growth = float(self.growth_factor)
            if not math.isfinite(growth) or not 1.0 < growth <= 10.0:
                raise InvalidScientificProblem("growth_factor must lie in (1, 10]")
            object.__setattr__(self, "growth_factor", growth)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WINDOW_CONTROL_SCHEMA,
            "minimum_window": self.minimum_window.to_dict(),
            "reduction_factor": self.reduction_factor,
            "max_subdivisions": self.max_subdivisions,
            "divergence_factor": self.divergence_factor,
            # absent when unset: policies without step-size memory keep their identity
            **({"growth_factor": self.growth_factor} if self.growth_factor is not None else {}),
            **({"stagnation_iterations": self.stagnation_iterations} if self.stagnation_iterations is not None else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WindowControlPolicy":
        require_schema(payload, WINDOW_CONTROL_SCHEMA)
        return cls(
            minimum_window=Quantity.from_dict(payload["minimum_window"]),
            reduction_factor=payload["reduction_factor"],
            max_subdivisions=payload["max_subdivisions"],
            divergence_factor=payload.get("divergence_factor"),
            growth_factor=payload.get("growth_factor"),
            stagnation_iterations=payload.get("stagnation_iterations"),
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
    #: Optional adaptive subdivision of non-converging windows (None: fixed windows).
    window_control: WindowControlPolicy | None = None

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
            # Phase 1 BR1: this check belongs to the scheme test.  Attached to
            # the IQN-ILS test below (as it was), it refused every explicit plan.
            raise InvalidScientificProblem("implicit coupling requires convergence criteria")
        if (
            self.relaxation.kind in IQN_KINDS
            and self.iteration_semantics is not IterationSemantics.JACOBI
        ):
            # Phase 3 BR14: the same holds for IQN-IMVJ; no Gauss-Seidel IQN variant
            # is implemented, so none is admitted
            raise InvalidScientificProblem(
                f"{self.relaxation.kind.value} updates the joint interface vector after every participant has run "
                "(Jacobi); serial Gauss-Seidel relaxes edges one at a time and is not supported"
            )
        if self.window_control is not None:
            if not isinstance(self.window_control, WindowControlPolicy):
                raise InvalidScientificProblem("window_control must be a WindowControlPolicy")
            if (
                self.window_control.minimum_window.magnitude_in("second")
                > self.time.coupling_window.magnitude_in("second")
            ):
                raise InvalidScientificProblem("minimum_window exceeds the coupling window")
            if (
                self.window_control.divergence_factor is not None
                and self.scheme is not CouplingScheme.IMPLICIT
            ):
                raise InvalidScientificProblem(
                    "divergence_factor applies to implicit coupling iterations only"
                )
            if (
                self.window_control.stagnation_iterations is not None
                and self.scheme is not CouplingScheme.IMPLICIT
            ):
                raise InvalidScientificProblem(
                    "stagnation_iterations applies to implicit coupling iterations only"
                )

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

    def required_convergence_edges(self, graph: PhysicsGraph) -> tuple[str, ...]:
        """The edges whose fixed-point residual an IMPLICIT plan must monitor.

        An implicit window is a fixed-point iteration ``x = H(x)`` over the
        interface vector.  The window is a solution of the coupled equations
        only if every input a participant CONSUMED equals the transfer of the
        output it consumed.  Which edges can violate that is a property of the
        iteration semantics, so the policy is derived, never declared:

        * JACOBI: every edge.  Each participant reads the frozen previous
          iterate, so every edge is lagged by one iteration.
        * SERIAL with NONE relaxation: every LAGGED edge -- its target runs at
          or before its source in the resolved order (self-loops included), so
          the target read the previous iterate.  A forward edge delivers this
          iteration's transfer to a target that runs later in the same
          iteration; it is consistent by construction (up to the rounding of
          ``old + (new - old)``) and needs no criterion.
        * SERIAL with CONSTANT or AITKEN relaxation: every edge.  A relaxed
          forward edge delivers a mix of two iterates, not the transfer.

        EXPLICIT plans make no convergence claim and require nothing.  The
        residual is an iterate-consistency measure: it is not the solution's
        error, and it says nothing about physical conservation.
        """
        if self.scheme is CouplingScheme.EXPLICIT:
            return ()
        if (
            self.iteration_semantics is IterationSemantics.JACOBI
            or self.relaxation.kind is not RelaxationKind.NONE
        ):
            return tuple(sorted(edge.edge_id for edge in graph.edges))
        position = {pid: index for index, pid in enumerate(self.resolved_order(graph))}
        return tuple(sorted(
            edge.edge_id
            for edge in graph.edges
            if position[edge.target.participant_id] <= position[edge.source.participant_id]
        ))

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
        missing = sorted(
            set(self.required_convergence_edges(graph))
            - {criterion.edge_id for criterion in self.criteria}
        )
        if missing:
            # Phase 1 BR1: a window could otherwise be labelled CONVERGED while
            # an interface the iteration updates was never measured.
            raise InvalidScientificProblem(
                f"implicit {self.iteration_semantics.value} coupling with "
                f"{self.relaxation.kind.value} relaxation must monitor edges {missing}: "
                f"they carry a lagged or relaxed iterate, and an unmonitored one can "
                f"leave the coupled equations unsatisfied in a window reported as converged"
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
        if self.window_control is not None:
            bad = [
                participant.participant_id
                for participant in graph.participants
                if not participant.checkpointable or not participant.deterministic_restore
            ]
            if bad:
                raise InvalidScientificProblem(
                    f"window subdivision rolls every participant back to the window start; "
                    f"deterministic checkpoint/restore is required on all participants: {bad}"
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
            # absent when unset: plans without window control keep their fingerprints
            **(
                {"window_control": self.window_control.to_dict()}
                if self.window_control is not None
                else {}
            ),
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
            window_control=(
                WindowControlPolicy.from_dict(payload["window_control"])
                if payload.get("window_control") is not None
                else None
            ),
        )
