"""Lens A r12: README §4 'a served experiment record is parsed from the owner's text at every read'.  Within one pinned
snapshot (one verification) the record is parsed once, at the pin, and every read of the snapshot returns that same
object: an edit made to it is seen by the next read of the same verification (not by a later verification)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind

o = ax.owned("battery")
eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
snap = reader.pinned()
a = snap.read(OwnerKind.EXPERIMENT, eid)
a.payload["accounting"]["remaining_observations"] = 10 ** 6
b = snap.read(OwnerKind.EXPERIMENT, eid)
print("same object within one verification:", a is b, "| edit seen by the next read of that verification:",
      b.payload["accounting"]["remaining_observations"])
c = reader.pinned().read(OwnerKind.EXPERIMENT, eid)
print("next verification:", c.payload["accounting"]["remaining_observations"])
