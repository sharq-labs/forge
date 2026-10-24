"""R11-D d20c: real threads, no tracing.  The execution side keeps an observation account at its budget and, to record
the next observation, first tops the budget up by one (an honest move of the owner: the history only extends).  A
verifier thread pins the following reader repeatedly.  When the top-up and the record land between the owner's
to_dict writing 'budget' and writing 'evaluations', the text holds more observations than its own budget allows; the
owner's from_dict refuses it, and BudgetReader classifies that as _Unreadable: the account is refused FOR GOOD,
although it only ever moved forward and every state the execution side held was readable."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

sys.setswitchinterval(float(sys.argv[1]) if len(sys.argv) > 1 else 1e-5)
SPIN = float(sys.argv[2]) if len(sys.argv) > 2 else 0.002
o = ax.owned("battery")
eid = next(iter(o.experiments))
E = o.experiments[eid]
while E.remaining_observations > 0:
    E.record(ScientificEvaluation(f"fill.{E.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
stop = threading.Event()
steps = {"n": 0, "unreadable_states_held": 0}


def execution_side():
    while not stop.is_set():
        E.budget = ExperimentBudget(E.budget.max_observations + 1)        # top up by one
        E.record(ScientificEvaluation(f"obs.{E.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        steps["n"] += 1
        t = time.perf_counter()
        while time.perf_counter() - t < SPIN:                             # (busy: keeps the account small)
            pass


th = threading.Thread(target=execution_side, daemon=True)
th.start()
counts = {"read": 0, "this verification": 0, "for good": 0}
first = None
t0 = time.time()
while time.time() - t0 < 6.0:
    try:
        reader.read(OwnerKind.EXPERIMENT, eid)
        counts["read"] += 1
    except OwnerUnavailable as e:
        if "from then on" in str(e):
            counts["for good"] += 1
            first = first or str(e)[:170]
            if counts["for good"] >= 3:
                break
        else:
            counts["this verification"] += 1
stop.set()
th.join(5)
print("steps:", steps["n"], "verifications:", counts)
print("first refusal for good:", first)
print("the account now, read by its owner:", ScientificExperiment.from_dict(E.to_dict()).attempts, "attempts;",
      "a new reader reads it:", BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
      .read(OwnerKind.EXPERIMENT, eid).revision)
