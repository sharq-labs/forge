"""verify-4: F11-2 variants. Each mode: the executor records an evaluation on the study the world reads, then the
accounts() mapping changes per mode; an admission on the spent mapping; checkpoint restore (mapping back to normal unless
'persist'); re-dispatch."""
import enum
import sys

import numpy as np

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


class Sid(enum.StrEnum):
    LATEST = "latest.run"


class SubExp(ScientificExperiment):
    pass


def run(mode):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    saved = o.experiments[eid].to_dict()
    state = {"after": False, "persist": mode.endswith("+persist")}
    base_mode = mode.replace("+persist", "")

    def accounts():
        exps = dict(o.experiments)
        if state["after"]:
            if base_mode == "control":
                pass
            elif base_mode == "alias":
                exps["latest.run"] = exps[eid]
            elif base_mode == "numpy":
                exps[np.str_("latest.run")] = ScientificExperiment.from_dict(saved)
            elif base_mode == "strenum":
                exps[Sid.LATEST] = ScientificExperiment.from_dict(saved)
            elif base_mode == "subclass-value":
                exps["latest.run"] = SubExp.from_dict(saved) if hasattr(SubExp, "from_dict") else None
            elif base_mode == "raises":
                raise RuntimeError("accounts() fails after the run")
            elif base_mode == "unreadable-extra":
                bad = ScientificExperiment.from_dict(saved)
                bad.metadata["notes"] = {"owner": "campaign"}
                bad.metadata["notes"]["self"] = bad.metadata["notes"]     # its owner cannot write it down
                exps["latest.run"] = bad
        return dict(o.ledgers), exps

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None, r.codes()
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run-{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="the executed pulse"))
        state["after"] = True

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    why = ""
    try:
        authorities.memoized().read(__import__("engcore.mind.world", fromlist=["OwnerKind"]).OwnerKind.EXPERIMENT, eid)
    except Exception as exc:  # noqa
        why = str(exc)[:90]
    o.experiments[eid] = ScientificExperiment.from_dict(saved)      # restore the pre-run checkpoint
    if not state["persist"]:
        state["after"] = False
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:110]})"
    return f"spent: {a.status.value} {a.codes()} [{why}] | re-dispatch after restore: {d} | executor ran {len(calls)}"


modes = sys.argv[1:] or ["control", "alias", "numpy", "strenum", "subclass-value", "raises", "unreadable-extra",
                         "alias+persist", "numpy+persist"]
for m in modes:
    try:
        print(f"[{m}] {run(m)}", flush=True)
    except Exception as exc:  # noqa
        print(f"[{m}] PROBE ERROR {type(exc).__name__}: {exc}", flush=True)
