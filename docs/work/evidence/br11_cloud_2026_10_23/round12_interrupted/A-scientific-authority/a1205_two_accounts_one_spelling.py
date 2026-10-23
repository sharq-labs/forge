"""Lens A r12: README §4 'What one accounts() call hands over is read entry by entry, so one malformed entry never hides
another account'; owners.py _handed: 'store[key[1]] = account' after key = str.__str__(raw_id).

An execution side hands its live (spent) solver ledger under its id AND a pre-spend copy under a str-subclass key that
spells the same id but hashes differently (so the dict holds both entries).  _handed reads both as the same plain id
and the later entry silently replaces the earlier: no refusal, no 'two accounts under one id' statement (the converse
of the 'one object under two ids' refusal).  The live spend is never compared; the stale copy is read and the executed
action is dispatched again with NO restore of the live ledger."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Twin(str):                     # spells the id; hashes and compares unlike it, so a dict keeps both entries
    def __hash__(self):
        return hash(("twin", str.__str__(self)))

    def __eq__(self, other):
        return type(other) is Twin and str.__eq__(self, other)


for order in ("twin_last", "twin_first"):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    state = {"twin": False}

    def accounts():
        ledgers = dict(o.ledgers)
        if state["twin"]:
            live = ledgers.pop(lid)
            ledgers = ({**ledgers, lid: live, Twin(lid): before} if order == "twin_last"
                       else {Twin(lid): before, **ledgers, lid: live})
        return ledgers, dict(o.experiments)

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    world = o.world
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run-{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                              family=ActionFamily.EXPLORE, realized=2.0)
        state["twin"] = True         # from now on the execution side also hands the pre-spend copy under a twin key

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    try:
        gateway.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        again = f"refused ({str(exc)[:110]})"
    print(f"{order}: live ledger revision {o.ledgers[lid].revision}; second dispatch: {again}; executor calls "
          f"{len(calls)}; reader observed revision {len(reader._seen.get(('ledger', lid), ()))}")
