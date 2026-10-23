"""The code comment at owners.py (round 8) says the per-account cache 'never outgrows the accounts' current state'.
An execution side that hands over a different experiment id at each verification (one account per campaign, the old
one dropped) leaves every dropped account's whole read-back form and history in the cache (and its history in _seen)
for the reader's life.  Private members are read only to measure."""
import tracemalloc
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind

state = {"i": 0}
def accounts():
    i = state["i"]
    return {}, {f"camp{i}": ax.experiment(f"camp{i}", 400, 200)}

reader = BudgetReader.following(accounts)
tracemalloc.start()
for i in range(1, 41):
    state["i"] = i
    reader.pinned()
cur, peak = tracemalloc.get_traced_memory()
print("accounts handed over now:", len(accounts()[1]), "| cache entries:", len(reader._readback),
      "| _seen entries:", len(reader._seen), f"| traced memory {cur/1e6:.1f} MB")
