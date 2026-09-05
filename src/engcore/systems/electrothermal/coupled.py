"""Closed-loop electro-thermal coupling: the loop, and the records it produces.

`ET-VERTICAL`. The previous milestone represented the loop and stopped one
electrical solve short of closing it. This module closes it::

        seed T⁽⁰⁾
            ↓
    ┌── T⁽ⁿ⁾ ──▶ R(T⁽ⁿ⁾) ──▶ electrical solve ──▶ P⁽ⁿ⁾ ──▶ thermal solve ──┐
    │                                                                       │
    └──────────────────── T⁽ⁿ⁺¹⁾  ◀── iterate change |T⁽ⁿ⁺¹⁾ − T⁽ⁿ⁾| ◀──────┘

Iteration *n ≥ 2* solves the electrical problem at a resistance the previous
thermal solve produced. That is the whole difference from `run_open_loop_pass`,
and it is what makes this a coupled execution rather than a representation.

Why these records live here and not in ``engcore.scientific``
------------------------------------------------------------
Because no universal reader of them exists. There is no planner, no
execution-plan compiler and no scheduler anywhere in the platform, and all three
are deferred. `MIN-FOUNDATION-ET` added its one universal record because a
*measurement* showed no reader could recover the fact it carried; there is no
analogous measurement here, and "a second coupled domain pair could reuse this"
is an argument, not evidence. The promotion criterion is preregistered in
``docs/milestones/electrothermal-vertical-prereg.md`` §16: a second, materially different
coupled consumer written against these records **without editing them**.

The two future systems nearest the commercial target both bend the shape a
universal record would freeze now — 2:1 fan-in has no combination rule, and
convective transport makes the upstream side a runtime property of the sign of
the mass flow. Freezing a directed, single-scalar-tolerance shape on one
consumer would be deciding those on no evidence.

What the loop is, and is not
----------------------------
It is a Gauss–Seidel (Picard) fixed-point iteration over a torn dependency
cycle. It is **not** a scheduler, a participant registry, a transfer operator,
an interpolator, a relaxation framework or a coupling platform. There is no
relaxation factor, no damping, no acceleration, no rollback, no checkpointing,
no event handling and no time synchronization.

It is also **not time marching.** The thermal problem's initial condition is the
same in every iteration; the iterate is a *coupling* iterate, not a time level.
Advancing the initial condition between iterations would make
``|T⁽ⁿ⁺¹⁾ − T⁽ⁿ⁾|`` a time-stepping increment and reporting it as coupling
convergence would collapse the two. Two things prevent it:
:meth:`FixedPointCouplingPlan.check_against` refuses to seed an endpoint a
declared condition already determines, and every iteration's thermal provenance
records the same t₀.

How the loop knows what feeds what
----------------------------------
It reads the declared :class:`~engcore.scientific.composition.QuantityDependency`
records. Every transported value is looked up as

    ``result_of(dep.source_problem_id).values[dep.source_quantity]``

and delivered under ``dep.target_quantity``. **No metric name is constructed,
parsed or inferred inside the iteration.** Change a dependency's
``source_quantity`` to a different declared metric of the same dimension and the
loop transports something else and converges somewhere else — which is what
makes the records load-bearing rather than decorative, and is exercised by the
two configurations described below.

The execution order is likewise computed, not written down: the torn edges are
removed and the remainder is topologically sorted. With the edges declared here
that yields *properties → circuit → bodies*, but the loop never states it.

Two configurations, one field apart
-----------------------------------
The thermal problem publishes three kelvin-valued quantities — ``temperature``
(the state at t₀), ``final_temperature`` (t = duration) and
``steady_state_temperature`` (t → ∞). A dimension check cannot tell them apart.
Selecting the second gives the self-consistent end-of-interval state; selecting
the third gives the coupled steady state. They differ by 3.4 K on identical
inputs, and only the enumerated *name* separates them.

Offset units are refused, and precisely why
-------------------------------------------
``Quantity(0.001, "kelvin").magnitude_in("degC")`` is ``-273.149``, and ``degC``
has the same dimensionality as ``kelvin``, so no dimension check can see a
mismatch between them.

What that does **not** break is the arithmetic of the comparison. Both sides are
converted into one unit before subtraction, and an affine offset cancels in a
difference — so the loop would compute the right number even on an affine scale.
What it breaks is the **stored record**: ``largest_iterate_change`` is a
difference carried in a type that means an absolute value, and a consumer
calling ``.to("kelvin")`` on a ``degC`` delta gets ``273.15``. The comparison
unit must therefore be a **ratio scale** — zero maps to zero in the base unit —
which admits ``rankine`` and refuses ``degC`` without containing any temperature
knowledge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from ...domains.thermal_models import lumped as lump
from ...domains.electrical import material as mat
from ...domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    build_dc_problem,
    solve_circuit,
)
# Same non-exported import the sibling module already needs: the DC package
# publishes no metric-name helper (MIN-FOUNDATION-ET finding C-11). Reusing the
# sibling's constant rather than re-deriving the convention a second time keeps
# one source of truth per name inside this pack.
from ...domains.electrical.dc.problem import resistance_name
from ...scientific.composition import QuantityDependency
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.serialization import require_schema, schema_string
from ...scientific.twins.definition import (
    ScientificTwin,
    TwinDatum,
    TwinDatumRole,
    TwinKind,
)
from ...scientific.units.quantity import Quantity, registry
from ...scientific.units.validation import require_unit
from .resistor_body import RESISTOR_POWER_METRIC

__all__ = [
    "COUPLED_ITERATION_SCHEMA",
    "COUPLED_RUN_SCHEMA",
    "CoupledElectroThermalSystem",
    "CoupledIteration",
    "CoupledRun",
    "CoupledStage",
    "CouplingOutcome",
    "FIXED_POINT_PLAN_SCHEMA",
    "FixedPointCouplingPlan",
    "TORN_ENDPOINT_SCHEMA",
    "TornEndpoint",
    "build_coupled_twin",
    "coupled_dependencies",
    "coupled_problems",
    "cycle_edges",
    "edge_key",
    "execution_order",
    "is_ratio_scale",
    "nominal_plan",
    "run_fixed_point",
    "run_fixed_point_coupling",
    "shares_origin",
    "stage_problems",
]

TORN_ENDPOINT_SCHEMA = schema_string("electrothermal_torn_endpoint")
FIXED_POINT_PLAN_SCHEMA = schema_string("electrothermal_fixed_point_plan")
COUPLED_ITERATION_SCHEMA = schema_string("electrothermal_coupled_iteration")
COUPLED_RUN_SCHEMA = schema_string("electrothermal_coupled_run")

#: Prose labels for the declared edges. Nothing branches on them.
DEPENDENCY_HEAT = "joule-dissipation-heats-body"
DEPENDENCY_TEMPERATURE = "body-temperature-sets-property-state"
DEPENDENCY_RESISTANCE = "property-resistance-sets-circuit-element"

SOURCE_ID = "V1"
REFERENCE_NODE = "gnd"


# =====================================================================
# Unit admissibility — required change 1
# =====================================================================

def is_ratio_scale(unit: str) -> bool:
    """Does zero of this unit map to zero of its base unit?

    A ratio scale can be subtracted and its difference stored under its own
    unit; an affine scale cannot. The test is structural and carries no
    knowledge of any particular dimension: ``rankine`` passes and ``degC`` does
    not, for the same reason and by the same arithmetic.

    **What this does and does not protect, stated precisely.** The arithmetic
    of the comparison is safe without it: both sides are converted into one unit
    before subtraction, and an affine offset cancels in a difference. What it
    protects is the **stored record**. ``largest_iterate_change`` is a
    *difference* carried in a type that means an *absolute value*, so a
    consumer holding a `4.7e-7 degC` delta and calling ``.to("kelvin")`` on it
    would get `273.15`. Refusing an affine scale for the comparison unit is
    what keeps that record convertible.

    **One provider dependency, recorded rather than hidden.** This reaches past
    the ``Quantity`` contract into the units backend through the units module's
    own ``registry()`` accessor, because the contract publishes no way to name a
    dimension's base unit. A backend without ``get_base_units`` would break this
    function. It is the only such call in this module, it is in a system pack
    and not in universal core, and :meth:`FixedPointCouplingPlan.__post_init__`
    additionally applies a pairwise check that uses published contract alone.
    """
    normalized = require_unit(unit, context="coupling comparison unit")
    _, base = registry().get_base_units(normalized)
    return Quantity(0.0, normalized).magnitude_in(str(base)) == 0.0


def shares_origin(unit: str, other: str) -> bool:
    """Do these two compatible units share a zero?

    Published contract only — no units-backend call. It catches the mixed pair
    (a tolerance in kelvin against an edge declared in ``degC``, or the
    reverse), which is the case where a conversion actually happens. It cannot
    catch a wholly affine composition, where every conversion is the identity
    and only the stored label is misleading; :func:`is_ratio_scale` covers that.
    """
    return Quantity(0.0, unit).magnitude_in(other) == 0.0


def _require_ratio_scale(unit: str, *, label: str) -> str:
    normalized = require_unit(unit, context=label)
    if not is_ratio_scale(normalized):
        raise InvalidScientificProblem(
            f"{label} may not use {unit!r}: its zero is conventional, so a "
            f"difference expressed in it is not a value of that unit and does "
            f"not survive conversion. Use a ratio scale, whose zero maps to "
            f"zero in its base unit"
        )
    return normalized


def edge_key(dependency: QuantityDependency) -> tuple[str, str, str, str]:
    """The identity of an edge: its two endpoints, and nothing else.

    One notion of edge identity, used everywhere. An earlier form tested torn
    membership by whole-record equality and computed the uncut set by this quad,
    so two records differing only in ``unit_exemplar`` were distinct for one
    purpose and identical for the other — the near-duplicate hazard
    `MIN-FOUNDATION-ET` recorded as known unknown 6, met for the first time.
    """
    return (
        dependency.source_problem_id,
        dependency.source_quantity,
        dependency.target_problem_id,
        dependency.target_quantity,
    )


# =====================================================================
# The plan — declarative, pre-execution, inspectable
# =====================================================================

class CouplingOutcome(str, Enum):
    """Why the coupling iteration stopped. **Never a scientific verdict.**

    Deliberately **not** :class:`~engcore.scientific.solvers.protocol.ConvergenceState`.
    Both closed-form participants here report ``NOT_APPLICABLE``, which
    ``RawSolverOutput.succeeded`` and ``ScientificResult.is_usable`` treat as
    success; reusing that enum would make "the coupled loop converged" and "a
    closed-form evaluation happened" the same serialized token, permanently, on
    a record that is already at ``scientific_result/2``.

    Members are limited to the ones this milestone actually executes. A
    ``DIVERGED`` member is deliberately absent: nothing here implements a
    divergence test, and `MODEL0-R` already had to delete an enum member
    (``SURROGATE``) that was minted from intuition.
    """

    CRITERION_MET = "criterion_met"
    ITERATION_LIMIT_REACHED = "iteration_limit_reached"


@dataclass(frozen=True)
class TornEndpoint:
    """One cut edge of the dependency cycle, paired with the seed it needs.

    The pairing is **structural**, not positional: two parallel tuples of
    dependencies and seeds would carry the association in an index, which is
    exactly the defect ``ExecutionBinding`` exists to prevent one level down.

    The seed supplies ``dependency.target_quantity`` of
    ``dependency.target_problem_id`` at iteration 1. It is not recoverable from
    any record — see ``docs/milestones/electrothermal-vertical-evidence.md`` §4 — and it is
    deliberately not inferred.
    """

    dependency: QuantityDependency
    initial_value: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.dependency, QuantityDependency):
            raise InvalidScientificProblem(
                "torn endpoint requires a QuantityDependency"
            )
        if not isinstance(self.initial_value, Quantity):
            raise InvalidScientificProblem(
                "torn endpoint seed must be a Quantity — a bare number carries "
                "no unit and cannot be checked against the edge it seeds"
            )
        if self.initial_value.dimensionality != self.dependency.dimension:
            raise InvalidScientificProblem(
                f"torn endpoint seed carries {self.initial_value.units!r} "
                f"[{self.initial_value.dimensionality}] but the edge transports "
                f"{self.dependency.unit_exemplar!r} [{self.dependency.dimension}]"
            )

    @property
    def endpoint(self) -> tuple[str, str]:
        """``(problem_id, quantity)`` of the endpoint this seed supplies."""
        return (self.dependency.target_problem_id, self.dependency.target_quantity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TORN_ENDPOINT_SCHEMA,
            "dependency": self.dependency.to_dict(),
            "initial_value": self.initial_value.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TornEndpoint":
        require_schema(payload, TORN_ENDPOINT_SCHEMA)
        return cls(
            dependency=QuantityDependency.from_dict(payload["dependency"]),
            initial_value=Quantity.from_dict(payload["initial_value"]),
        )


@dataclass(frozen=True)
class FixedPointCouplingPlan:
    """Everything needed to execute a cyclic dependency set, stated before it runs.

    A dependency set that contains a cycle has **zero** admissible execution
    orders. Making it executable requires four facts that no existing record
    carries: which edges are cut, what value each cut edge's target takes at
    iteration 1, when to stop, and how long to try. This record carries exactly
    those and nothing else.

    It is a record rather than a set of keyword arguments for the same reason
    ``QuantityDependency`` is: it must be inspectable *before* anything runs.
    A ``float`` tolerance additionally could not be checked at all — the
    dimension check against the torn edge, and the refusal of an affine scale,
    are only possible because the tolerance carries its unit.
    """

    plan_id: str
    dependencies: tuple[QuantityDependency, ...]
    torn: tuple[TornEndpoint, ...]
    absolute_tolerance: Quantity
    max_iterations: int

    def __post_init__(self) -> None:
        plan_id = str(self.plan_id).strip()
        if not plan_id:
            raise InvalidScientificProblem("coupling plan requires a plan_id")
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "torn", tuple(self.torn))

        if not self.dependencies:
            raise InvalidScientificProblem(
                "a coupling plan over no dependencies composes nothing"
            )
        if not self.torn:
            raise InvalidScientificProblem(
                "a coupling plan must cut at least one edge; an uncut cycle has "
                "no admissible execution order"
            )

        declared = {edge_key(d) for d in self.dependencies}
        for endpoint in self.torn:
            if edge_key(endpoint.dependency) not in declared:
                raise InvalidScientificProblem(
                    f"torn edge {endpoint.dependency.name or endpoint.endpoint!r} "
                    f"is not one of the plan's declared dependencies; cutting an "
                    f"edge the composition does not contain states nothing"
                )

        # Fan-in is REPORTED as unrepresentable, never resolved by accident.
        #
        # Two edges into one endpoint are individually valid records — each
        # checks clean, and MIN-FOUNDATION-ET measured exactly that. What no
        # record states is how to combine them: sum, override, or split. A
        # dict of transported values keyed by target quantity would resolve it
        # silently by declaration order, which is a combination rule invented
        # from one consumer and hidden in an insertion order. Refused instead,
        # in the same voice as the mixed-dimension refusal below.
        for label, keys in (
            (
                "dependencies",
                [(d.target_problem_id, d.target_quantity) for d in self.dependencies],
            ),
            ("torn edges", [e.endpoint for e in self.torn]),
        ):
            duplicated = sorted({k for k in keys if keys.count(k) > 1})
            if duplicated:
                raise InvalidScientificProblem(
                    f"{len(duplicated)} endpoint(s) receive more than one of "
                    f"this plan's {label}: {duplicated}. No record states "
                    f"whether they sum, override or split, so the composition "
                    f"is refused rather than combined by invention"
                )

        if not isinstance(self.absolute_tolerance, Quantity):
            raise InvalidScientificProblem(
                "coupling tolerance must be a Quantity — the criterion belongs "
                "to coupling execution and a bare float cannot be checked "
                "against the quantity it stops"
            )
        magnitude = self.absolute_tolerance.magnitude
        if not math.isfinite(magnitude) or magnitude <= 0.0:
            raise InvalidScientificProblem(
                f"coupling tolerance must be finite and strictly positive, got "
                f"{magnitude!r} {self.absolute_tolerance.units}"
            )
        _require_ratio_scale(
            self.absolute_tolerance.units, label="coupling tolerance"
        )

        dimensions = {e.dependency.dimension for e in self.torn}
        if len(dimensions) != 1:
            raise InvalidScientificProblem(
                f"the torn edges transport {len(dimensions)} different "
                f"dimensions ({sorted(dimensions)}); one scalar tolerance "
                f"cannot serve them and no record states how to normalize "
                f"between them. Refused rather than normalized by invention"
            )
        (dimension,) = dimensions
        if self.absolute_tolerance.dimensionality != dimension:
            raise InvalidScientificProblem(
                f"coupling tolerance carries "
                f"{self.absolute_tolerance.units!r} "
                f"[{self.absolute_tolerance.dimensionality}] but the torn edges "
                f"transport [{dimension}]"
            )
        # Published-contract check, in addition to the backend-assisted one:
        # the tolerance and every torn edge must share a zero, or a conversion
        # between them is not a conversion of a difference.
        for endpoint in self.torn:
            for unit in (
                endpoint.dependency.unit_exemplar,
                endpoint.initial_value.units,
            ):
                if not shares_origin(unit, self.absolute_tolerance.units):
                    raise InvalidScientificProblem(
                        f"{unit!r} and {self.absolute_tolerance.units!r} do not "
                        f"share a zero, so a difference converted between them "
                        f"is not a difference"
                    )

        budget = int(self.max_iterations)
        if budget < 1:
            raise InvalidScientificProblem(
                f"coupling budget must allow at least one iteration, got {budget}"
            )
        object.__setattr__(self, "max_iterations", budget)

    @property
    def comparison_unit(self) -> str:
        """The one unit both sides of every comparison are converted into."""
        return self.absolute_tolerance.units

    @property
    def torn_endpoints(self) -> tuple[tuple[str, str], ...]:
        return tuple(e.endpoint for e in self.torn)

    @property
    def uncut(self) -> tuple[QuantityDependency, ...]:
        """The dependencies that remain, and are therefore ordered, not seeded."""
        cut = {edge_key(e.dependency) for e in self.torn}
        return tuple(d for d in self.dependencies if edge_key(d) not in cut)

    def unsupplied(
        self, problems: Iterable[ScientificProblem]
    ) -> tuple[tuple[str, str, str], ...]:
        """Inputs this plan supplies no edge for. **Reported, never refused.**

        Core's :func:`externally_imposed` answers this, and its answer is
        deliberately ambiguous: an input with no supplier is either genuinely
        imposed by the environment or forgotten, and **no record distinguishes
        the two**. An ambient temperature and a missing heat source read
        identically here.

        So this reports and the caller decides. A plan that omits a required
        edge is therefore *not* refused before the first iteration — which is a
        measured limitation of the records, recorded rather than papered over,
        and the reason the failure surfaces from the executor instead.
        """
        from ...scientific.composition import externally_imposed

        return externally_imposed(problems, self.dependencies)

    def check_against(
        self, problems: Iterable[ScientificProblem]
    ) -> tuple[str, ...]:
        """Every reason this plan cannot be executed against these problems.

        Reported before the first iteration. A dependency that names a quantity
        no record enumerates, or transports a dimension the endpoint does not
        carry, is a **malformed declaration** — not a scientific finding — so
        the caller raises on a non-empty result rather than recording it.

        Sources that are result metrics cannot be checked here: they do not
        exist until a solve has produced them. The asymmetry is real and is not
        papered over.
        """
        by_id = {p.problem_id: p for p in problems}
        issues: list[str] = []
        for dependency in self.dependencies:
            for side, problem_id in (
                ("target", dependency.target_problem_id),
                ("source", dependency.source_problem_id),
            ):
                if problem_id not in by_id:
                    issues.append(
                        f"{side} problem {problem_id!r} is not part of the "
                        f"composition"
                    )
            target = by_id.get(dependency.target_problem_id)
            if target is not None:
                for issue in dependency.check_against(target_problem=target):
                    issues.append(
                        f"{issue.kind.value}: {issue.name}: {issue.detail}"
                    )

        # A torn endpoint whose target is already determined by a declared
        # condition is refused. The seed would override the condition, and for
        # a STATE variable pinned by an initial condition that override is
        # precisely time marching wearing the name of coupling.
        for endpoint in self.torn:
            target = by_id.get(endpoint.dependency.target_problem_id)
            if target is None:
                continue
            determined = {c.variable for c in target.initial_conditions}
            determined |= {c.variable for c in target.boundary_conditions}
            if endpoint.dependency.target_quantity in determined:
                issues.append(
                    f"seeded_over_condition: "
                    f"{endpoint.dependency.target_quantity}: problem "
                    f"{target.problem_id!r} already determines it by a declared "
                    f"condition; seeding it would override the condition, and "
                    f"for a state variable that is time marching rather than "
                    f"coupling"
                )
        return tuple(issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIXED_POINT_PLAN_SCHEMA,
            "plan_id": self.plan_id,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "torn": [e.to_dict() for e in self.torn],
            "absolute_tolerance": self.absolute_tolerance.to_dict(),
            "max_iterations": self.max_iterations,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FixedPointCouplingPlan":
        require_schema(payload, FIXED_POINT_PLAN_SCHEMA)
        return cls(
            plan_id=payload["plan_id"],
            dependencies=tuple(
                QuantityDependency.from_dict(d) for d in payload["dependencies"]
            ),
            torn=tuple(TornEndpoint.from_dict(e) for e in payload["torn"]),
            absolute_tolerance=Quantity.from_dict(payload["absolute_tolerance"]),
            max_iterations=payload["max_iterations"],
        )


# =====================================================================
# Graph readers — pure, and they report rather than decide
# =====================================================================

def _edges(dependencies: Iterable[QuantityDependency]) -> list[tuple[str, str]]:
    return [(d.source_problem_id, d.target_problem_id) for d in dependencies]


def execution_order(
    problem_ids: Sequence[str], dependencies: Iterable[QuantityDependency]
) -> tuple[str, ...]:
    """A deterministic order in which these problems may be solved.

    Kahn's algorithm with a sorted tie-break, so the order is a function of the
    records and not of insertion. Returns an empty tuple when no order exists —
    which is the answer for a cycle, not an error, because reporting that a
    composition is cyclic is exactly what a reader of a composition is for.

    It **reports**. It never chooses which edge to cut: three edges of a
    3-cycle are equally admissible tears, nothing in any record ranks them, and
    the only rule that would select one keys on a domain modelling a computed
    quantity as a configured parameter — an undeclared accident, not a law.
    """
    remaining = {str(p) for p in problem_ids}
    incoming: dict[str, int] = {p: 0 for p in remaining}
    outgoing: dict[str, list[str]] = {p: [] for p in remaining}
    for source, target in _edges(dependencies):
        if source not in remaining or target not in remaining or source == target:
            continue
        outgoing[source].append(target)
        incoming[target] += 1

    ready = sorted(p for p in remaining if incoming[p] == 0)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for target in sorted(outgoing[node]):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort()
    return tuple(order) if len(order) == len(remaining) else ()


def cycle_edges(
    problem_ids: Sequence[str], dependencies: Iterable[QuantityDependency]
) -> tuple[QuantityDependency, ...]:
    """The dependencies that lie on the cyclic core. Reports; chooses nothing.

    Computed by peeling: repeatedly discard any node with no incoming edges
    (nothing feeds it, so it cannot be downstream of a cycle) and any node with
    no outgoing edges (it feeds nothing, so it cannot be upstream of one). What
    remains is exactly the part of the graph a topological order cannot reach,
    and the edges among it are the ones that must be cut.

    An earlier form asked :func:`execution_order` for the settled set — which
    that function discards whenever an order does not exist — so on any cyclic
    graph the settled set was empty and **every** edge was reported as cyclic.
    On this milestone's own composition, a pure 3-cycle, that was
    indistinguishable from the right answer. It was wrong for `A→B, B→C, C→B`,
    where it named `A→B`.
    """
    nodes = {str(p) for p in problem_ids}
    edges = [
        d
        for d in dependencies
        if d.source_problem_id in nodes
        and d.target_problem_id in nodes
        and d.source_problem_id != d.target_problem_id
    ]
    remaining = set(nodes)
    while True:
        sources = {d.source_problem_id for d in edges
                   if d.source_problem_id in remaining
                   and d.target_problem_id in remaining}
        targets = {d.target_problem_id for d in edges
                   if d.source_problem_id in remaining
                   and d.target_problem_id in remaining}
        core = remaining & sources & targets
        if core == remaining:
            break
        remaining = core
        if not remaining:
            break
    return tuple(
        d
        for d in edges
        if d.source_problem_id in remaining and d.target_problem_id in remaining
    )


# =====================================================================
# The system declaration
# =====================================================================

@dataclass(frozen=True)
class CoupledStage:
    """One conductor and the thermal body it dissipates into.

    The two share a ``component_id``, and that co-identity remains a
    **convention of this pack**: no universal record states that a conductor
    declaration and a body declaration describe one physical object. A
    ``ComponentInstance`` to state it was tested and deferred at arity 1 by
    `MIN-FOUNDATION-ET`; this milestone runs it at arity 2 to find out whether
    arity forces it.
    """

    conductor: mat.TemperatureDependentConductor
    body: lump.ThermalBody

    def __post_init__(self) -> None:
        if not isinstance(self.conductor, mat.TemperatureDependentConductor):
            raise InvalidScientificProblem(
                "stage conductor must be a TemperatureDependentConductor"
            )
        if not isinstance(self.body, lump.ThermalBody):
            raise InvalidScientificProblem("stage body must be a ThermalBody")
        if self.conductor.component_id != self.body.body_id:
            raise InvalidScientificProblem(
                f"conductor {self.conductor.component_id!r} and body "
                f"{self.body.body_id!r} must share an id in this system pack; "
                f"no universal record states that two declarations describe one "
                f"physical object, so this pack keeps them aligned by "
                f"construction"
            )

    @property
    def component_id(self) -> str:
        return self.conductor.component_id


@dataclass(frozen=True)
class CoupledElectroThermalSystem:
    """N self-heating conductors in series across one ideal source.

    Series, deliberately. Across an ideal voltage source, parallel elements do
    not interact, and a multiplicity case in which the instances cannot
    influence each other exercises nothing. In series, heating one conductor
    changes the loop current, which changes every other conductor's
    dissipation — so the N coupling cycles are genuinely coupled through the
    circuit and an identity confusion between them would change the answer.

    With ``N = 1`` this is exactly the physics of `MIN-FOUNDATION-ET`'s
    single-resistor system.
    """

    stages: tuple[CoupledStage, ...]
    source_voltage: Quantity
    system_id: str = "electrothermal-series"

    def __post_init__(self) -> None:
        object.__setattr__(self, "stages", tuple(self.stages))
        if not self.stages:
            raise InvalidScientificProblem("a coupled system requires a stage")
        seen: set[str] = set()
        for stage in self.stages:
            if not isinstance(stage, CoupledStage):
                raise InvalidScientificProblem("stages must be CoupledStage")
            if stage.component_id in seen:
                raise InvalidScientificProblem(
                    f"duplicate component id {stage.component_id!r}: two stages "
                    f"sharing an id would alias every endpoint that names it"
                )
            seen.add(stage.component_id)
        if not isinstance(self.source_voltage, Quantity):
            raise InvalidScientificProblem("source_voltage must be a Quantity")
        self.source_voltage.require_compatible(
            "volt", context="coupled source voltage"
        )

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(s.component_id for s in self.stages)

    @property
    def circuit_id(self) -> str:
        return f"{self.system_id}-{'-'.join(self.component_ids)}"

    def power_metric(self, component_id: str) -> str:
        """The DC domain's published power metric for one element."""
        return RESISTOR_POWER_METRIC.format(component_id=component_id)

    def _node_ids(self) -> tuple[str, ...]:
        """``n0 … n(N-1)`` plus the reference. ``n0`` is the source's positive."""
        return tuple(f"n{i}" for i in range(len(self.stages))) + (REFERENCE_NODE,)

    def circuit_at(self, resistances: Mapping[str, Quantity]) -> DCCircuit:
        """The series circuit with every element set to one evaluated value."""
        nodes = self._node_ids()
        resistors = []
        for index, stage in enumerate(self.stages):
            try:
                value = resistances[stage.component_id]
            except KeyError:
                raise InvalidScientificProblem(
                    f"no resistance supplied for {stage.component_id!r}"
                ) from None
            resistors.append(
                Resistor(stage.component_id, nodes[index], nodes[index + 1], value)
            )
        return DCCircuit(
            circuit_id=self.circuit_id,
            nodes=tuple(
                ElectricalNode(n, is_reference=(n == REFERENCE_NODE)) for n in nodes
            ),
            resistors=tuple(resistors),
            voltage_sources=(
                DCVoltageSource(
                    SOURCE_ID, nodes[0], REFERENCE_NODE, self.source_voltage
                ),
            ),
        )


