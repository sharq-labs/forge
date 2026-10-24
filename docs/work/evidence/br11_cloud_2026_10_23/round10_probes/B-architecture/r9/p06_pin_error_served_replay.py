"""_Memo._pin_now (round 8): an eager pin's exception is kept and raised at the first read of that owner.  Check that
served() and replay agree for (a) a budget follower whose accounts() fails, world READS budget; (b) the same, world
reads NO budget (gen1 pool world projected under an unbounded budget? -> use a world with budget and one without)."""
import json
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import AdmissionRecord, Authorities, BudgetReader, FeasibleActionSpace, admit, replay_admission

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
state = {"fail": False}
def accounts():
    if state["fail"]:
        raise RuntimeError("ledger store offline")
    return o.ledgers, o.experiments
reader = BudgetReader.following(accounts)
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
state["fail"] = True
r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), auth)
print("(a) admission with the budget pin failing:", r.status.value, sorted(r.codes()))
rec = AdmissionRecord.of(r, auth).to_dict()
print("    snapshot unavailable:", [u[0] for u in rec["snapshot"]["unavailable"]], "| records:",
      sorted({x["owner_kind"] for x in rec["snapshot"]["records"]}))
print("    replay:", replay_admission(json.loads(json.dumps(rec))).outcome.value)
