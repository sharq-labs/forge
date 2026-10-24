"""The finally at owners.py:476-479 is what keeps one failed accounts() from refusing every later verification for good
(its ticket would otherwise stay in flight).  At c69e579 this holds; mutant m2 (finally without the discard) passes the
whole BR1.1 suite, so the guarantee has no regression control."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
lid = next(iter(o.ledgers))
state = {"fail": False}
def accounts():
    if state["fail"]:
        raise RuntimeError("ledger store offline")
    return o.ledgers, o.experiments
reader = BudgetReader.following(accounts)
state["fail"] = True
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid)
except OwnerUnavailable as exc:
    print("while the store is offline:", str(exc)[:70])
state["fail"] = False
for i in range(2):
    try:
        print(f"read {i} after the store is back:", reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)
    except OwnerUnavailable as exc:
        print(f"read {i} after the store is back: OwnerUnavailable: {str(exc)[:80]}")