# =====================================================================
# Representation
# =====================================================================

def coupled_problems(
    system: CoupledElectroThermalSystem, resistances: Mapping[str, Quantity]
) -> tuple[ScientificProblem, ...]:
    """``(electrical, property…, thermal…)`` — ``2N + 1`` separately posed problems.

    The electrical resistance has to be supplied to *build* the electrical
    problem, because the DC domain carries it as a configured
    ``ScientificParameter`` and folds it into the circuit's canonical identity.
    That is the configuration/state conflation `MIN-FOUNDATION-ET` measured; it
    is why every iteration builds a **fresh** electrical problem, and why the
    problem *record* differs between iterations while its ``problem_id`` does
    not.
    """
    problems = [build_dc_problem(system.circuit_at(resistances))]
    for _, prop, thermal in stage_problems(system):
        problems += [prop, thermal]
    return tuple(problems)


def stage_problems(
    system: CoupledElectroThermalSystem,
) -> tuple[tuple[CoupledStage, ScientificProblem, ScientificProblem], ...]:
    """``(stage, property problem, thermal problem)``, associated structurally.

    The one place the correspondence between a declared stage and the two
    problems posed for it is stated. An earlier form returned a flat tuple and
    let three separate functions recover the correspondence by slicing it —
    ``problems[1:1+n]`` and ``problems[1+n:1+2n]`` — which is the positional
    association ``ExecutionBinding`` exists to prevent and which
    :class:`TornEndpoint`'s own docstring argues against. A caller passing a
    reordered sequence got a silently mis-wired composition that still
    converged.
    """
    return tuple(
        (
            stage,
            mat.build_resistance_problem(stage.conductor),
            lump.build_lumped_thermal_problem(stage.body),
        )
        for stage in system.stages
    )


