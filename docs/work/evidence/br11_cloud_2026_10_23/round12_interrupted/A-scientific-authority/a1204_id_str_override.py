"""Lens A r12: README §4 / owners.py _handed: 'a str subclass ... is read as the plain str it spells, and no code of the
id runs'.  An execution side hands its solver ledger under a str-subclass key that spells the solver id but whose
__str__ names another id ('decoy').  At a96baa6 the account is read under the id it spells.  Under the mutant
'key = (kind, str(raw_id))' (which passes the whole BR1.1 suite) it is read under 'decoy', and the id the world binds
is reported MISSING.  Run from the tree to test."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
ran = []


class Spelled(str):
    def __str__(self):
        ran.append("__str__")
        return "decoy"


mode = {"odd": False}


def accounts():
    ledgers = dict(o.ledgers)
    if mode["odd"]:
        ledgers[Spelled(lid)] = ledgers.pop(lid)
    return ledgers, dict(o.experiments)


reader = BudgetReader.following(accounts)
mode["odd"] = True
snap = reader.pinned()
print("read under the id it spells:", snap.read(OwnerKind.BUDGET_LEDGER, lid) is not None)
print("read under the id its __str__ names:", snap.read(OwnerKind.BUDGET_LEDGER, "decoy") is not None)
print("id code ran:", ran)
