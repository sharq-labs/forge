"""A spent experiment state that to_json writes but ScientificExperiment.from_dict refuses (the executor records an
observation and the execution side lowers the experiment's budget below what is recorded: the owner object holds it,
its from_dict refuses it).  aad2f69: refused for good, a restore re-authorizes nothing.  On a tree where that from_dict
failure is classified 'once' the spend is never observed and the restore re-dispatches."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []
def executor(auth):
    calls.append(1)
    e = o.experiments[eid]
    e.record(ScientificEvaluation("run.1", {}, status="ok" and EvaluationStatus.NOT_CONVERGED, detail="x"))
    e.budget = ExperimentBudget(max(1, e.observations - 1))   # the campaign is stopped: budget cut below what is spent
gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
print("observations before:", before.observations, "max:", before.budget.max_observations)
gw.dispatch(r.admitted)
from engcore.mind.world import OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
try:
    reader.read(OwnerKind.EXPERIMENT, eid); print("spent state served")
except OwnerUnavailable as exc:
    print("a verification is handed the spent state:", str(exc)[:120])
o.experiments[eid] = before
try:
    gw.dispatch(r.admitted); print("re-dispatch: DISPATCHED; executor calls", len(calls))
except DispatchRefused as exc:
    print("re-dispatch refused:", str(exc)[:100], "; executor calls", len(calls))