def coupled_dependencies(
    system: CoupledElectroThermalSystem,
    problems: Sequence[ScientificProblem],
    *,
    temperature_metric: str = lump.TEMPERATURE_METRIC,
) -> tuple[QuantityDependency, ...]:
    """``3N`` directed edges: dissipation heats, temperature sets, resistance sets.

    ``temperature_metric`` selects which of the thermal problem's kelvin-valued
    result metrics is transported. It is the **only** difference between the
    end-of-interval configuration and the coupled-steady-state configuration,
    and the two converge to different temperatures. A dimension check cannot
    distinguish them; only the enumerated name can.
    """
    declared = {p.problem_id for p in problems}
    electrical = next(
        (p for p in problems if p.problem_id.startswith("electrical_dc:")), None
    )
    if electrical is None:
        raise InvalidScientificProblem(
            "the supplied problems contain no electrical analysis to wire into"
        )

    edges: list[QuantityDependency] = []
    for stage, prop, thermal in stage_problems(system):
        cid = stage.component_id
        for problem in (prop, thermal):
            if problem.problem_id not in declared:
                raise InvalidScientificProblem(
                    f"stage {cid!r} poses problem {problem.problem_id!r}, which "
                    f"is not among the supplied problems; the correspondence "
                    f"between a stage and its problems is stated, not inferred "
                    f"from position"
                )
        edges.append(
            QuantityDependency(
                source_problem_id=electrical.problem_id,
                source_quantity=system.power_metric(cid),
                target_problem_id=thermal.problem_id,
                target_quantity=lump.HEAT_INPUT,
                unit_exemplar=lump.POWER_UNIT,
                name=f"{DEPENDENCY_HEAT}:{cid}",
                description=(
                    "The power absorbed by this element is the heat delivered "
                    "to the body it is thermally represented by."
                ),
            )
        )
        edges.append(
            QuantityDependency(
                source_problem_id=thermal.problem_id,
                source_quantity=temperature_metric,
                target_problem_id=prop.problem_id,
                target_quantity=mat.TEMPERATURE,
                unit_exemplar=mat.TEMPERATURE_UNIT,
                name=f"{DEPENDENCY_TEMPERATURE}:{cid}",
                description=(
                    "The body temperature is the state coordinate at which "
                    "this conductor's resistance is evaluated."
                ),
            )
        )
        edges.append(
            QuantityDependency(
                source_problem_id=prop.problem_id,
                source_quantity=mat.RESISTANCE_METRIC,
                target_problem_id=electrical.problem_id,
                target_quantity=resistance_name(cid),
                unit_exemplar=mat.RESISTANCE_UNIT,
                name=f"{DEPENDENCY_RESISTANCE}:{cid}",
                description=(
                    "The evaluated resistance is the value this circuit "
                    "element takes."
                ),
            )
        )
    return tuple(edges)


