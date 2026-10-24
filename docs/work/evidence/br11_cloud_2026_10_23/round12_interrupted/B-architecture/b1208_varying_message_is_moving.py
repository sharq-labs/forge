"""R12-B b1208: 'alike' is decided by (exception text, written text).  A spent state whose serialization fails the
same way every time but with a message that names something fresh per attempt (here a per-call request number; a
fresh object's address or a timestamp behave alike) is classified 'moved while serialized': refused per verification,
never observed; a restore re-dispatches.  Control: the same failure with a fixed message (refused for good)."""
import copy
import itertools

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
counter = itertools.count()


class RemoteNote:                            # a note fetched from a store that is not reachable from this process
    def __init__(self, varying):
        self.varying = varying

    def __str__(self):
        n = next(counter) if self.varying else 0
        raise ConnectionError(f"note store unreachable (request {n})")


def run(varying):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), auth)
    calls = []
    before = BudgetLedger.from_dict(copy.deepcopy(o.ledgers[lid].to_dict()))

    def executor(a):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=1.0, detail=RemoteNote(varying))

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    gw.dispatch(r.admitted)
    seen = []
    for _ in range(3):
        try:
            reader.read(OwnerKind.BUDGET_LEDGER, lid)
            seen.append("read")
        except OwnerUnavailable as e:
            seen.append("FOR GOOD" if "from then on" in str(e) else "this verification only")
    o.ledgers[lid] = before
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused:
        again = "refused"
    print(f"[{'message varies per attempt' if varying else 'control: fixed message'}] verifications handed the spend: "
          f"{seen}; after the restore: {again}; executor ran {len(calls)}")


run(True)
run(False)
