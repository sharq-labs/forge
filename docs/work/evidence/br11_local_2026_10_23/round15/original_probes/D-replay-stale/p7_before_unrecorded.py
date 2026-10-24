"""P7: a state LISTED just before a verification's read-back (holding the executed action's charge) that rolls back in
place during that read-back (the account's own serialization does it, then fails once) is never recorded: with no
earlier unread record, the 'before' listing is only compared, never recorded, and the rolled-back state is accepted.
Contrast: round 14's control has an earlier unread record, and the same rollback is refused.
The rollback rewrites a frozen ledger's history with object.__setattr__ (inside the execution side's trust boundary)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
base = o.authorities()
auth = type(base).of(*(reader if type(r) is BudgetReader else r for r in base.readers))
calls = []
live = o.ledgers[lid]


class RollsBackOnce:
    """The run's charge detail: when first written down by the read-back, it rolls the ledger back in place to the
    charges before the run and reports the interpreter's mutation error once."""
    def __init__(self, earlier):
        self.earlier, self.done = earlier, False

    def __str__(self):
        if not self.done:
            self.done = True
            object.__setattr__(live, "charges", self.earlier)
            raise RuntimeError("dictionary changed size during iteration")
        return "run"


def executor(authorization):
    calls.append(1)
    earlier = live.charges
    live.settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                realized=0.5, detail=RollsBackOnce(earlier))


gateway = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
print("first admission:", r.status.value)
gateway.dispatch(r.admitted)
print("executor ran", len(calls), "; charges now", len(live.charges))
try:
    gateway.dispatch(r.admitted)
    print("SAME admitted action dispatched AGAIN; executor ran", len(calls))
except DispatchRefused as exc:
    print("re-dispatch refused:", str(exc)[:120])
print("charges after:", [c.charge_id for c in live.charges], "diverged:", reader._diverged, "unread:", reader._unread_entries)
