"""p23 without settrace: an execution side tops up an exhausted experiment (new ExperimentBudget) and records one more
observation, again and again, while one thread verifies through a following BudgetReader.  Count verifications until
the account is refused FOR GOOD (owners.py:450-456), though every state the owner held reads back."""
import sys, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget

sys.setswitchinterval(float(sys.argv[1]) if len(sys.argv) > 1 else 1e-5)
exp = ax.experiment("camp", 1, 1)
reader = BudgetReader.following(lambda: ({}, {"camp": exp}))
stop = threading.Event()

def execution_side():
    i = 0
    while not stop.is_set():
        i += 1
        exp.budget = ExperimentBudget(exp.budget.max_observations + 1)     # top-up (the account moves forward)
        exp.record(ScientificEvaluation(f"camp.{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        time.sleep(0)

threading.Thread(target=execution_side, daemon=True).start()
t0, n, once = time.perf_counter(), 0, 0
verdict = "never refused for good"
while time.perf_counter() - t0 < 20:
    n += 1
    try:
        reader.read(OwnerKind.EXPERIMENT, "camp")
    except OwnerUnavailable as exc:
        if "from then on" in str(exc):
            verdict = f"refused FOR GOOD at verification {n} after {time.perf_counter()-t0:.2f}s: {str(exc)[:150]}"
            break
        once += 1
stop.set()
print(verdict, "| refused once (torn, moved):", once, "| evaluations now:", len(exp.evaluations))
