"""The re-check after the wait (owners.py:483-485): a verification D that accepted the rollback waits for P, which was
handed the spent account in a state its owner cannot write down; P's comparison refuses the account for good
(_diverged).  At aad2f69 D, re-checking, is refused.  On a tree without the `_diverged` re-check D decides on the
rollback and the executed action is dispatched again.  Deterministic (events in the execution side's accounts())."""
import threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
p_handed, p_go = threading.Event(), threading.Event()

def accounts():
    mapping = (dict(o.ledgers), dict(o.experiments))
    if threading.current_thread().name == "P":
        p_handed.set(); p_go.wait(10)                     # P holds the spent account; its store answers later
    return mapping

reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []

def executor(auth):
    calls.append(1)
    o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    o.experiments[eid].metadata["note"] = {1, 2}          # the spent state cannot be written down

gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
gw.dispatch(r.admitted)
p = threading.Thread(target=lambda: (lambda: reader.pinned())() if True else None, name="P", daemon=True)
def p_run():
    try:
        reader.pinned()
    except Exception:  # noqa: BLE001
        pass
p = threading.Thread(target=p_run, name="P", daemon=True); p.start(); assert p_handed.wait(10)
o.experiments[eid] = before                                # the execution side restores (replaces)
threading.Timer(0.2, p_go.set).start()                     # P is answered while D waits for it
try:
    gw.dispatch(r.admitted); print("re-dispatch: DISPATCHED; executor calls", len(calls))
except DispatchRefused as exc:
    print("re-dispatch refused:", str(exc)[:110], "; executor calls", len(calls))
p.join(10)
