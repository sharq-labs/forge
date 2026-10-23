"""R11-C c1108: sequential, through ExecutionDesk.gateway(): the executor records the run's observation, then the
execution side stores a 3000-deep nested trace in the study metadata, so the
owner's ScientificExperiment.from_dict refuses the owner's own to_json text (round 10: _Unreadable -> refused by the
reader for good).  A Mind admission request is verified on that state; the execution side then restores the pre-run
checkpoint (object replaced, budget restored) and the Mind re-dispatches the same admitted action."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
auth = o.authorities()
calls = []


def executor(authorization):
    calls.append(1)
    exp = o.experiments[eid]
    exp.record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    deep = []
    node = deep
    for _ in range(3000):
        node.append([])
        node = node[0]
    exp.metadata["trace"] = deep                                            # deeply nested (RecursionError)


gateway = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(o.world)
r = gateway.admit(space, o.propose("simulate_pulse", *SIM))
checkpoint = o.experiments[eid].to_dict()
gateway.dispatch(r.admitted)
later = gateway.admit(space, o.propose("simulate_pulse", *SIM))          # verified on the cut state
why = [c.detail.get("why", "")[-90:] for c in later.verification.checks if c.status.name != "VERIFIED"]
print("admission on the cut state:", later.status.value, later.codes(), why[:1])
o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)           # restore
try:
    gateway.dispatch(r.admitted)
    print("re-dispatch after the restore: DISPATCHED AGAIN; executor ran", len(calls))
except DispatchRefused as exc:
    print("re-dispatch after the restore: refused (", str(exc)[:80], "); executor ran", len(calls))
