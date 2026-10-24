"""The thread-local guard covers only accounts().  Execution-side code that runs inside the LOCKED read-back (an
experiment metadata value's __deepcopy__, called by the follower's copy.deepcopy of the cached read-back form) and
reads through the same follower re-enters pinned(): the guard is already reset, accounts() is called again, and
_observe_all blocks on the follower's own non-reentrant Lock held by this very thread.  The process hangs (run under
`timeout`); a faulthandler dump after 5 s shows where."""
import faulthandler, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind

faulthandler.dump_traceback_later(5, exit=True, file=sys.stdout)
state = {"reader": None, "depth": 0}


class Notes(dict):
    def __deepcopy__(self, memo):
        r = state["reader"]
        if r is not None and state["depth"] == 0:
            state["depth"] += 1
            print("execution-side hook reads through the follower (under its lock) ...", flush=True)
            r.read(OwnerKind.BUDGET_LEDGER, "x")
        return Notes(self)


o = ax.owned("battery")
extra = ax.experiment("campaign.notes", 10, 1)
experiments = dict(o.experiments, **{"campaign.notes": extra})
reader = BudgetReader.following(lambda: (o.ledgers, experiments))
extra.metadata["notes"] = Notes(owner="campaign")   # added after construction: the next read-back recomputes
state["reader"] = reader
reader.pinned()
print("returned (no hang)")
