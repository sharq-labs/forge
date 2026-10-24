"""The round-8 re-entrancy guard is thread-local.  An accounts() that reads through the reader it feeds on ANOTHER thread
(e.g. it asks a worker that consults the desk's reader) is not refused at once: the worker's pin calls accounts()
again, which asks a worker again ... With a bounded worker pool this blocks until the pool is exhausted (here: a
timeout of 2 s per hop keeps the probe finite).  README §4: 'an accounts() that reads through the reader it feeds is
refused at once (OWNER_UNAVAILABLE), never recursed'."""
import concurrent.futures as cf, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
eid = next(iter(o.experiments))
pool = cf.ThreadPoolExecutor(max_workers=4)
hops = []
state = {"reader": None}

def accounts():
    r = state["reader"]
    if r is not None:
        hops.append(threading.current_thread().name)
        fut = pool.submit(r.read, OwnerKind.EXPERIMENT, eid)
        try:
            fut.result(timeout=2)
        except Exception as exc:
            hops.append(type(exc).__name__)
    return o.ledgers, o.experiments

state["reader"] = BudgetReader.following(accounts)
t0 = time.time()
try:
    state["reader"].read(OwnerKind.EXPERIMENT, eid)
    out = "read returned"
except OwnerUnavailable as exc:
    out = "OwnerUnavailable: " + str(exc)[:80]
print(out, f"after {time.time()-t0:.1f}s; nested pins on threads:", [h for h in hops if h.startswith('Thread')][:8],
      "| outcomes:", [h for h in hops if not h.startswith('Thread')][:8])
pool.shutdown(wait=False, cancel_futures=True)
