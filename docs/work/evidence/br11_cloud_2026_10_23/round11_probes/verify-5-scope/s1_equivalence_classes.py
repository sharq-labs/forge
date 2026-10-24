"""verify-5-scope s1: is F11-2's outcome (a spend handed in a mapping the reader refuses as a whole is never observed, a
restore re-dispatches) NEW beyond the documented residuals?  Same harness as f1105, with the post-run accounts() made
to fail in several ways:
  raise          : accounts() raises right after the run (documented: 'the state of a verification whose accounts() raises')
  subclass value : an extra entry whose value is a ScientificExperiment subclass (constructor's exact-type check on values,
                   round 6: B6-M5 'the constructor refuses a malformed account set for the whole reader')
  ledger as dict : an extra ledger entry that is a plain dict (same check)
  no verification: no verification at all between the run and the restore (documented: 'a spend and its rollback both
                   between two verifications look like no change')
  numpy str_ id  : F11-2 (round 10's id check)
  alias          : F11-2 (round 6's duplicate-object check)
  control        : a well-formed extra entry: the spend must be observed and the re-dispatch refused
"""
import numpy as np

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


class SubExp(ScientificExperiment):
    pass


def run(mode):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    saved = o.experiments[eid].to_dict()
    state = {"after": False}

    def accounts():
        exps = dict(o.experiments)
        leds = dict(o.ledgers)
        if state["after"]:
            if mode == "raise":
                raise RuntimeError("the execution side's account store is busy")
            if mode == "alias":
                exps["latest.run"] = exps[eid]
            elif mode == "numpy str_ id":
                exps[np.str_("latest.run")] = ScientificExperiment.from_dict(saved)
            elif mode == "subclass value":
                exps["latest.run"] = SubExp.from_dict(saved)
            elif mode == "ledger as dict":
                leds["latest.run"] = {"not": "a ledger"}
            elif mode == "control":
                exps["latest.run"] = ScientificExperiment.from_dict(saved)
        return leds, exps

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
    if mode != "no verification":
        a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
        a = f"{a.status.value} {a.codes()}"
    else:
        a = "(no verification)"
    o.experiments[eid] = ScientificExperiment.from_dict(saved)      # restore the pre-run checkpoint
    state["after"] = False
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:70]})"
    return f"after the run: {a} | after restore: {d} | executor ran {len(calls)}"


for mode in ("control", "no verification", "raise", "subclass value", "ledger as dict", "alias", "numpy str_ id"):
    try:
        print(f"[{mode}] {run(mode)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{mode}] ERROR {type(exc).__name__}: {exc}")
