"""R11-F f1103: the re-check after round 10's bounded wait has two clauses (owners.py:466-470): an accepted account
another verification moved past is behind, and one refused for good meanwhile is refused.  The second clause is what
protects a spend handed to a verification still in flight when the re-dispatch compares, when that spend's state
cannot be written down (round 10: refused for good because 'it may hold a spend').  Deterministic, through
ExecutionDesk.gateway():
  dispatch #1 executes, records an observation, and leaves an unwritable value in the study metadata;
  P is handed that spent state and held in flight; the execution side restores the pre-run checkpoint;
  D (re-dispatch) is handed the restore, compares (accepts: it extends nothing), and waits for P;
  P reads back: the state is unwritable -> the account is refused for good; D re-checks.
Expected at aad2f69: D refused, executor ran once.  Run the same file in a tree whose re-check drops the 'diverged'
clause (mutant M1) to see whether any control notices."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
import engcore

print("engcore from", engcore.__file__)
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
saved = o.experiments[eid].to_dict()
p_handed, p_go = threading.Event(), threading.Event()


def accounts():
    mapping = (dict(o.ledgers), dict(o.experiments))
    if threading.current_thread().name == "P":
        p_handed.set()
        p_go.wait(10)
    return mapping


reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []


def executor(authorization):
    calls.append(1)
    o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    o.experiments[eid].metadata["note"] = {1, 2}                  # the spent state cannot be written down


gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
gateway.dispatch(r.admitted)
out = {}


def p_run():
    try:
        reader.pinned()
        out["P"] = "pinned"
    except Exception as exc:  # noqa: BLE001
        out["P"] = f"{type(exc).__name__}"


def d_run():
    try:
        gateway.dispatch(r.admitted)
        out["D"] = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out["D"] = f"refused ({str(exc)[:90]})"


p = threading.Thread(target=p_run, name="P", daemon=True)
p.start()
assert p_handed.wait(10)
o.experiments[eid] = ScientificExperiment.from_dict(saved)       # restore the pre-run checkpoint
d = threading.Thread(target=d_run, name="D", daemon=True)
d.start()
t0 = time.perf_counter()
waiting = False
while time.perf_counter() - t0 < 5 and not waiting:
    f = sys._current_frames().get(d.ident)
    names = []
    while f is not None:
        names.append(f.f_code.co_name)
        f = f.f_back
    waiting = "_observe_all" in names and "wait" in names
    time.sleep(0.002)
p_go.set()
d.join(10)
p.join(10)
print("D waited for P:", waiting, "| D (handed the restore):", out.get("D"), "| executor ran", len(calls))
