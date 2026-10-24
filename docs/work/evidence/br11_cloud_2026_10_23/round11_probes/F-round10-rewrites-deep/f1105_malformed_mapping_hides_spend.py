"""R11-F f1105: a verification whose accounts() RETURNS a mapping the reader's constructor refuses (one account object
under two ids; an id that is not exactly str) leaves without comparing anything (pinned(): 'could not state its budget
accounts', per verification).  So a spend handed in such a mapping is never observed, and a restore (a well-formed
mapping again) re-authorizes the executed action.  Sequential, through ExecutionDesk.gateway().  README §4 lists what is
never observed: a state no verification was handed and read back, a state that moved while serialized, and the state
of a verification whose accounts() RAISES; this one returned."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


import numpy as np


def Id(x):
    return np.str_(x)                                      # ids as a numpy array or pandas index yields them


def run(mode):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    saved = o.experiments[eid].to_dict()
    state = {"alias": False}

    def accounts():
        exps = dict(o.experiments)
        if state["alias"]:
            if mode == "alias":
                exps["latest.run"] = exps[eid]                 # the run's study also listed as the latest one
            else:
                exps[Id("latest.run")] = ScientificExperiment.from_dict(saved)
        return dict(o.ledgers), exps

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run-{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="the executed pulse"))
        state["alias"] = True

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    o.experiments[eid] = ScientificExperiment.from_dict(saved)      # restore the pre-run checkpoint
    state["alias"] = False
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:80]})"
    return f"admission on the spent mapping: {a.status.value} {a.codes()} | re-dispatch after the restore: {d} | " \
           f"executor ran {len(calls)}"


for mode in ("alias", "numpy str_ id"):
    print(f"[{mode}] {run(mode)}")
