"""F10 f10: README section 4 / the BudgetReader docstring say a pinned snapshot serves DETACHED copies.  Round 9 detaches
experiments through a JSON round trip but reads a ledger back with BudgetLedger.from_dict(raw) on the live to_dict()
(plain data only), which passes nested plain values (a charge's detail, predicted, enforced_cap) through by reference.
Does a pinned snapshot's ledger record alias the live account?"""
import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.owners import rederive
from engcore.sria.decision import ActionFamily

print("engcore from", engcore.__file__)
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
note = {"runs": ["r1"]}
o.ledgers[lid].settle(charge_id="c1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=0.5,
                      detail=note)                                   # a plain-data detail (the field is typed str)
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
snap = reader.pinned()
rec = snap.read(OwnerKind.BUDGET_LEDGER, lid)
print("pinned record detail:", rec.payload["ledger"]["charges"][-1]["detail"])
note["runs"].append("EDITED-AFTER-THE-PIN")                         # the execution side edits the live object
rec2 = snap.read(OwnerKind.BUDGET_LEDGER, lid)
print("same pinned snapshot, read again:", rec2.payload["ledger"]["charges"][-1]["detail"])
_, digest = rederive(OwnerKind.BUDGET_LEDGER, rec2.owner_id, rec2.record_id, rec2.payload)
print("pinned record still re-derives its digest:", digest == rec2.record_digest)
