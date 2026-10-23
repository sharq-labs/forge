"""_written's RecursionError clause (owners.py:116-117): a spend whose state its owner's encoder cannot write down
because it is too deep raises RecursionError, a RuntimeError subclass.  At aad2f69 it is classified for good (the
account is refused from then on, so a restore re-authorizes nothing).  Run on a tree where the clause is removed it
falls into 'moved while serialized' (once): the spend is never observed and a restore re-dispatches the executed
action.  Sequential; public API; an executor that records the observation and a deep metadata value."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []
deep = []
cur = deep
for _ in range(100000):
    nxt = []; cur.append(nxt); cur = nxt

def executor(auth):
    calls.append(1)
    o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    o.experiments[eid].metadata["trace"] = deep              # the spent state is too deep for the owner's encoder

gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
gw.dispatch(r.admitted)
try:
    reader.read(OwnerKind.EXPERIMENT, eid); print("spent state served")
except OwnerUnavailable as exc:
    print("spent state refused:", str(exc)[:160])
o.experiments[eid] = before                                  # the execution side restores
try:
    gw.dispatch(r.admitted); print("re-dispatch: DISPATCHED; executor calls", len(calls))
except DispatchRefused as exc:
    print("re-dispatch refused:", str(exc)[:100], "; executor calls", len(calls))
