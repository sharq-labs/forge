"""_written (owners.py:111-121) and the experiment read-back (owners.py:397-402) classify a failure: RuntimeError (not
recursion) = 'moved while serialized' (refused once); ANY other failure, including the owner's from_dict refusing the
text to_dict produced, = _Unreadable = the account refused by the reader FOR GOOD (owners.py:450-456).  But a torn read
of a state that moved while it was serialized surfaces as the owner's own validation error (ValueError /
ScientificCoreError), not RuntimeError.  So an honest top-up concurrent with a verification refuses an account forever,
although every state the owner ever held reads back -- while README section 4 / owners.py:327-328 say 'a state that moved
while it was serialized is refused for that verification only'.

The interleaving is forced with sys.settrace in the verifying thread only (scheduling control, as round 8/10 probes did);
the execution side uses only owner API: a ledger top-up raising total then reservation (every intermediate state valid),
and an experiment top-up (a new ExperimentBudget) followed by one recorded observation.
CASE=ledger | experiment."""
import os, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
import engcore.sria.campaign.budget as budget_mod
import engcore.scientific.experiments.experiment as exp_mod

CASE = os.environ.get("CASE", "ledger")
led = BudgetLedger(total_budget=10.0, reserved_validation_budget=2.0, cost_unit="hour")
exp = ax.experiment("camp", 2, 2)                 # exhausted: 2 of 2 observations
reader = BudgetReader.following(lambda: ({"camp.ledger": led}, {"camp": exp}))

def top_up():
    if CASE == "ledger":
        for st in ((30.0, 2.0), (30.0, 15.0)):   # total first: every state the owner holds is valid
            led.total_budget, led.reserved_validation_budget = st[0], 2.0 if st is None else st[1]
            BudgetLedger.from_dict(led.to_dict())   # (each intermediate state reads back)
    else:
        exp.budget = ExperimentBudget(3)          # top-up, then one more observation
        exp.record(ScientificEvaluation("camp.more", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        ScientificExperiment.from_dict(exp.to_dict())   # (the state reads back)

LINE = {"ledger": (budget_mod.__file__, "to_dict", 330), "experiment": (exp_mod.__file__, "to_dict", 320)}[CASE]
done = {"x": False}
def tracer(frame, event, arg):
    if frame.f_code.co_filename == LINE[0] and frame.f_code.co_name == LINE[1]:
        def local(frame, event, arg):
            if event == "line" and frame.f_lineno == LINE[2] and not done["x"]:
                done["x"] = True
                t = threading.Thread(target=top_up); t.start(); t.join()   # the execution side moves now
            return local
        return local
    return None

kind, rid = (OwnerKind.BUDGET_LEDGER, "camp.ledger") if CASE == "ledger" else (OwnerKind.EXPERIMENT, "camp")
def verify(trace):
    if trace:
        sys.settrace(tracer)
    try:
        return "served revision " + reader.read(kind, rid).revision
    except OwnerUnavailable as exc:
        return "refused: " + str(exc)[:230]
    finally:
        sys.settrace(None)

print(CASE, "| verification during the top-up:", verify(True))
for i in range(2):
    print(CASE, f"| later verification {i} (account at rest):", verify(False))
print("owner reads the current state back:", (BudgetLedger.from_dict(led.to_dict()).digest[:12] if CASE == "ledger"
      else len(ScientificExperiment.from_dict(exp.to_dict()).evaluations)))
