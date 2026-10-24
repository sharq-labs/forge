"""R11-D d20: an honest declaration top-up that lands WHILE a verification serializes the account (a torn
serialization) is classified as a state its owner cannot write down (_Unreadable) and refuses the account FOR GOOD,
although README section 4 / owners.py:327 say a state that moved while it was serialized is refused for that
verification only.  The interleaving is forced deterministically with sys.settrace in the verifying thread (the
callback performs the execution side's two-step top-up at a fixed line of the owner's to_dict, as another thread
would).  Then the account is honest, readable and only moved forward, and every later verification is still refused.
"""
import inspect
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger

SIM = ax.base("battery")["simulate_pulse"]


def line_of(func, needle):
    src, start = inspect.getsourcelines(func)
    for i, s in enumerate(src):
        if needle in s:
            return start + i
    raise AssertionError(needle)


def inject(code, lineno, action):
    fired = {"n": 0}

    def local(frame, event, arg):
        if event == "line" and frame.f_lineno == lineno and fired["n"] == 0:
            fired["n"] += 1
            action()
        return local

    def glob(frame, event, arg):
        if frame.f_code is code:
            return local
        return None

    sys.settrace(glob)
    return fired


def read(reader, kind, rid):
    try:
        rec = reader.read(kind, rid)
        return f"read revision {rec.revision}"
    except OwnerUnavailable as e:
        s = str(e)
        return "OWNER_UNAVAILABLE (" + ("FOR GOOD" if "from then on" in s else "this verification") + "): " + s[:150]


# ---- ledger: total_budget read before the top-up, reserved_validation_budget after it -------------------------------
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
L = o.ledgers[lid]
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
print("ledger before:", L.total_budget, L.reserved_validation_budget, "|", read(reader, OwnerKind.BUDGET_LEDGER, lid))
T = L.total_budget


def topup():                                       # the execution side's honest two-step top-up (another thread)
    L.total_budget = T + 100.0
    L.reserved_validation_budget = T + 50.0


fired = inject(BudgetLedger.to_dict.__code__, line_of(BudgetLedger.to_dict, '"reserved_validation_budget":'), topup)
out = read(reader, OwnerKind.BUDGET_LEDGER, lid)
sys.settrace(None)
print("torn verification (top-up landed mid-serialization, fired", fired["n"], "):", out)
print("ledger now:", L.total_budget, L.reserved_validation_budget, "digest readable by its owner:",
      BudgetLedger.from_dict(L.to_dict()).digest[:12])
for i in range(3):
    print(f"  later verification {i}:", read(reader, OwnerKind.BUDGET_LEDGER, lid))
print("  a new reader over the same accounts:", read(BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments))),
                                                   OwnerKind.BUDGET_LEDGER, lid))
w = o.world
r = admit(FeasibleActionSpace.build(w), o.propose("simulate_pulse", *SIM, world=w), auth)
print("  admission through the old reader:", r.status.value, r.codes())

# ---- experiment: budget written before the top-up, evaluations after it -------------------------------------------
o = ax.owned("battery")
eid = next(iter(o.experiments))
E = o.experiments[eid]
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
print("\nexperiment before:", E.budget, "observations", E.observations, "|", read(reader, OwnerKind.EXPERIMENT, eid))
# exhaust it first, honestly
while E.remaining_observations > 0:
    E.record(ScientificEvaluation(f"fill.{E.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
print("exhausted:", E.observations, "of", E.budget.max_observations, "|", read(reader, OwnerKind.EXPERIMENT, eid))


def topup_and_record():                            # top up, then record the next observation (another thread)
    E.budget = ExperimentBudget(E.budget.max_observations + 5)
    E.record(ScientificEvaluation("after-topup", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))


fired = inject(ScientificExperiment.to_dict.__code__, line_of(ScientificExperiment.to_dict, '"evaluations":'),
               topup_and_record)
out = read(reader, OwnerKind.EXPERIMENT, eid)
sys.settrace(None)
print("torn verification (fired", fired["n"], "):", out)
print("experiment now:", E.budget, "observations", E.observations, "readable by its owner:",
      ScientificExperiment.from_dict(E.to_dict()).attempts)
for i in range(3):
    print(f"  later verification {i}:", read(reader, OwnerKind.EXPERIMENT, eid))
print("  a new reader:", read(BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments))),
                              OwnerKind.EXPERIMENT, eid))
