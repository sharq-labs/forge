"""R11-C c1109: round 10's _written classifies by exception TYPE: any RuntimeError (not RecursionError) from the
owner's serialization is 'the account moved while it was serialized' (refused for that verification only, never
observed, never refused for good).  A spend recorded with a value whose text form raises a RuntimeError subclass
deterministically (here NotImplementedError from __str__, which the ledger's digest rule calls through default=str)
is therefore never observed by ANY verification, and a restore re-authorizes the executed action (sequential, no
concurrency).  The same value raising TypeError instead is refused for good (control).  Execution-side content (a
non-str detail), so theoretical; it shows the classification is not 'a property of the state handed over'."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Note:
    def __init__(self, exc):
        self.exc = exc

    def __str__(self):
        raise self.exc("this note has no text form")


def run(label, exc):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run-{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=1.0, detail=Note(exc))

    gateway = ExecutionDesk(o.authorities(), executor, accept_synthetic=True).gateway()
    space = FeasibleActionSpace.build(o.world)
    r = gateway.admit(space, o.propose("simulate_pulse", *SIM))
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    seen = []
    for _ in range(3):                                                    # three Mind admissions on the spent state
        a = gateway.admit(space, o.propose("simulate_pulse", *SIM))
        seen.append([c.detail.get("why", "")[-60:] for c in a.verification.checks if c.status.name != "VERIFIED"][:1])
    o.ledgers[lid] = before                                               # restore
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc_:
        d = "refused"
    print(f"{label:22s} | admissions on the spend: {seen[0]} | after restore: {d} | executor ran {len(calls)}")


run("TypeError (control)", TypeError)
run("NotImplementedError", NotImplementedError)
