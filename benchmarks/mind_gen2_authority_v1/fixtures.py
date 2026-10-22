"""GEN2-BR1.1 authority-bound contract fixtures: every projected fact is read from a real owner record.

The five BR1 synthetic worlds (battery pulse cell, HVAC climate chamber, HVAC field task, quadrotor, electric motor)
and the Gen1 two-level protocol are re-expressed as a problem/protocol DECLARATION plus the owner records a world is
projected from.  Nothing here writes a value into a world:

* state, environment and estimate values are committed by the system runtime (``SystemExecutor`` over a
  ``SystemRunRequest``): the base world is projected from the run's checkpoint after its ``settle`` node, and the run
  then moves on (``advance``), so its final result is a later head of the same run;
* model records live in a ``ModelRegistry``, provider status in a ``ProviderRegistry`` (probes) and its health
  assessment, the observation budget in a ``ScientificExperiment``, solver-call and wall-time accounts in
  ``BudgetLedger`` records;
* the declaration (roles, domains, actions, constraints, channels, value sources, model references, budget sources) is
  held in force by a ``DeclarationReader``, as the execution side would hold it.

Every number is invented to exercise the contract (development evidence only, never a scientific claim).  Interval
uncertainties are stated at 95 % coverage and every bound variable declares the guard band the protocol accepts
decisions at; that is a declared acceptance rule, not a guarantee.  All domain vocabulary lives here.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from benchmarks.mind_gen2_world_v1 import fixtures as br1
from engcore.mind.repsem.roles import VariableRole as R
from engcore.mind.world import ProposedAction, ScientificWorld, ValueOrigin, WorldVariable
from engcore.mind.world.authority import Authorities
from engcore.mind.world.declaration import BudgetSource, GuardBand, ProtocolDeclaration, ValueSource
from engcore.mind.world.owners import (
    BudgetReader, DeclarationReader, ModelRegistryReader, ProviderRegistryReader, RunStateReader, UnitRegistryReader,
)
from engcore.mind.world.projection import project_world
from engcore.providers.catalog import ProviderRegistry
from engcore.scenarios import ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline
from engcore.scientific import Quantity, Uncertainty
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
from engcore.scientific.ir.problem import ScientificProblem
from engcore.scientific.models.registry import ModelRegistry
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import UncertaintyKind
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind
from engcore.systems import ComponentDefinition, ComponentInstance, SystemDefinition
from engcore.system_runtime import (
    ApplicabilityReport, AuthorityRegistry, CallbackAuthority, ExecutionProfile, InitialStateSpec, NodeInput, NodeKind,
    NodeOutcome, NodeOutputSpec, NodeSpec, OutputValue, OwnerState, RequestedObservable, RuntimeContext, StateProposal,
    SystemCheckpoint, SystemRunRequest, SystemRunResult,
)
from engcore.system_runtime.executor import SystemExecutor

COVERAGE = 0.95
GUARD = GuardBand(COVERAGE, "synthetic protocol accepts state decisions at the stated 95 % coverage (not a guarantee)")
D = "dimensionless"
HUMAN = ProposalProvenance(ProposerKind.HUMAN, "fixture")
q = br1.q


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def covered(lower: Quantity, upper: Quantity) -> Uncertainty:
    """An interval stated at 95 % coverage (a probabilistic statement, never an enclosure)."""
    return Uncertainty(kind="interval", lower=lower, upper=upper, confidence_level=COVERAGE,
                       method="synthetic fixture interval at 95 % coverage")


def _restated(u: Uncertainty) -> Uncertainty:
    if u.kind is UncertaintyKind.INTERVAL:
        return covered(u.lower, u.upper)
    return u


def _shifted(value: Quantity, u: Uncertainty) -> tuple[Quantity, Uncertainty]:
    """The state after the run moved on: shifted by the interval width (or 10 % with no interval)."""
    if u.kind is UncertaintyKind.INTERVAL:
        width = u.upper.magnitude_in(value.units) - u.lower.magnitude_in(value.units)
        step = width if width else 0.1
        shift = lambda x: Quantity(x.magnitude_in(value.units) + step, value.units)  # noqa: E731
        return shift(value), covered(shift(u.lower), shift(u.upper))
    return Quantity(value.magnitude * 1.1 + 0.1, value.units), u


# ---- the state owner: a real system-runtime run ------------------------------------------------------------------------
@dataclass(frozen=True)
class Run:
    request: SystemRunRequest
    checkpoint: SystemCheckpoint      # head after `settle`: the base world's state
    result: SystemRunResult           # head after `advance`: the same run, moved on


def run_state(run_id: str, owners: Mapping[str, tuple[str, Mapping[str, tuple[Quantity, Uncertainty]]]]) -> Run:
    """Commit ``owners`` through the system runtime (settle), checkpoint, then advance every value (advance)."""
    owner_ids = sorted(owners)
    twins = {o: ScientificTwin(f"{run_id}.{o}", "1", TwinKind.CONCEPT) for o in owner_ids}
    sysdef = SystemDefinition(f"{run_id}.system", "1", tuple(ComponentDefinition(o, "1") for o in owner_ids),
                              tuple(ComponentInstance(o, o, "1", twins[o].reference) for o in owner_ids))
    scn = ScenarioSpecification(f"{run_id}.scenario", "1", q(0, "s"), q(3600, "s"),
                                segments=(ScenarioSegment("whole", q(0, "s"), q(3600, "s")),))
    tl = Timeline.from_scenario(scn, timeline_id=f"{run_id}.timeline", basis=TimeBasis("run", "elapsed", "start"))

    def states(values: Mapping[str, tuple[str, Mapping[str, tuple[Quantity, Uncertainty]]]]) -> tuple[OwnerState, ...]:
        return tuple(OwnerState(o, values[o][0], tuple(InitialStateValue(v, x, u) for v, (x, u) in
                                                       sorted(values[o][1].items()))) for o in owner_ids)

    advanced = {o: (role, {v: _shifted(x, u) for v, (x, u) in vals.items()}) for o, (role, vals) in owners.items()}
    within = (ApplicabilityReport("state_in_declared_range", "within", sha("fixture-evidence"), "synthetic fixture"),)
    marker = OutputValue(q(1, D), Uncertainty.unknown("a marker, not a measurement"), "fixture")

    def settle(call):
        return NodeOutcome("succeeded", {"marker": marker}, applicability=within,
                           state_proposal=StateProposal(q(60, "s"), states(owners)))

    def advance(call):
        return NodeOutcome("succeeded", {"marker": marker}, applicability=within,
                           state_proposal=StateProposal(q(120, "s"), states(advanced)))

    a = CallbackAuthority(f"{run_id}.settle", settle, config={"step": "settle"}, deterministic=True)
    b = CallbackAuthority(f"{run_id}.advance", advance, config={"step": "advance"}, deterministic=True)
    out = (NodeOutputSpec("marker", D),)
    nodes = (NodeSpec("settle", NodeKind.NUMERICAL_EXECUTION, a.ref, out, commits_state=True, writes_owners=tuple(owner_ids),
                      applicability_checks=("state_in_declared_range",), checkpointable=True),
             NodeSpec("advance", NodeKind.NUMERICAL_EXECUTION, b.ref, out, inputs=(NodeInput("after", "settle", "marker", D),),
                      commits_state=True, writes_owners=tuple(owner_ids), applicability_checks=("state_in_declared_range",)))
    request = SystemRunRequest.build(
        request_id=run_id, system=sysdef, scenario=scn, timeline=tl,
        initial_state=InitialStateSpec(q(0, "s"), states(owners)), nodes=nodes,
        observables=(RequestedObservable("settled", "settle", "marker", D),),
        environment_absent_reason="synthetic fixture: no environment timeline",
        profile=ExecutionProfile((), "off", True, ("settle",)))
    result = SystemExecutor(RuntimeContext(AuthorityRegistry((a, b)), system=sysdef, scenario=scn, timeline=tl)).run(request)
    if len(result.checkpoints) != 1 or len(result.state_history) != 3:
        raise RuntimeError(f"fixture run did not commit settle + advance: {result.status}")
    return Run(request, result.checkpoints[0], result)


# ---- an owned world: a declaration and its owners --------------------------------------------------------------------
@dataclass
class Owned:
    name: str
    declaration: ProtocolDeclaration
    run: Run
    models: ModelRegistry
    providers: ProviderRegistry
    ledgers: dict[str, BudgetLedger]
    experiments: dict[str, ScientificExperiment]
    base_world: ScientificWorld = field(repr=False)           # the BR1 synthetic world the declaration restates
    _world: ScientificWorld | None = field(default=None, repr=False)

    def authorities(self, *, state: Any = None, models: Any = None, providers: Any = None,
                    declarations: Any = None, budget: Any = None) -> Authorities:
        """The execution side's readers over its own owners (the base view unless one is replaced)."""
        return Authorities.of(
            RunStateReader(self.run.checkpoint if state is None else state),
            ModelRegistryReader(self.models if models is None else models, "fixture.models"),
            ProviderRegistryReader(self.providers if providers is None else providers, "fixture.providers"),
            BudgetReader(self.ledgers, self.experiments) if budget is None else budget,
            DeclarationReader((self.declaration,) if declarations is None else tuple(declarations)),
            UnitRegistryReader(),
        )

    @property
    def world(self) -> ScientificWorld:
        if self._world is None:
            self._world = project_world(self.declaration, self.authorities())
        return self._world

    def propose(self, action_id: str, assignments: Mapping[str, Any], observe: tuple[str, ...] = (),
                world: ScientificWorld | None = None) -> ProposedAction:
        w = self.world if world is None else world
        return ProposedAction(action_id, w.revision_id, dict(assignments), tuple(observe), HUMAN)


