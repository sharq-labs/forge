"""verify-5-scope s2: what F11-2's numpy.str_ trigger needs.
  steady numpy ids : an execution side that always keys its accounts with numpy.str_ -> refused at construction?
  keep after restore: the ill-typed entry stays in the mapping after the checkpoint restore -> re-dispatch refused?
"""
import numpy as np

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]

o = ax.owned("battery")
try:
    BudgetReader.following(lambda: ({np.str_(k): v for k, v in o.ledgers.items()},
                                    {np.str_(k): v for k, v in o.experiments.items()}))
    print("[steady numpy ids] reader built")
except Exception as exc:  # noqa: BLE001
    print(f"[steady numpy ids] {type(exc).__name__}: {exc}")

o = ax.owned("battery")
eid = next(iter(o.experiments))
saved = o.experiments[eid].to_dict()
state = {"after": False}


def accounts():
    exps = dict(o.experiments)
    if state["after"]:
        exps[np.str_("latest.run")] = ScientificExperiment.from_dict(saved)
    return dict(o.ledgers), exps


reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []


def executor(authorization):
    calls.append(1)
    o.experiments[eid].record(ScientificEvaluation(f"run-{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                   detail="the executed pulse"))
    state["after"] = True


gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
gateway.dispatch(r.admitted)
a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
o.experiments[eid] = ScientificExperiment.from_dict(saved)          # restore; the ill-typed entry is kept
try:
    gateway.dispatch(r.admitted)
    d = "DISPATCHED AGAIN"
except DispatchRefused as exc:
    d = f"refused ({str(exc)[:90]})"
print(f"[keep after restore] after the run: {a.status.value} {a.codes()} | after restore: {d} | executor ran {len(calls)}")
