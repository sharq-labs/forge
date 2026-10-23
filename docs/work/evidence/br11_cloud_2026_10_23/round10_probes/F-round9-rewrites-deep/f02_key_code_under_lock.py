"""F10 f02: round 9 says no execution-side code ever runs under the follower's lock (owners.py docstring, README section
4).  The comparison step hashes every account key under the lock (self._seen.get(key), key in self._diverged, the cache
pruning 'k in read').  Account ids are not required to be str, so an account id object the execution side hands over
runs its __hash__ under the lock.  Part A: that code waits on an execution-side lock E held by a thread that is
starting a verification (blocked in _ticket() on the follower's lock): a lock-order deadlock (bounded here by a 3 s
timeout).  Part B: the same with plain str ids never runs code under the lock (control)."""
import threading
import time

import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader
from engcore.mind.world.authority import OwnerUnavailable

print("engcore from", engcore.__file__)
o = ax.owned("battery")
E = threading.Lock()                                   # an execution-side lock
go, x_has_e, x_done = threading.Event(), threading.Event(), threading.Event()
state = {"reader": None, "armed": False, "acquired": None, "fired": False}


class AccountId:
    def __init__(self, s):
        self.s = s

    def __hash__(self):
        r = state["reader"]
        if state["armed"] and not state["fired"] and r is not None and r._lock.locked() \
                and threading.current_thread().name == "V":      # (the probe's detector only)
            state["fired"] = True
            go.set()
            x_has_e.wait(5)
            t0 = time.monotonic()
            state["acquired"] = E.acquire(timeout=3)              # the execution side's own lock
            state["waited"] = round(time.monotonic() - t0, 2)
            if state["acquired"]:
                E.release()
        return hash(self.s)

    def __eq__(self, other):
        return isinstance(other, AccountId) and other.s == self.s


key = AccountId("extra.ledger")
extra = next(iter(o.ledgers.values()))
from engcore.sria.campaign.budget import BudgetLedger
extra = BudgetLedger.from_dict(extra.to_dict())
reader = BudgetReader.following(lambda: ({**o.ledgers, key: extra}, dict(o.experiments)))
state["reader"] = reader
print("following reader built with a non-str account id: accepted")
out = {}


def x():
    go.wait(10)
    with E:
        x_has_e.set()
        t0 = time.monotonic()
        try:
            reader.pinned()
            out["X"] = f"pinned after {round(time.monotonic() - t0, 2)} s (blocked in _ticket while V held the lock)"
        except OwnerUnavailable as exc:
            out["X"] = f"refused after {round(time.monotonic() - t0, 2)} s: {str(exc)[:80]}"
    x_done.set()


def v():
    state["armed"] = True
    try:
        reader.pinned()
        out["V"] = "pinned"
    except OwnerUnavailable as exc:
        out["V"] = f"refused: {str(exc)[:80]}"


tx = threading.Thread(target=x, name="X", daemon=True)
tv = threading.Thread(target=v, name="V", daemon=True)
tx.start(); tv.start()
tv.join(20); tx.join(20)
print("V's comparison ran the account id's __hash__ under the follower's lock:", state["fired"])
print("  E.acquire inside it (timeout 3 s) acquired:", state["acquired"], "after", state.get("waited"), "s",
      "-> without a timeout this is a deadlock" if state["acquired"] is False else "")
print("  V:", out.get("V"), "| X:", out.get("X"))
