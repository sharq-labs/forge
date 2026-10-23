"""R12-B b1204: the round-11 'moving' carve-out (owners._moving) is decided by the exception's exact type and message,
so a state whose serialization raises the interpreter's own 'dictionary changed size during iteration' EVERY time
(a value whose __str__ iterates a dict it fills: a deterministic bug, nothing moves) is refused to each verification
only, never observed; a restore re-dispatches the executed action.  Control: the same value raising a different
RuntimeError (three alike -> refused for good)."""
import copy

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class SelfFillingNote:                       # its __str__ fills the cache it iterates: the interpreter's own error
    def __init__(self, genuine=True):
        self.genuine = genuine

    def __str__(self):
        if not self.genuine:
            raise RuntimeError("note cache unavailable")
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


def run(genuine):
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
                              family=ActionFamily.EXPLORE, realized=1.0, detail=SelfFillingNote(genuine))

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
    except DispatchRefused as e:
        again = "refused"
    print(f"[{'interpreter mutation error, every time' if genuine else 'control: other RuntimeError'}] verifications "
          f"handed the spend: {seen}; after the restore: {again}; executor ran {len(calls)}")


run(True)
run(False)