def nominal_plan(
    system: CoupledElectroThermalSystem,
    dependencies: Sequence[QuantityDependency],
    *,
    seed: Quantity,
    tolerance: Quantity = Quantity(1e-6, "kelvin"),
    max_iterations: int = 50,
    plan_id: str | None = None,
) -> FixedPointCouplingPlan:
    """Build the plan this milestone's cases use: cut every temperature edge.

    **This is a caller-side convenience and it does select a tear by a rule** —
    ``d.target_quantity == mat.TEMPERATURE``. Saying it is "stated, never
    inferred" would be false of *this* function; what is true, and what the
    constraint actually requires, is that **the loop and the graph readers
    infer nothing**: :func:`execution_order` reports three admissible tears per
    cycle and ranks none, and :class:`FixedPointCouplingPlan` accepts whatever
    tear it is handed. The choice is made here, by a caller, and is then a
    typed field of a record rather than control flow.

    The rule is also narrower than it reads: ``mat.TEMPERATURE`` and
    ``lump.TEMPERATURE`` are **both** the string ``"temperature"``, so an edge
    targeting the thermal problem's ``temperature`` *state variable* would
    match this filter too. That edge is refused by
    :meth:`FixedPointCouplingPlan.check_against`, because seeding a quantity a
    declared initial condition already determines is time marching wearing the
    name of coupling.
    """
    torn = tuple(
        TornEndpoint(dependency=d, initial_value=seed)
        for d in dependencies
        if d.target_quantity == mat.TEMPERATURE
    )
    return FixedPointCouplingPlan(
        plan_id=plan_id or f"{system.system_id}-fixed-point",
        dependencies=tuple(dependencies),
        torn=torn,
        absolute_tolerance=tolerance,
        max_iterations=max_iterations,
    )


