"""R12-B b1207: _at_baseline_depth joins its fresh thread with no timeout.  An execution side that verifies while
holding a re-entrant lock its account's serialization also takes (works on the calling thread at aad2f69: the lock is
re-entrant) hangs when the verification runs on a deep stack: the three same-thread attempts hit RecursionError, the
fresh thread blocks on the lock the caller holds, and the caller waits for it with no bound.  Meanwhile its ticket
stays in flight, so every other verification that accepts an account waits WAIT_S and is refused.  Simulated as in
the r11 tests (an instance to_dict that raises RecursionError when the caller's stack is deep)."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
eid = next(iter(o.experiments))
live = o.experiments[eid]
real = live.to_dict
lock = threading.RLock()                        # the execution side's own store lock


def depth():
    n, frame = 0, sys._getframe()
    while frame is not None:
        n, frame = n + 1, frame.f_back
    return n


shallow = depth() + 40


def to_dict():
    with lock:                                   # serialization takes the store lock (re-entrant)
        if depth() > shallow:
            raise RecursionError("maximum recursion depth exceeded")
        return real()


reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
live.to_dict = to_dict
out = {}


def deep(k):
    return deep(k - 1) if k else reader.read(OwnerKind.EXPERIMENT, eid)


def verifier():
    with lock:                                   # verifies while holding its store lock
        try:
            out["v"] = "served " + deep(60).revision
        except OwnerUnavailable as e:
            out["v"] = "refused " + str(e)[:80]


t = threading.Thread(target=verifier, daemon=True)
t.start()
t.join(5)
print("deep-stack verification under the re-entrant lock, after 5 s:", "STILL BLOCKED" if t.is_alive() else out)
t0 = time.perf_counter()


def other():
    try:
        out["o"] = "served " + reader.read(OwnerKind.EXPERIMENT, eid).revision
    except OwnerUnavailable as e:
        out["o"] = "refused: " + str(e)[:90]


live.to_dict = real                              # (another verification needs no lock)
u = threading.Thread(target=other, daemon=True)
u.start()
u.join(10)
print(f"another verification meanwhile ({time.perf_counter() - t0:.2f} s):", out.get("o"))
print("tickets in flight:", sorted(reader._in_flight))
