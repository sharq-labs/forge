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
* **A tear must be a lag.**  A torn edge that runs forward in the sweep order
  (a redundant tear) is refused: the runtime would read it in the same sweep.
* **Termination states.**  ``ResultParticipant`` treats a result whose solver
  reports a failed termination as a numerical failure of the window; the
  native loop ignores termination states (every executor here reports
  CONVERGED or NOT_APPLICABLE, so this does not differ in practice).
* **Relaxation (Phase 3.5 WS2).**  A plan with ``relaxation_factor`` is built
  with a CONSTANT relaxation restricted to the lagged edges
  (``RelaxationPolicy.scope = "lagged_edges"``): exactly the torn values are
  mixed, ``old + w (new - old)`` in the target port's unit, as the native loop
  does in its comparison unit (a linear rescaling: equal up to rounding).  The
  criterion stays the UNRELAXED change in both.
* **Failed results (Phase 3.5 WS2).**  The native loop refuses a failed result
  where a value would TRAVEL; the participants here declare
  ``refuse_failed_sink=False`` so a problem that supplies no coupling value
  records a failed result exactly as the native loop does.
* **Migration candidate (Phase 3.5 WS2).**  :func:`run_coupled_via_runtime`
  executes the composition on the runtime and returns a native-shaped
  :class:`~.coupled.CoupledRun` (iterations, outcome incl. ``TRANSFER_REFUSED``,
  final values, provenance, crossings), so ``credibility.CouplingEvidence`` and
  every report read it unchanged.  :func:`run_electrothermal_coupling` selects
  the path; the NATIVE loop stays the default, and the candidate refuses to run
  unless the caller acknowledges that parity is unverified, until
  :data:`RUNTIME_PATH_PARITY_VERIFIED` is set by an owner decision after the
  deferred parity tests have been executed and passed.

Behaviour that may change at the migration boundary (each is a parity-test
target, DEFERRED_VALIDATION DV-49 / DV-88..DV-90):

1. on a failed result that supplies a coupling value the runtime refuses at
   PRODUCTION; the native loop first solves the problems of that sweep that do
   not read it, so the TRANSFER_REFUSED iteration lists fewer results;
2. the runtime relaxes in the target port unit, the native loop in the plan's
   comparison unit (rounding only);
3. the provenance ``software_version`` names the adapter, and one assumption
   states that the runtime executed the iteration;
4. iterations, largest changes and final values are the runtime's (the largest
   change is the runtime's own residual on the torn edges; final values are
   re-transported from the recorded results by the native rule);
5. a ``TransportRefused`` raised by the native transfer for an UNDECLARED
   efficiency becomes a TRANSFER_REFUSED stop natively; in the runtime the
   transfer engine refuses it with an exception, so the candidate raises;
6. with two failed results in one sweep the candidate names the first one
   PRODUCED, the native loop the first one TRANSPORTED;
7. the candidate's ``CoupledRun`` is read by ``credibility.CouplingEvidence``
   exactly like a native one; only ``software_version`` and the first
   assumption distinguish it (no structural marker: an owner decision, OD-P35-4).

Parity is a diagnostic (:class:`ParityRecord`).  It never makes either path
correct, and nothing here claims the two agree until the deferred parity tests
have been executed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from ...data.resolver import BulkDataResolver
from ...data.store import InMemoryBulkStore
from ...execution.multiphysics.authority import fixed_point_outcome
from ...execution.multiphysics.runtime import MultiphysicsRuntime, assess_run_outcome
from ...execution.multiphysics.runtime import MultiphysicsExecutionError
from ...execution.multiphysics.steady import ResultParticipant, ResultRefused
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
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
    RelaxationKind,
    RelaxationPolicy,
    ResidualNorm,
    TimePolicy,
    WindowOutcome,
)
from ...scientific.units.quantity import Quantity
from . import coupled as cp