def build_coupled_twin(
    system: CoupledElectroThermalSystem,
    *,
    twin_id: str | None = None,
    version: str = "0.1.0",
) -> ScientificTwin:
    """The scientific instance description. **Not the runtime state.**

    The twin is immutable and versioned. It is built once, it is not an input to
    :func:`run_fixed_point_coupling`, and it is not re-versioned per iteration.
    A coupling iterate is not a scientific declaration: it is a working value
    that exists only while the loop runs and is superseded by the next one.
    Making the twin carry it would require one twin version per iteration for a
    single interval — ten of them for the nominal case — and would give
    ``ScientificTwin`` a second meaning.
    """
    declarations: list[TwinDatum] = [
        TwinDatum(
            name=f"source_voltage:{SOURCE_ID}",
            value=system.source_voltage,
            role=TwinDatumRole.CONTROL,
        )
    ]
    models: list[ModelReference] = [
        ModelReference(mat.LINEAR_TCR_MODEL.model_id, mat.LINEAR_TCR_MODEL.version),
        ModelReference(
            lump.LUMPED_CAPACITY_MODEL.model_id, lump.LUMPED_CAPACITY_MODEL.version
        ),
    ]
    for stage in system.stages:
        cid = stage.component_id
        conductor, body = stage.conductor, stage.body
        declarations += [
            TwinDatum(f"reference_resistance:{cid}", conductor.reference_resistance,
                      TwinDatumRole.PARAMETER),
            TwinDatum(f"temperature_coefficient:{cid}",
                      conductor.temperature_coefficient, TwinDatumRole.PARAMETER),
            TwinDatum(f"reference_temperature:{cid}",
                      conductor.reference_temperature, TwinDatumRole.PARAMETER),
            TwinDatum(f"heat_capacity:{cid}", body.heat_capacity,
                      TwinDatumRole.PARAMETER),
            TwinDatum(f"ambient_conductance:{cid}", body.ambient_conductance,
                      TwinDatumRole.PARAMETER),
            TwinDatum(f"ambient_temperature:{cid}", body.ambient_temperature,
                      TwinDatumRole.OPERATING_CONDITION),
            TwinDatum(f"temperature:{cid}", body.initial_temperature,
                      TwinDatumRole.STATE,
                      description="Body temperature at the start of the interval."),
        ]
    return ScientificTwin(
        twin_id=twin_id or system.system_id,
        version=version,
        kind=TwinKind.CONCEPT,
        name="Self-heating conductors in series with lumped thermal bodies",
        description=(
            "N conductors whose resistance depends on their temperature, each "
            "thermally represented as a lumped body exchanging with an ambient, "
            "in series across an ideal DC voltage source."
        ),
        models=tuple(models),
        declarations=tuple(declarations),
        assumptions=(
            "each conductor and its thermal body are the same physical object",
            "the whole dissipated power of an element enters its body",
            "the resistance is evaluated at the transported temperature and "
            "held constant over the integrated interval",
        ),
    )


