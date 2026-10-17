"""The electrothermal composition as participants of the authoritative coupling runtime (Phase 2 BR8).

A bounded strangler step, not a migration.  :func:`run_fixed_point_coupling`
(the native Gauss-Seidel loop in :mod:`.coupled`) stays the product path.  This
module builds the SAME composition -- the same problems, the same executor
table, the same dependency graph, the same order and the same criterion -- as a
:class:`~engcore.execution.multiphysics.runtime.MultiphysicsRuntime` plan, so
the two can be compared and the native loop can later delegate.  The status
and the remaining work are declared in
:data:`engcore.execution.multiphysics.authority.COUPLING_PATHS`.

The correspondence, and where it stops
--------------------------------------
* **Problems -> steady participants.**  One
  :class:`~engcore.execution.multiphysics.steady.ResultParticipant` per problem,
  solved by the native executor table (``coupled._executors``); no physics is
  re-implemented here.
* **Dependencies -> edges.**  Every declared dependency, cut or not, is one
  edge carrying its declared ``EnergyConversion`` / transport declaration; the
  runtime's transfer engine applies a conversion and refuses an undeclared
  efficiency exactly as ``coupled._transport`` does.
* **Order.**  The native order (``coupled.execution_order`` over the uncut
  edges) is the plan's explicit ``participant_order`` under SERIAL semantics.
  The torn edges are then exactly the lagged edges, i.e. exactly the edges the
  runtime requires a criterion on.
* **Criterion.**  One LINF criterion per torn edge with the plan's absolute
  tolerance and zero relative tolerance: "every torn change <= tol" is "the
  largest torn change <= tol".  The runtime compares in the base unit of the
  port; the native loop in the plan's ratio-scale comparison unit.  Both are
  linear (ratio-scale) rescalings of one inequality, so they can disagree only
  by rounding at the boundary.
* **Seeds.**  Torn seeds are the initial coupling values of the torn edges.
  Forward edges carry no initial value: their source runs first in every sweep.
* **Time.**  Steady participants ignore it; the plan is one formal window
  ``[0, 1] s``.  It is not a time level, as in the native loop.
* **Refused, not approximated.**  A plan with ``relaxation_factor`` is refused:
  the runtime's serial relaxation mixes EVERY edge, the native loop only the
  torn values, so the iterates differ.  A transfer refusal is raised by the
  runtime instead of being recorded as a ``TRANSFER_REFUSED`` stop.

Parity is a diagnostic (:class:`ParityRecord`).  It never makes either path
correct, and nothing here claims the two agree until the deferred parity tests
have been executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...data.resolver import BulkDataResolver
from ...data.store import InMemoryBulkStore
from ...execution.multiphysics.authority import fixed_point_outcome
from ...execution.multiphysics.runtime import MultiphysicsRuntime, assess_run_outcome
from ...execution.multiphysics.steady import ResultParticipant
from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import (
    ConvergenceCriterion,
    CouplingEdge,
    CouplingPlan,
    CouplingScheme,
    IterationSemantics,
    MultiphysicsRunRecord,
    ParticipantSpec,
    PhysicsGraph,
    PortDefinition,
    PortDirection,
    PortKind,
    PortRef,
    ResidualNorm,
    TimePolicy,
)
from ...scientific.units.quantity import Quantity
from . import coupled as cp

ADAPTER_ID = "engcore.systems.electrothermal.runtime_adapter"
ADAPTER_VERSION = "0.1.0"


def edge_id(dependency: Any) -> str:
    """The runtime edge id of one declared dependency (its endpoint quad)."""
    source, source_quantity, target, target_quantity = cp.edge_key(dependency)
    return f"{source}.{source_quantity}->{target}.{target_quantity}"


@dataclass(frozen=True)
class RuntimeEquivalent:
    """What the runtime needs to execute the composition, and how it maps back."""

    graph: PhysicsGraph
    plan: CouplingPlan
    participants: Mapping[str, ResultParticipant]
    initial_coupling_values: Mapping[str, Quantity]
    #: runtime edge id -> the native torn endpoint ``(problem_id, quantity)`` it seeds
    torn_edges: Mapping[str, tuple[str, str]]


def runtime_equivalent(
    system: "cp.CoupledElectroThermalSystem",
    plan: "cp.FixedPointCouplingPlan",
    *,
    run_prefix: str = "et-runtime",
) -> RuntimeEquivalent:
    """Build the runtime plan that executes the same composition as ``run_fixed_point_coupling``."""
    if plan.relaxation_factor is not None:
        raise InvalidScientificProblem(
            "the runtime-equivalent build refuses a relaxed fixed-point plan: the runtime's serial relaxation "
            "mixes every edge of the sweep, while the native loop relaxes only the torn values, so the iterates "
            "would differ (recorded as remaining migration work)"
        )
    problems = cp.coupled_problems(
        system, {stage.component_id: stage.conductor.reference_resistance for stage in system.stages}
    )
    issues = plan.check_against(problems)
    if issues:
        raise InvalidScientificProblem(f"coupling plan {plan.plan_id!r} does not fit this composition: " + "; ".join(issues))
    problem_ids = [p.problem_id for p in problems]
    order = cp.execution_order(problem_ids, plan.uncut)
    if not order:
        raise InvalidScientificProblem(f"coupling plan {plan.plan_id!r} leaves a cycle after its tears")
    executors = cp._executors(system, problems)

    inputs: dict[str, dict[str, str]] = {pid: {} for pid in problem_ids}
    outputs: dict[str, dict[str, str]] = {pid: {} for pid in problem_ids}
    for dependency in plan.dependencies:
        inputs[dependency.target_problem_id][dependency.target_quantity] = dependency.unit_exemplar
        outputs[dependency.source_problem_id].setdefault(dependency.source_quantity, dependency.unit_exemplar)

    specs: dict[str, ParticipantSpec] = {}
    participants: dict[str, ResultParticipant] = {}
    for pid in problem_ids:
        ports = tuple(
            PortDefinition(name, PortDirection.INPUT, PortKind.SCALAR, name, unit) for name, unit in sorted(inputs[pid].items())
        ) + tuple(
            PortDefinition(name, PortDirection.OUTPUT, PortKind.SCALAR, name, unit) for name, unit in sorted(outputs[pid].items())
        )
        if not ports:
            raise InvalidScientificProblem(f"problem {pid!r} takes part in no dependency; it is not a coupling participant")
        spec = ParticipantSpec(
            pid, pid, "declared-by-problem", "electrothermal.native_executor", "1", "engcore.systems.electrothermal",
            "1", ADAPTER_ID, ADAPTER_VERSION, ports, transient=False, checkpointable=True, deterministic_restore=True,
            description="steady problem of the electrothermal composition, solved by the native executor table",
        )
        specs[pid] = spec
        participants[pid] = ResultParticipant(
            spec, problem_id=pid, solve=executors[pid], outputs={name: name for name in outputs[pid]},
            run_prefix=run_prefix,
        )

    edges = tuple(
        CouplingEdge(
            edge_id(dependency),
            PortRef(dependency.source_problem_id, dependency.source_quantity),
            PortRef(dependency.target_problem_id, dependency.target_quantity),
            conversion=dependency.conversion,
            transport_declaration=dependency.transport_declaration,
            description=dependency.description or dependency.name,
        )
        for dependency in plan.dependencies
    )
    torn = {edge_id(endpoint.dependency): endpoint.endpoint for endpoint in plan.torn}
    graph = PhysicsGraph(f"{plan.plan_id}-runtime", tuple(specs[pid] for pid in problem_ids), edges,
                         description="electrothermal composition as runtime participants (Phase 2 BR8 adapter)")
    criteria = tuple(
        ConvergenceCriterion(eid, 0.0, plan.absolute_tolerance, ResidualNorm.LINF) for eid in sorted(torn)
    )
    runtime_plan = CouplingPlan(
        f"{plan.plan_id}-runtime", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
        TimePolicy(Quantity(0.0, "second"), Quantity(1.0, "second"), Quantity(1.0, "second"), align_events=False),
        tuple(order), criteria, max_iterations=plan.max_iterations, fail_on_nonconvergence=False,
    )
    seeds = {edge_id(endpoint.dependency): endpoint.initial_value for endpoint in plan.torn}
    return RuntimeEquivalent(graph, runtime_plan, participants, seeds, torn)


def run_through_runtime(
    system: "cp.CoupledElectroThermalSystem",
    plan: "cp.FixedPointCouplingPlan",
    *,
    run_id: str = "et-runtime",
) -> tuple[MultiphysicsRunRecord, RuntimeEquivalent]:
    """Execute the composition on the authoritative runtime (not the product path)."""
    built = runtime_equivalent(system, plan, run_prefix=run_id)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(built.graph, built.plan, dict(built.participants),
                                  resolver=BulkDataResolver(store), store=store)
    run = runtime.run(run_id, external_inputs={}, initial_coupling_values=dict(built.initial_coupling_values))
    return run, built


@dataclass(frozen=True)
class ParityRecord:
    """How the native loop and the runtime build compare on one composition.  A diagnostic only."""

    native_outcome: str
    runtime_outcome: str
    native_iterations: int
    runtime_iterations: int
    #: ``problem.quantity`` -> |native - runtime| of the last sweep's output, in the native value's unit
    output_differences: Mapping[str, float]

    @property
    def same_outcome(self) -> bool:
        return self.native_outcome == self.runtime_outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "electrothermal_runtime_parity",
            "native_outcome": self.native_outcome,
            "runtime_outcome": self.runtime_outcome,
            "same_outcome": self.same_outcome,
            "native_iterations": self.native_iterations,
            "runtime_iterations": self.runtime_iterations,
            "output_differences": dict(sorted(self.output_differences.items())),
            "notice": "parity of two executions is a diagnostic; it validates neither",
        }


def compare_with_native(
    native: "cp.CoupledRun", run: MultiphysicsRunRecord, built: RuntimeEquivalent
) -> ParityRecord:
    """Compare a native ``CoupledRun`` with a runtime run of the same composition."""
    if len(run.windows) != 1:
        raise InvalidScientificProblem("the runtime build executes exactly one formal window")
    differences: dict[str, float] = {}
    final = native.iterations[-1] if native.iterations else None
    if final is not None:
        for result in final.results:
            outs = built.participants.get(result.problem_id)
            if outs is None:
                continue
            for port in outs.spec.outputs:
                key = f"{result.problem_id}.{port.port_id}"
                raw = run.final_outputs.get(key)
                if raw is None:
                    continue
                native_value = result.value(port.port_id)
                runtime_value = Quantity.from_dict(raw)
                differences[key] = abs(native_value.magnitude - runtime_value.magnitude_in(str(native_value.units)))
    return ParityRecord(
        native_outcome=fixed_point_outcome(native.outcome).value,
        runtime_outcome=assess_run_outcome(run).outcome.value,
        native_iterations=len(native.iterations),
        runtime_iterations=len(run.windows[0].iterations),
        output_differences=differences,
    )


__all__ = [
    "ADAPTER_ID",
    "ParityRecord",
    "RuntimeEquivalent",
    "compare_with_native",
    "edge_id",
    "run_through_runtime",
    "runtime_equivalent",
]
