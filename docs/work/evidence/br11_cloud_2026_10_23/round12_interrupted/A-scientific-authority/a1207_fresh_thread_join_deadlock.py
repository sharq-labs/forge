"""Lens A r12: round 11's _at_baseline_depth runs the read-back on a fresh thread and joins it with NO timeout
(owners.py thread.join()).  README §4 says an execution side that verifies while holding a lock its accounts() takes is
refused after WAIT_S 'with no deadlock'.  Here the execution side holds an RLock that its account's serialization also
takes (a dict subclass in the experiment's metadata whose items() takes it), and the account holds content too deep
for the owner's encoder (as test_a_spend_too_deep_for_the_owners_encoder_refuses_the_account_for_good).  On the
verifying thread the RLock is re-entered and every attempt hits RecursionError; the fresh thread then blocks on the
RLock the verifying thread holds while the verifying thread joins it: the verification never returns, and every
other verification of the reader is refused after WAIT_S for as long as it hangs.  (At aad2f69 the same account was
refused for good at once, on the verifying thread.)"""
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

lock = threading.RLock()


class Guarded(dict):
    def items(self):
        with lock:
            return list(super().items())


o = ax.owned("battery")
eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
deep: list = []
cur = deep
for _ in range(100000):
    nxt: list = []
    cur.append(nxt)
    cur = nxt
o.experiments[eid].metadata["telemetry"] = Guarded(trace=deep)
outcome = {}


def verify_under_lock():
    with lock:                                   # the execution side verifies while holding its own lock
        try:
            reader.read(OwnerKind.EXPERIMENT, eid)
            outcome["v"] = "read"
        except OwnerUnavailable as exc:
            outcome["v"] = "refused: " + str(exc)[:120]


t = threading.Thread(target=verify_under_lock, daemon=True)
t.start()
t.join(5)
print("verification under the execution side's lock returned within 5 s:", not t.is_alive(), outcome.get("v"))
t0 = time.perf_counter()
box = {}


def other_verification():
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, next(k for k in o.ledgers if k.endswith(".solver")))
        box["v"] = "read"
    except OwnerUnavailable as exc:
        box["v"] = "refused: " + str(exc)[:110]


u = threading.Thread(target=other_verification, daemon=True)
u.start()
u.join(10)
print(f"another verification (no lock held) returned within 10 s: {not u.is_alive()} {box.get('v')}")
print("threads named budget-read-back alive:", [x.name for x in threading.enumerate() if x.name == "budget-read-back"])
import os
os._exit(0)