# =====================================================================
# The executed loop
# =====================================================================

@dataclass(frozen=True)
class CoupledIteration:
    """One pass of the loop: what was solved, and how far the iterate moved.

    ``results`` carries every :class:`ScientificResult` produced in this pass,
    so the value that crossed any declared edge is recoverable as
    ``result_for(dep.source_problem_id).values[dep.source_quantity]``. A
    companion ``CouplingTransfer`` record was designed and dropped for exactly
    that reason: it would have restated what these results already say.

    ``largest_iterate_change`` is the **change in the iterate**, not the
    residual of any equation. Those are different quantities: the iterate
    change measures how far a Gauss–Seidel sweep moved, and the residual
    measures how far the coupled system is from being satisfied. Nothing here
    computes the second, so nothing here may be named for it.

    It is a **difference** stored in a type that means an absolute value.
    ``Quantity`` draws no interval/ratio distinction, so a consumer could call
    ``.to()`` on it with an affine target and get nonsense. The plan's
    ratio-scale refusal is what keeps this field convertible; the limitation is
    stated here because the type cannot state it.
    """

    index: int
    results: tuple[ScientificResult, ...]
    largest_iterate_change: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", int(self.index))
        object.__setattr__(self, "results", tuple(self.results))
        if not isinstance(self.largest_iterate_change, Quantity):
            raise InvalidScientificProblem(
                "iterate change must be a Quantity"
            )

    def result_for(self, problem_id: str) -> ScientificResult:
        for result in self.results:
            if result.problem_id == problem_id:
                return result
        raise InvalidScientificProblem(
            f"iteration {self.index} produced no result for problem "
            f"{problem_id!r}"
        )

    def transported(self, dependency: QuantityDependency) -> Quantity:
        """The value that crossed this edge in this pass. Derived, not stored."""
        return self.result_for(dependency.source_problem_id).value(
            dependency.source_quantity
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLED_ITERATION_SCHEMA,
            "index": self.index,
            "results": [r.to_dict() for r in self.results],
            "largest_iterate_change": self.largest_iterate_change.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoupledIteration":
        require_schema(payload, COUPLED_ITERATION_SCHEMA)
        return cls(
            index=payload["index"],
            results=tuple(
                ScientificResult.from_dict(r) for r in payload["results"]
            ),
            largest_iterate_change=Quantity.from_dict(
                payload["largest_iterate_change"]
            ),
        )


@dataclass(frozen=True)
class CoupledRun:
    """What the coupling iteration did, and why it stopped.

    ``outcome`` is the **only** statement of coupling convergence anywhere. It
    is not written into any ``ScientificResult.convergence``, any
    ``ValidationReport``, any ``SolverSettings.tolerances``, any
    ``ProvenanceRecord.tolerances``, or any metadata, diagnostics or artifacts
    mapping — and it is never computed from the sub-solves' own convergence.
    Every closed-form participant here reports ``NOT_APPLICABLE`` and the MNA
    solve reports ``CONVERGED`` in every iteration of a run that did not
    converge at all.
    """

    plan: FixedPointCouplingPlan
    outcome: CouplingOutcome
    iterations: tuple[CoupledIteration, ...]
    #: The last value each torn endpoint took, whatever the outcome.
    #:
    #: Named ``final_values`` and **not** ``converged_values``: it is populated
    #: identically on both exit paths, so on an ``ITERATION_LIMIT_REACHED`` run
    #: it holds an iterate six kelvin from the fixed point. A field named
    #: *converged* holding an unconverged number is one name meaning two things
    #: — the defect `MIN-FOUNDATION-ET` caught pre-commit as finding D-1, when
    #: it still cost a rename rather than a schema bump.
    #:
    #: Keyed by the ``(problem_id, quantity)`` pair itself, not by a
    #: ``"{problem}::{quantity}"`` string. Both components already contain
    #: colons, so a composite key would have to be parsed to be read — the
    #: string convention this platform refuses, and the association
    #: :class:`TornEndpoint` exists to carry structurally.
    final_values: Mapping[tuple[str, str], Quantity]
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        if not isinstance(self.plan, FixedPointCouplingPlan):
            raise InvalidScientificProblem(
                "a coupled run requires the plan it executed"
            )
        if not isinstance(self.provenance, ProvenanceRecord):
            raise InvalidScientificProblem(
                "a coupled run requires a ProvenanceRecord: an unattributable "
                "iteration is not a scientific result"
            )
        object.__setattr__(self, "outcome", CouplingOutcome(self.outcome))
        iterations = tuple(self.iterations)
        if not iterations:
            raise InvalidScientificProblem(
                "a coupled run with no iterations executed nothing; the budget "
                "guarantees at least one"
            )
        for iteration in iterations:
            if not isinstance(iteration, CoupledIteration):
                raise InvalidScientificProblem(
                    f"coupled run iterations must be CoupledIteration records, "
                    f"got {type(iteration).__name__}"
                )
        object.__setattr__(self, "iterations", iterations)
        object.__setattr__(
            self,
            "final_values",
            {(str(p), str(q)): v for (p, q), v in dict(self.final_values).items()},
        )
        for name, value in self.final_values.items():
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"final value {name!r} must be a Quantity"
                )

    @property
    def criterion_met(self) -> bool:
        """Derived from :attr:`outcome`, never stored beside it."""
        return self.outcome is CouplingOutcome.CRITERION_MET

    @property
    def iterations_run(self) -> int:
        return len(self.iterations)

    @property
    def final_iterate_change(self) -> Quantity:
        return self.iterations[-1].largest_iterate_change

    @property
    def iterate_changes(self) -> tuple[Quantity, ...]:
        return tuple(i.largest_iterate_change for i in self.iterations)

    @property
    def final(self) -> CoupledIteration:
        return self.iterations[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLED_RUN_SCHEMA,
            "plan": self.plan.to_dict(),
            "outcome": self.outcome.value,
            "iterations": [i.to_dict() for i in self.iterations],
            # A list of records, not a mapping keyed by a joined string. The
            # endpoint travels as its two components and is read back without
            # being parsed.
            "final_values": [
                {
                    "problem_id": problem_id,
                    "quantity": quantity,
                    "value": self.final_values[(problem_id, quantity)].to_dict(),
                }
                for problem_id, quantity in sorted(self.final_values)
            ],
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoupledRun":
        require_schema(payload, COUPLED_RUN_SCHEMA)
        return cls(
            plan=FixedPointCouplingPlan.from_dict(payload["plan"]),
            outcome=CouplingOutcome(payload["outcome"]),
            iterations=tuple(
                CoupledIteration.from_dict(i) for i in payload["iterations"]
            ),
            final_values={
                (entry["problem_id"], entry["quantity"]): Quantity.from_dict(
                    entry["value"]
                )
                for entry in payload["final_values"]
            },
            provenance=ProvenanceRecord.from_dict(payload["provenance"]),
        )


# ---- per-problem execution, supplied by this pack --------------------------

def _property_result(
    *, run_id: str, stage: CoupledStage, problem: ScientificProblem,
    temperature: Quantity,
) -> ScientificResult:
    solver = mat.ResistancePropertySolver()
    solver.bind_conductor(stage.conductor, problem.problem_id,
                          temperature=temperature)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    model = ModelReference(mat.LINEAR_TCR_MODEL.model_id,
                           mat.LINEAR_TCR_MODEL.version)
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version="engcore.domains.electrical.material/0.1.0",
        bindings=(
            ExecutionBinding(
                model=model,
                realization=prepared.payload.realization.reference(),
                solver=solver.identity,
            ),
        ),
        inputs=dict(problem.parameter_values()) | {mat.TEMPERATURE: temperature},
        assumptions=mat.LINEAR_TCR_MODEL.assumptions,
    )
    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=((model.model_id, model.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=solver.validate(prepared, raw),
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification is performed on the declared "
                "temperature coefficient"
            )
            for name in metrics
        },
        assumptions=mat.LINEAR_TCR_MODEL.assumptions,
        provenance=provenance,
    )


