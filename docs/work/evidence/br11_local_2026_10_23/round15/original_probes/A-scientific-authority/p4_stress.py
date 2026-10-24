"""Honest in-place movers under real threads: a campaign thread records evaluations and settles charges while three
threads verify (some from a deep stack).  Nothing may be refused for good, and no refusal may say 'from then on'."""
import sys, threading, time, collections
from common import *
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
print("owners:", owners_mod.__file__)
sys.setrecursionlimit(3000)
o = ax.owned("battery")
lid = solver(o)
eid = next(iter(o.experiments))
exp = o.experiments[eid]
if exp.budget.max_attempts is not None or True:
    pass
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
stop = time.monotonic() + float(sys.argv[1]) if len(sys.argv) > 1 else time.monotonic() + 6
outcomes = collections.Counter()
lock = threading.Lock()

def mover():
    i = 0
    while time.monotonic() < stop:
        i += 1
        o.ledgers[lid].settle(charge_id=f"c{i}", action_id="other", iteration=i, family=ActionFamily.EXPLORE,
                              realized=0.0)
        try:
            exp.record(ScientificEvaluation(f"camp.{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        except Exception as e:
            pass
        time.sleep(0.0005)

def deep(n, f):
    return f() if n == 0 else deep(n - 1, f)

def verifier(depth):
    while time.monotonic() < stop:
        for kind, rid in ((OwnerKind.BUDGET_LEDGER, lid), (OwnerKind.EXPERIMENT, eid)):
            try:
                deep(depth, lambda: reader.read(kind, rid))
                k = "served"
            except OwnerUnavailable as exc:
                s = str(exc)
                k = "FOR GOOD" if "from then on" in s else ("behind" if "behind" in s else s[:70])
            except RecursionError:
                k = "caller recursion"
            with lock:
                outcomes[(kind.value, k)] += 1

ts = [threading.Thread(target=mover)] + [threading.Thread(target=verifier, args=(d,)) for d in (0, 0, 2850)]
for t in ts: t.start()
for t in ts: t.join()
for k, v in sorted(outcomes.items()): print(v, k)
print("diverged:", reader._diverged)
print("sealed:", reader._sealed, "| ledger charges", len(o.ledgers[lid].charges), "| evaluations", len(exp._evaluations))
