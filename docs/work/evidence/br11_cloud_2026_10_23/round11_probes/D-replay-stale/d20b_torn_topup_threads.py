"""R11-D d20b: d20 with real threads (no tracing): one execution-side thread tops a ledger up honestly in two steps
(total, then a validation reservation below the new total) while another thread verifies through the following
reader.  Counts verifications refused for good, and whether the reader ever reads the (honest, forward-only) ledger
again.  sys.setswitchinterval is lowered to make the interleaving likely."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

sys.setswitchinterval(float(sys.argv[1]) if len(sys.argv) > 1 else 1e-5)
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
L = o.ledgers[lid]
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
stop = threading.Event()
steps = {"n": 0}


def execution_side():
    while not stop.is_set():
        t = L.total_budget + 100.0
        L.total_budget = t                          # step 1: the new total
        L.reserved_validation_budget = t - 50.0     # step 2: a reservation within the new total (always honest)
        steps["n"] += 1


th = threading.Thread(target=execution_side, daemon=True)
th.start()
counts = {"read": 0, "this verification": 0, "for good": 0}
first_for_good = None
t0 = time.time()
for i in range(3000):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        counts["read"] += 1
    except OwnerUnavailable as e:
        if "from then on" in str(e):
            counts["for good"] += 1
            first_for_good = first_for_good or (i, str(e)[:140])
        else:
            counts["this verification"] += 1
stop.set()
th.join(5)
print("top-ups:", steps["n"], "verifications:", counts, "elapsed %.1fs" % (time.time() - t0))
print("first refusal for good:", first_for_good)
print("ledger at the end (honest):", L.total_budget, L.reserved_validation_budget)