def _owner_id(world: ScientificWorld, name: str) -> str:
    for e in world.entities:
        if name in e.variables:
            return e.entity_id
    return "system"


def _provider_registry(statuses: Mapping[str, tuple[str, bool]]) -> ProviderRegistry:
    registry = ProviderRegistry()
    for pid, (version, available) in sorted(statuses.items()):
        status = br1.live_status(pid, version, available=available)
        registry.register(status.capability, lambda status=status: status)
    return registry


def provider_registry(owned: Owned, *, down: tuple[str, ...] = (), versions: Mapping[str, str] | None = None
                      ) -> ProviderRegistry:
    """Another state of the provider authority: some providers unavailable or at another version."""
    base = {p.provider_id: (p.version, True) for p in owned.base_world.providers}
    for pid, version in (versions or {}).items():
        base[pid] = (version, base[pid][1])
    for pid in down:
        base[pid] = (base[pid][0], False)
    return _provider_registry(base)


def experiment(experiment_id: str, max_observations: int, spent: int) -> ScientificExperiment:
    exp = ScientificExperiment(experiment_id, ScientificProblem(f"{experiment_id}.problem"),
                               ExperimentBudget(max_observations))
    for i in range(spent):
        exp.record(ScientificEvaluation(f"{experiment_id}.spent.{i}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                        detail="synthetic fixture: one observation of budget spent"))
    return exp


def ledger(total: float, spent: float, unit: str, ledger_id: str) -> BudgetLedger:
    account = BudgetLedger(total_budget=total, cost_unit=unit)
    if spent:
        account.settle(charge_id=f"{ledger_id}.spent", action_id="fixture", iteration=0, family=ActionFamily.EXPLORE,
                       realized=spent, detail="synthetic fixture: already spent")
    return account


def owned(name: str, base: ScientificWorld | None = None) -> Owned:
    """Re-express a BR1 synthetic world as a declaration plus the owner records it is projected from."""
    w = br1.WORLDS[name]() if base is None else base
    owners: dict[str, tuple[str, dict[str, tuple[Quantity, Uncertainty]]]] = {}
    sources, variables = [], []
    for v in w.variables:
        bound = v.value is not None and v.origin is not ValueOrigin.DECLARED
        if not bound:
            variables.append(v)
            continue
        if not isinstance(v.value, Quantity):          # a system state holds quantities only: left unbound (UNKNOWN)
            variables.append(dataclasses.replace(v, value=None, origin=None, source=None,
                                                 uncertainty=Uncertainty.unknown("not declared")))
            continue
        owner = _owner_id(w, v.name)
        role = "scenario" if v.role is R.NUISANCE_VARIABLE else "component"
        owners.setdefault(owner, (role, {}))[1][v.name] = (v.value, _restated(v.uncertainty))
        sources.append(ValueSource(v.name, owner, v.origin))
        guard = GUARD if v.uncertainty.kind is UncertaintyKind.INTERVAL else None
        variables.append(dataclasses.replace(v, value=None, origin=None, source=None,
                                             uncertainty=Uncertainty.unknown("not declared"), guard_band=guard))
    run = run_state(f"{w.world_id}.run", owners)
    models = ModelRegistry(tuple(a.model for a in w.applicability))
    providers = _provider_registry({p.provider_id: (p.version, True) for p in w.providers})
    b = w.budget
    ledgers: dict[str, BudgetLedger] = {}
    experiments: dict[str, ScientificExperiment] = {}
    budget = []
    if b.experiments is not None:
        experiments[f"{w.world_id}.experiment"] = experiment(f"{w.world_id}.experiment", b.experiments,
                                                             b.observations_spent)
        budget.append(BudgetSource.experiment("experiments", f"{w.world_id}.experiment"))
    if b.compute is not None and b.compute.max_function_evaluations is not None:
        ledgers[f"{w.world_id}.solver"] = ledger(b.compute.max_function_evaluations,
                                                 b.compute_used.function_evaluations, "solver_call",
                                                 f"{w.world_id}.solver")
        budget.append(BudgetSource.ledger("solver_calls", f"{w.world_id}.solver"))
    if b.compute is not None and b.compute.max_wall_seconds is not None:
        ledgers[f"{w.world_id}.wall"] = ledger(b.compute.max_wall_seconds, b.compute_used.wall_seconds, "second",
                                               f"{w.world_id}.wall")
        budget.append(BudgetSource.ledger("wall_time", f"{w.world_id}.wall"))
    for dim, basis in b.unbounded:
        budget.append(BudgetSource.unbounded(dim, basis))
    declaration = ProtocolDeclaration(
        declaration_id=w.world_id, revision=1, world_id=w.world_id, declared_by=w.declared_by, basis=w.basis,
        variables=tuple(variables), entities=w.entities, constraints=w.constraints, actions=w.actions,
        channels=w.channels, references=w.references, values=tuple(sources),
        models=tuple((a.model.model_id, a.model.version) for a in w.applicability),
        providers=tuple(p.provider_id for p in w.providers), budget=tuple(budget))
    return Owned(name, declaration, run, models, providers, ledgers, experiments, w)


def gen1_pool() -> Owned:
    """The Gen1 failure-class protocol (two declared current levels), owner-bound."""
    return owned("gen1_pool", br1.gen1_pool_world())


WORLDS: dict[str, Callable[[], Owned]] = {
    "battery": lambda: owned("battery"),
    "hvac_chamber": lambda: owned("hvac_chamber"),
    "hvac_field": lambda: owned("hvac_field"),
    "drone": lambda: owned("drone"),
    "motor": lambda: owned("motor"),
}

#: One proposal per action that the BR1 benchmark built FEASIBLE by construction (``br1.base``).
base = br1.base