def _thermal_result(
    *, run_id: str, stage: CoupledStage, problem: ScientificProblem,
    heat_input: Quantity,
) -> ScientificResult:
    solver = lump.LumpedThermalSolver()
    solver.bind_body(stage.body, problem.problem_id, heat_input=heat_input)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    model = ModelReference(lump.LUMPED_CAPACITY_MODEL.model_id,
                           lump.LUMPED_CAPACITY_MODEL.version)
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version="engcore.domains.thermal_models.lumped/0.1.0",
        bindings=(
            ExecutionBinding(
                model=model,
                realization=prepared.payload.realization.reference(),
                solver=solver.identity,
            ),
        ),
        inputs=dict(problem.parameter_values()) | {
            lump.HEAT_INPUT: heat_input,
            lump.AMBIENT_TEMPERATURE: stage.body.ambient_temperature,
            # The state at t0. Identical in every iteration: the loop iterates
            # the coupling, it does not march time.
            lump.TEMPERATURE: stage.body.initial_temperature,
        },
        assumptions=lump.LUMPED_CAPACITY_MODEL.assumptions,
    )
    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=((model.model_id, model.version),),
        solver=solver.identity,
        convergence=raw.convergence,
        validation=solver.validate(prepared, raw),
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification is performed on the lumped "
                "thermal declaration"
            )
            for name in metrics
        },
        assumptions=lump.LUMPED_CAPACITY_MODEL.assumptions,
        provenance=provenance,
    )


def _electrical_result(
    *, run_id: str, system: CoupledElectroThermalSystem,
    resistances: Mapping[str, Quantity],
) -> ScientificResult:
    circuit = system.circuit_at(resistances)
    return solve_circuit(
        circuit, run_id=run_id, problem=build_dc_problem(circuit)
    )


def _executors(
    system: CoupledElectroThermalSystem, problems: Sequence[ScientificProblem]
) -> dict[str, Callable[[Mapping[str, Quantity], str], ScientificResult]]:
    """problem_id -> how this pack solves it, given its transported inputs.

    This mapping is the *only* place the loop learns which science sits behind
    which problem, and it is built here, in the system pack, from declarations
    the caller supplied. The iteration below reads a dependency graph and a
    dispatch table; it contains no electrical or thermal branch of its own.
    """
    electrical = next(
        p for p in problems if p.problem_id.startswith("electrical_dc:")
    )
    table: dict[str, Callable[[Mapping[str, Quantity], str], ScientificResult]] = {}

    def electrical_call(inputs: Mapping[str, Quantity], run_id: str):
        resistances = {
            stage.component_id: inputs[resistance_name(stage.component_id)]
            for stage in system.stages
        }
        return _electrical_result(
            run_id=run_id, system=system, resistances=resistances
        )

    table[electrical.problem_id] = electrical_call

    for stage, prop, thermal in stage_problems(system):

        def property_call(inputs, run_id, _stage=stage, _problem=prop):
            return _property_result(
                run_id=run_id, stage=_stage, problem=_problem,
                temperature=inputs[mat.TEMPERATURE],
            )

        def thermal_call(inputs, run_id, _stage=stage, _problem=thermal):
            return _thermal_result(
                run_id=run_id, stage=_stage, problem=_problem,
                heat_input=inputs[lump.HEAT_INPUT],
            )

        table[prop.problem_id] = property_call
        table[thermal.problem_id] = thermal_call
    return table


