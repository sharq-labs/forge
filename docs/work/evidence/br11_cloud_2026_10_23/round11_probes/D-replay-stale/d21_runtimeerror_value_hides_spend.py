"""R11-D d21: the 'moved while serialized' class is decided by exception TYPE (owners._written: any RuntimeError other
than RecursionError, which includes NotImplementedError).  A spent state whose serialization raises a RuntimeError
every time (a value the execution side stored; nothing moves) is refused for that verification only, so it is never
observed, and a restore to the pre-spend state re-authorizes the executed action.  Compare with the same value raising
TypeError (refused for good, as round 10 intends)."""
import json

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def make(exc):
    class Lazy(dict):                     # e.g. a lazily loaded mapping whose backing store is not implemented here
        def items(self):
            raise exc("not available in this process")
    return Lazy(a=1)


for exc in (NotImplementedError, RuntimeError, TypeError):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    calls = []

    def executor(a):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="spent"))
        o.experiments[eid].metadata["cache"] = make(exc)

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(json.loads(json.dumps(o.experiments[eid].to_dict())))
    gw.dispatch(r.admitted)
    seen = []
    for i in range(3):                    # three verifications handed the spent state
        try:
            reader.read(OwnerKind.EXPERIMENT, eid)
            seen.append("read")
        except OwnerUnavailable as e:
            seen.append("FOR GOOD" if "from then on" in str(e) else "this verification only")
    o.experiments[eid] = before            # the execution side restores the pre-spend state (replaces the object)
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as e:
        again = "refused: " + str(e)[:80]
    print(f"[{exc.__name__}] verifications handed the spend: {seen}; after the restore: {again}; executor calls "
          f"{len(calls)}")