ADAPTER_ID = "engcore.systems.electrothermal.runtime_adapter"
ADAPTER_VERSION = "0.2.0"

#: Phase 3.5 WS2: set ONLY by an owner decision after the deferred parity tests (DV-49, DV-88..DV-90) were
#: executed and passed.  While False the runtime candidate runs only on an explicit acknowledgement.
RUNTIME_PATH_PARITY_VERIFIED = False


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
    problems = cp.coupled_problems(
        system, {stage.component_id: stage.conductor.reference_resistance for stage in system.stages}
    )
    problem_ids = [p.problem_id for p in problems]
    order = cp.execution_order(problem_ids, plan.uncut)
    if not order:
        raise InvalidScientificProblem(f"coupling plan {plan.plan_id!r} leaves a cycle after its tears")
    position = {pid: k for k, pid in enumerate(order)}
    forward = sorted(
        cp.edge_key(e.dependency) for e in plan.torn
        if position[e.dependency.source_problem_id] < position[e.dependency.target_problem_id]
    )
    if forward:
        # the native loop lags every torn value (seed, then the previous sweep); in a serial
        # runtime sweep a forward edge reads THIS sweep's value, so the iteration would differ
        raise InvalidScientificProblem(
            f"torn edges {forward} run forward in the sweep order {list(order)}: the runtime would read them in "
            f"the same sweep while the native loop lags them; only tears of the cycle are reproduced"
        )
    issues = plan.check_against(problems)
    if issues:
        raise InvalidScientificProblem(f"coupling plan {plan.plan_id!r} does not fit this composition: " + "; ".join(issues))
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
            # the native loop refuses a failed result only where a value travels (coupled._transport)
            refuse_failed_sink=False,
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
    relaxation = RelaxationPolicy()
    if plan.relaxation_factor is not None:
        # Phase 3.5 WS2: the native loop under-relaxes the TORN values only; the torn edges are exactly the
        # lagged edges of this serial order (forward tears are refused above)
        factor = float(plan.relaxation_factor)
        relaxation = RelaxationPolicy(RelaxationKind.CONSTANT, factor, min(0.05, factor), 1.0, scope="lagged_edges")
    runtime_plan = CouplingPlan(
        f"{plan.plan_id}-runtime", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
        TimePolicy(Quantity(0.0, "second"), Quantity(1.0, "second"), Quantity(1.0, "second"), align_events=False),
        tuple(order), criteria, relaxation=relaxation, max_iterations=plan.max_iterations, fail_on_nonconvergence=False,
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


class CouplingPathChoice(str, Enum):
    """Phase 3.5 WS2: which loop executes the electrothermal fixed point."""

    NATIVE = "native"                        # the product path (default)
    RUNTIME_CANDIDATE = "runtime_candidate"  # the authoritative runtime through this adapter; parity UNVERIFIED


#: the native loop's own assumption statements (``coupled.run_fixed_point_coupling``), carried verbatim
_NATIVE_ASSUMPTIONS = (
    "the resistance is evaluated at the transported temperature and "
    "held constant over the integrated interval; this is an implicit "
    "statement over one interval and carries a coupling error that is "
    "not quantified here",
    "the whole dissipated power of an element enters its body",
)


def _first_transport_out_of(problem_id: str, plan: "cp.FixedPointCouplingPlan", order: tuple[str, ...]) -> Any:
    """The dependency the native sweep would transport first out of ``problem_id`` (uncut edges in order, then tears)."""
    position = {pid: k for k, pid in enumerate(order)}
    later = sorted((d for d in plan.uncut if d.source_problem_id == problem_id),
                   key=lambda d: position[d.target_problem_id])
    if later:
        return later[0]
    for endpoint in plan.torn:
        if endpoint.dependency.source_problem_id == problem_id:
            return endpoint.dependency
    raise InvalidScientificProblem(f"problem {problem_id!r} supplies no coupling value; it cannot be refused at a transfer")


def run_coupled_via_runtime(
    system: "cp.CoupledElectroThermalSystem",
    plan: "cp.FixedPointCouplingPlan",
    *,
    run_id: str = "et-runtime",
    acknowledge_unverified_parity: bool = False,
) -> tuple["cp.CoupledRun", MultiphysicsRunRecord | None]:
    """Phase 3.5 WS2: the migration candidate -- the composition executed by the runtime, as a native ``CoupledRun``.

    The runtime decides order, convergence, relaxation and the outcome; this
    function only re-expresses its record (and the participants' results) in
    the native record type.  It refuses to run unless parity is verified or the
    caller acknowledges that it is not.
    """
    if not RUNTIME_PATH_PARITY_VERIFIED and acknowledge_unverified_parity is not True:
        raise InvalidScientificProblem(
            "the runtime path of the electrothermal coupling has no executed parity evidence against the native loop "
            "(DEFERRED_VALIDATION DV-49, DV-88..DV-90); pass acknowledge_unverified_parity=True to run it as a "
            "candidate, or use the native path"
        )
    built = runtime_equivalent(system, plan, run_prefix=run_id)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(built.graph, built.plan, dict(built.participants),
                                  resolver=BulkDataResolver(store), store=store)
    record: MultiphysicsRunRecord | None = None
    refused: ResultRefused | None = None
    try:
        record = runtime.run(run_id, external_inputs={}, initial_coupling_values=dict(built.initial_coupling_values))
    except ResultRefused as exc:
        owner = next((p for p in built.participants.values() if p.results and p.results[-1] is exc.result), None)
        if owner is None or owner.problem_id != exc.result.problem_id:
            raise  # a misattributed result is an execution failure in the native loop too, never a recorded stop
        refused = exc
    return _as_coupled_run(system, plan, built, record, refused, run_id), record


def _as_coupled_run(system, plan, built: RuntimeEquivalent, record, refused, run_id) -> "cp.CoupledRun":
    order = tuple(built.plan.participant_order)
    participants = built.participants
    unit = plan.comparison_unit
    sweeps = max(len(participants[pid].results) for pid in order)
    if record is not None:
        if len(record.windows) != 1 or len(record.windows[0].iterations) != sweeps:
            raise MultiphysicsExecutionError(
                "migration candidate: the runtime record and the participants' results disagree on the number of sweeps"
            )
        window = record.windows[0]
        outcome = {WindowOutcome.CONVERGED: cp.CouplingOutcome.CRITERION_MET,
                   WindowOutcome.ITERATION_LIMIT: cp.CouplingOutcome.ITERATION_LIMIT_REACHED}.get(window.outcome)
        if outcome is None:
            raise MultiphysicsExecutionError(f"migration candidate: unexpected runtime window outcome {window.outcome.value!r}")
    else:
        window = None
        outcome = cp.CouplingOutcome.TRANSFER_REFUSED
    current = {endpoint.endpoint: endpoint.initial_value for endpoint in plan.torn}
    iterations: list[cp.CoupledIteration] = []
    for k in range(1, sweeps + 1):
        results = tuple(participants[pid].results[k - 1] for pid in order if len(participants[pid].results) >= k)
        if refused is not None and k == sweeps:
            iterations.append(cp.CoupledIteration(
                index=k, results=results,
                # as the native loop: the last change it DID measure (zero only for a refusal on the first sweep)
                largest_iterate_change=iterations[-1].largest_iterate_change if iterations else Quantity(0.0, unit),
            ))
            break
        produced = {r.problem_id: r for r in results}
        updated = {e.endpoint: cp._transport(produced[e.dependency.source_problem_id], e.dependency, k) for e in plan.torn}
        if window is not None:
            # the authority's own measurement: the residual it judged on the torn edges
            largest = max((item.absolute.magnitude_in(unit) for item in window.iterations[k - 1].residuals), default=0.0)
        else:
            largest = max((abs(v.magnitude_in(unit) - current[key].magnitude_in(unit)) for key, v in updated.items()),
                          default=0.0)
        iterations.append(cp.CoupledIteration(index=k, results=results, largest_iterate_change=Quantity(largest, unit)))
        last_converged = window is not None and k == sweeps and outcome is cp.CouplingOutcome.CRITERION_MET
        if last_converged or plan.relaxation_factor is None:
            current = updated  # a converged run reports the unrelaxed transported values (native rule)
        else:
            omega = float(plan.relaxation_factor)
            current = {key: Quantity(current[key].magnitude_in(unit)
                                     + omega * (value.magnitude_in(unit) - current[key].magnitude_in(unit)), unit).to(str(value.units))
                       for key, value in updated.items()}
    refusal = None
    if refused is not None:
        dependency = _first_transport_out_of(refused.result.problem_id, plan, order)
        refusal = cp.TransportRefused(str(refused), result=refused.result, dependency=dependency, iteration=sweeps)
    bindings: list[ExecutionBinding] = []
    for result in [r for iteration in iterations for r in iteration.results]:
        if result.provenance.bindings:
            bindings.extend(result.provenance.bindings)
        else:
            bindings.extend(ExecutionBinding(model=ModelReference(model_id, version), realization=None, solver=result.solver)
                            for model_id, version in result.models)
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=f"{ADAPTER_ID}/{ADAPTER_VERSION}",
        bindings=tuple(bindings),
        inputs={f"{p}::{q}": v for (p, q), v in sorted(current.items())},
        assumptions=(
            "Gauss-Seidel fixed-point iteration over a torn dependency cycle, executed by the authoritative "
            "MultiphysicsRuntime through the electrothermal runtime adapter (migration candidate; parity with the "
            "native loop NOT VERIFIED)",
            (
                "no relaxation, damping or acceleration is applied"
                if plan.relaxation_factor is None
                else f"torn values are under-relaxed with factor {plan.relaxation_factor!r} between "
                     f"sweeps; the criterion is the unrelaxed change; no damping or acceleration otherwise"
            ),
            "every problem's own declared conditions are identical in every "
            "iteration; the iterate is a coupling iterate and not a time level",
        ) + _NATIVE_ASSUMPTIONS,
    )
    run = cp.CoupledRun(plan=plan, outcome=outcome, iterations=tuple(iterations), final_values=dict(current),
                        provenance=provenance, refusal=refusal)
    final = run.iterations[-1]
    return replace(
        run,
        crossings=cp.recorded_crossings(final, cp._recorded_transfers(system, plan, final)),
        provenance=replace(run.provenance, transfers=cp.ambient_transfers(system, final) + cp.converted_transfers(plan, final)),
    )


def run_electrothermal_coupling(
    system: "cp.CoupledElectroThermalSystem",
    plan: "cp.FixedPointCouplingPlan",
    *,
    path: CouplingPathChoice = CouplingPathChoice.NATIVE,
    run_id: str = "et-coupled",
    acknowledge_unverified_parity: bool = False,
) -> "cp.CoupledRun":
    """The controlled migration switch.  NATIVE (default) is the product path, unchanged."""
    path = CouplingPathChoice(path)
    if path is CouplingPathChoice.NATIVE:
        return cp.run_fixed_point_coupling(system, plan, run_id=run_id)
    run, _ = run_coupled_via_runtime(system, plan, run_id=run_id,
                                     acknowledge_unverified_parity=acknowledge_unverified_parity)
    return run


__all__ = [
    "ADAPTER_ID",
    "CouplingPathChoice",
    "RUNTIME_PATH_PARITY_VERIFIED",
    "ParityRecord",
    "RuntimeEquivalent",
    "compare_with_native",
    "edge_id",
    "run_through_runtime",
    "runtime_equivalent",
    "run_coupled_via_runtime",
    "run_electrothermal_coupling",
]
