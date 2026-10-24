"""R10-D d15: execution-side code still runs inside the follower's read-back: ScientificExperiment.to_dict sorts the
metadata keys (owners.py _account calls exp.to_dict() before the plain-data walk), so a str-subclass key's __lt__ runs.
Records whether the follower's lock is held while it runs (c69e579: must be False; a mutant that moves the read-back
under the lock: True), and the outcome."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

held = []
state = {"reader": None}


class Key(str):
    def __lt__(self, other):
        if state["reader"] is not None:
            held.append(state["reader"]._lock.locked())
        return str.__lt__(self, other)


o = ax.owned("battery")
eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
state["reader"] = reader
o.experiments[eid].metadata[Key("b")] = 1
o.experiments[eid].metadata[Key("a")] = 2
try:
    reader.read(OwnerKind.EXPERIMENT, eid)
    print("read")
except OwnerUnavailable as e:
    print("OWNER_UNAVAILABLE:", str(e)[-70:])
print("key code ran during the read-back:", bool(held), "| lock held while it ran:", sorted(set(held)))
