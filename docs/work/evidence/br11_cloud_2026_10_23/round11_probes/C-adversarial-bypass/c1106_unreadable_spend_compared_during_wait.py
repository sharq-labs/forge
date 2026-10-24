"""R11-C c1106: the round-10 for-good rule combined with the bounded wait, through ExecutionDesk.gateway().

The executor's run records an observation and the execution side's state then cannot be read back by the owner
(variant 'nan': a non-finite metadata value, to_json refuses it; variant 'cut': the study's budget is cut below what
was observed, so the owner's from_dict refuses its own text).  A verification W is handed that state, and is still in
flight (its accounts() returns 0.3 s later) when the execution side restores the pre-run checkpoint (object replaced)
and the Mind re-dispatches the same admitted action D: D compares while W is in flight, waits for W, W refuses the
account for good, and D must re-check and be refused.  Run at aad2f69 (expected: refused) and under the mutant
'M2_no_diverged_recheck' (D decides on what it accepted before the wait)."""
import os
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def run(variant):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    handed, resume = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "W":
            handed.set()
            resume.wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        exp = o.experiments[eid]
        exp.record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        if variant == "nan":
            exp.metadata["last_wall_s"] = float("nan")
        else:
            exp.budget = ExperimentBudget(max(1, exp.observations - 1))    # the operator cuts the study

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    checkpoint = o.experiments[eid].to_dict()
    gateway.dispatch(r.admitted)
    w = threading.Thread(target=lambda: _quiet(reader.pinned), name="W", daemon=True)
    w.start()
    assert handed.wait(10)
    o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)       # restore
    threading.Timer(0.3, resume.set).start()
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:80]})"
    w.join(10)
    print(f"{variant:4s} | D (compared while W in flight): {d} | executor ran {len(calls)}")


def _quiet(f):
    try:
        f()
    except Exception:  # noqa: BLE001
        pass


for v in ("nan", "cut"):
    run(v)
