"""verify-1-scope: (a) the documented residual's own outcome at this tree: dispatch, the executor records a PLAIN
evaluation, NO verification in between, the execution side restores, re-dispatch.  (b) whether the owner's own canonical
serialization (to_json of the experiment, the digest rule) works for the states the follower refuses."""
import datetime
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.scientific.results.immutable import FrozenList, FrozenMapping
try:
    from engcore.mind.world.owners import to_json
except ImportError:
    to_json = None

SIM = ax.base("battery")["simulate_pulse"]


def baseline(verify_between):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(a):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata={"seed": 1}))
    gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    gw.dispatch(r.admitted)
    if verify_between:
        reader.pinned()
    o.experiments[eid] = before
    try:
        gw.dispatch(r.admitted)
        after = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        after = "refused " + str(exc)[str(exc).find("("):][:50]
    print(f"plain metadata, verification between={verify_between}: after restore: {after} | ran {len(calls)}")


baseline(False)
baseline(True)

for label, meta in {"nested list": {"seeds": [1, 2]}, "datetime": {"t": datetime.datetime(2026, 1, 1)}}.items():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    e = o.experiments[eid]
    e.record(ScientificEvaluation("x", {}, status=EvaluationStatus.NOT_CONVERGED, detail="d", metadata=meta))
    md = e.to_dict()["evaluations"][-1]["metadata"]
    print(label, "| to_dict metadata value types:", {k: type(v).__name__ for k, v in md.items()})
    try:
        to_json(e); print(label, "| owner's canonical to_json of the experiment: ok")
    except Exception as exc:  # noqa: BLE001
        print(label, "| owner's canonical to_json of the experiment raises:", type(exc).__name__, str(exc)[:60])
