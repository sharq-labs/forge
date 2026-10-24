"""a1205 companion: the strict constructor (BudgetReader(...) and following()'s first baseline) also collapses two
handed accounts whose keys spell one id into one, silently (no WorldRefused), keeping the later one."""
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.sria.campaign.budget import BudgetLedger


class Twin(str):
    def __hash__(self):
        return hash(("twin", str.__str__(self)))

    def __eq__(self, other):
        return type(other) is Twin and str.__eq__(self, other)


live = BudgetLedger(total_budget=10.0)
live.settle(charge_id="run-1", action_id="a", iteration=1, family="explore", realized=4.0)
stale = BudgetLedger(total_budget=10.0)
m = {"acct": live, Twin("acct"): stale}
print("handed entries:", len(m))
r = BudgetReader(m)
print("constructor refused: no | reads revision", r.read(OwnerKind.BUDGET_LEDGER, "acct").revision,
      "(live is revision", live.revision, ")")
f = BudgetReader.following(lambda: (m, {}))
print("following() baseline revision", f.read(OwnerKind.BUDGET_LEDGER, "acct").revision)
