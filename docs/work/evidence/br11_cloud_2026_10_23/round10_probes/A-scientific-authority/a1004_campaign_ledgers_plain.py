"""Lens A r10: do the ledgers sria.campaign's runner settles, and every benchmark fixture's accounts, pass the plain-data
rule (owners._plain) and read back through a following BudgetReader at c69e579?"""
import tests.test_sria_m5_campaign as M
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners as ow

results = []
for name in ("test_S2_realized_cost_changes_the_next_decision", "test_S6_resume_after_execution_duplicates_nothing",
             "test_S1_belief_change_changes_the_next_decision"):
    captured = []
    orig = M.CampaignRunner.__init__

    def init(self, *a, **kw):
        orig(self, *a, **kw)
        captured.append(self)

    M.CampaignRunner.__init__ = init
    try:
        getattr(M, name)()
    finally:
        M.CampaignRunner.__init__ = orig
    for runner in captured:
        led = runner.budget
        reader = BudgetReader.following(lambda led=led: ({"campaign": led}, {}))
        rec = reader.read(OwnerKind.BUDGET_LEDGER, "campaign")
        results.append((name, len(led.charges), ow._plain(led.to_dict()), rec.revision))
for r in results:
    print("campaign", r)
for wname, mk in ax.WORLDS.items():
    o = mk()
    bad = [k for k, v in o.ledgers.items() if not ow._plain(v.to_dict())] + \
          [k for k, v in o.experiments.items() if not ow._plain(v.to_dict())]
    r = BudgetReader.following(lambda o=o: (o.ledgers, o.experiments))
    n = sum(1 for k in o.ledgers if r.read(OwnerKind.BUDGET_LEDGER, k)) + \
        sum(1 for k in o.experiments if r.read(OwnerKind.EXPERIMENT, k))
    print("fixture", wname, "non-plain:", bad, "read:", n, "of", len(o.ledgers) + len(o.experiments))