def run_fixed_point(
    problems: Sequence[ScientificProblem],
    executors: Mapping[str, Callable[[Mapping[str, Quantity], str], ScientificResult]],
    plan: FixedPointCouplingPlan,
    *,
    run_id: str,
    software_version: str,
    assumptions: tuple[str, ...] = (),
) -> CoupledRun:
    """Execute a torn dependency cycle to convergence, or to the budget.

    A Gauss–Seidel sweep in the order the *records* imply: cut the torn edges,
    topologically sort what remains, and solve each problem with the values its
    incoming edges transported. Torn targets take the seed on the first pass and
    the previous pass's value afterwards.

    **Nothing in this function names a domain, and nothing in it can.** It sees
    a set of problems, a directed dependency set, a plan, and a mapping from
    problem id to *something that solves that problem*. Which sciences sit
    behind those callables is supplied by the caller and is unreadable from
    here — which is what makes "the loop does not secretly know it is
    electro-thermal" a checkable claim rather than an assurance.

    It remains a **system-pack** function. It is not promoted into universal
    core because no universal reader of a coupling plan or outcome exists;
    the promotion criterion is preregistered.

    Convergence is the largest change of any torn iterate, compared in one
    ratio-scale unit fixed by the plan. It is **not** derived from any
    participant's own convergence: in the non-convergent cases every sub-solve
    reports success in every one of the fifty iterations that did not converge.

    A sub-solve that refuses an inadmissible value is **not caught**. An
    execution failure and a failure to converge are different findings, and a
    loop that swallowed the first to report the second would be collapsing them.
    """
    seeds = {e.endpoint: e.initial_value for e in plan.torn}
    problems = tuple(problems)
    issues = plan.check_against(problems)
    if issues:
        raise InvalidScientificProblem(
            f"coupling plan {plan.plan_id!r} cannot be executed against this "
            f"composition: " + "; ".join(issues)
        )

    problem_ids = [p.problem_id for p in problems]
    # Three pairing guards. Every domain in this repository has them —
    # ``verify_problem_matches_circuit``, ``verify_problem_matches_body``,
    # ``verify_problem_matches_conductor`` — and the one place that *composes*
    # results is the place that most needs them. The next milestone replaces a
    # participant with an external provider, which is exactly the producer most
    # likely to hand back a result carrying its own identity.
    duplicated = sorted({p for p in problem_ids if problem_ids.count(p) > 1})
    if duplicated:
        raise InvalidScientificProblem(
            f"duplicate problem id(s) {duplicated}: two problems under one id "
            f"would collapse into one solve and one attribution"
        )
    uncovered = sorted(set(problem_ids) - set(executors))
    if uncovered:
        raise InvalidScientificProblem(
            f"no executor was supplied for {uncovered}; a problem in the "
            f"composition that nothing solves cannot be ordered into a sweep"
        )

    order = execution_order(problem_ids, plan.uncut)
    if not order:
        raise InvalidScientificProblem(
            f"coupling plan {plan.plan_id!r} leaves a cycle after its declared "
            f"tears; no execution order exists"
        )

    unit = plan.comparison_unit
    tolerance = plan.absolute_tolerance.magnitude_in(unit)
    incoming: dict[str, list[QuantityDependency]] = {p: [] for p in problem_ids}
    for dependency in plan.uncut:
        incoming[dependency.target_problem_id].append(dependency)

    current = dict(seeds)
    iterations: list[CoupledIteration] = []
    outcome = CouplingOutcome.ITERATION_LIMIT_REACHED

    for index in range(1, plan.max_iterations + 1):
        produced: dict[str, ScientificResult] = {}
        for problem_id in order:
            inputs: dict[str, Quantity] = {}
            for dependency in incoming[problem_id]:
                inputs[dependency.target_quantity] = produced[
                    dependency.source_problem_id
                ].value(dependency.source_quantity)
            # Torn targets take the seed on the first pass and the previous
            # pass's value afterwards. This cannot shadow a transported value:
            # the plan refuses two dependencies sharing a target endpoint, so a
            # torn edge's endpoint is never also an uncut edge's. An earlier
            # form had no such refusal, and this assignment then silently
            # discarded the transported value.
            for endpoint, value in current.items():
                if endpoint[0] == problem_id:
                    inputs[endpoint[1]] = value
            result = executors[problem_id](
                inputs, f"{run_id}-{index}-{problem_id}"
            )
            if result.problem_id != problem_id:
                raise InvalidScientificProblem(
                    f"the executor for {problem_id!r} returned a result "
                    f"attributed to {result.problem_id!r}; a composition that "
                    f"accepted that would misattribute every value it "
                    f"transported out of it"
                )
            produced[problem_id] = result

        updated: dict[tuple[str, str], Quantity] = {}
        largest = 0.0
        for endpoint in plan.torn:
            key = endpoint.endpoint
            value = produced[endpoint.dependency.source_problem_id].value(
                endpoint.dependency.source_quantity
            )
            updated[key] = value
            largest = max(
                largest,
                abs(value.magnitude_in(unit) - current[key].magnitude_in(unit)),
            )

        iterations.append(
            CoupledIteration(
                index=index,
                results=tuple(produced[p] for p in order),
                largest_iterate_change=Quantity(largest, unit),
            )
        )
        current = updated
        if largest <= tolerance:
            outcome = CouplingOutcome.CRITERION_MET
            break

    # Every iteration, not only the last. For this consumer every sweep binds
    # the same participants, so the two agree — but this function is generic,
    # and an executor that changed realization mid-run (an adaptive fallback, a
    # provider degrading to a coarser method) would leave those bindings out of
    # a last-iteration-only record. ``ProvenanceRecord`` deduplicates by key,
    # so the union costs nothing and cannot under-claim.
    bindings: list[ExecutionBinding] = []
    for result in [r for iteration in iterations for r in iteration.results]:
        if result.provenance.bindings:
            bindings.extend(result.provenance.bindings)
        else:
            # Producers predating MODEL0-R declare participants without an
            # association. The electrical solver is one; its models are named
            # by the circuit it solved, and pairing them with its solver here
            # states an association it did make. Nothing is inferred about a
            # realization: it stays None, which is a real answer.
            bindings.extend(
                ExecutionBinding(
                    model=ModelReference(model_id, version),
                    realization=None,
                    solver=result.solver,
                )
                for model_id, version in result.models
            )

    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        bindings=tuple(bindings),
        # ``ProvenanceRecord.inputs`` is ``Mapping[str, Quantity]`` in frozen
        # core, so an endpoint has to be flattened to reach it. Recorded as a
        # stated limitation rather than left silent: this key must be parsed to
        # be read back, and ``CoupledRun.final_values`` is the record that
        # carries the same endpoints structurally.
        inputs={f"{p}::{q}": v for (p, q), v in sorted(current.items())},
        assumptions=(
            "Gauss-Seidel fixed-point iteration over a torn dependency cycle",
            "no relaxation, damping or acceleration is applied",
            "every problem's own declared conditions are identical in every "
            "iteration; the iterate is a coupling iterate and not a time level",
        )
        + tuple(assumptions),
    )

    return CoupledRun(
        plan=plan,
        outcome=outcome,
        iterations=tuple(iterations),
        final_values=dict(current),
        provenance=provenance,
    )


def run_fixed_point_coupling(
    system: CoupledElectroThermalSystem,
    plan: FixedPointCouplingPlan,
    *,
    run_id: str = "et-coupled",
) -> CoupledRun:
    """The electro-thermal entry point: build the composition, then iterate it.

    Everything domain-specific happens here — the problems, and the dispatch
    table that says how each of them is solved. :func:`run_fixed_point` receives
    both as data and runs the iteration without being able to name either.
    """
    problems = coupled_problems(
        system,
        {stage.component_id: stage.conductor.reference_resistance
         for stage in system.stages},
    )
    return run_fixed_point(
        problems,
        _executors(system, problems),
        plan,
        run_id=run_id,
        software_version="engcore.systems.electrothermal.coupled/0.1.0",
        assumptions=(
            "the resistance is evaluated at the transported temperature and "
            "held constant over the integrated interval; this is an implicit "
            "statement over one interval and carries a coupling error that is "
            "not quantified here",
            "the whole dissipated power of an element enters its body",
        ),
    )
