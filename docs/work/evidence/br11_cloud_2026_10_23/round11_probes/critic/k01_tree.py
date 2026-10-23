"""K11-01: what in BudgetReader._account's experiment branch runs OUTSIDE the classifying try (owners.py:393-412)?
(a) the deep case (reader-side deepcopy), sequential spend -> restore -> re-dispatch, at aad2f69;
(b) the same with a json round trip in place of deepcopy (the narrowest fix): does anything else outside the try raise?
(c) an owner-readable state whose written text lacks 'accounting' (instance to_dict) -> line 403 KeyError."""
import json, sys, traceback
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit)
from engcore.mind.world import owners as ow
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]

def nest(d):
    v = "leaf"
    for _ in range(d):
        v = [v]
    return v

def run(label, mutate_spent):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    calls = []
    def executor(a):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        mutate_spent(o.experiments[eid])
    g = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    g.dispatch(r.admitted)
    try:
        got = reader.read(OwnerKind.EXPERIMENT, eid)
        mid = f"read revision {got.revision}"
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        where = [f"{f.filename.split('/')[-1]}:{f.lineno}" for f in tb if 'owners.py' in f.filename][-1:]
        mid = f"{type(exc).__name__} {where} {str(exc)[:70]}"
    o.experiments[eid] = before
    try:
        g.dispatch(r.admitted); out = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out = f"refused ({str(exc)[:60]})"
    except Exception as exc:
        out = f"RAISED {type(exc).__name__}"
    print(f"{label:48s} | read on the spent state: {mid} | after restore: {out} | executor ran {len(calls)}")

def deep(d):
    return lambda e: e.metadata.__setitem__("deep", nest(d))

def no_accounting(e):
    real = type(e).to_dict
    def td():
        p = real(e); p.pop("accounting"); return p
    e.to_dict = td

print("python", sys.version.split()[0], "limit", sys.getrecursionlimit())
run("(a) deep 300", deep(300))
run("(a) deep 600", deep(600))
run("(c) to_dict without 'accounting' (owner reads it back)", no_accounting)
real_deepcopy = ow.copy.deepcopy
pass
for d in (600, 2000, 5000):
    run(f"(b) json round trip instead of deepcopy, deep {d}", deep(d))
ow.copy.deepcopy = real_deepcopy

def fractional_budget(e):        # (d) a budget its owner writes as 5.5 and reads back as 5: the torn check fails EVERY read
    object.__setattr__(e.budget, "max_observations", e.budget.max_observations + 0.5)
run("(d) budget that does not round-trip (deterministic 'torn')", fractional_budget)
