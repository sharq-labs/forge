"""Lens A r11: _written classifies EVERY RuntimeError other than RecursionError as 'the account moved while it was
serialized' (refused for that verification only).  NotImplementedError is a RuntimeError.  A spend recorded in a state
whose serialization raises one deterministically (here: a charge detail whose __str__ raises NotImplementedError, run by
canonical_digest's default=str) is never observed, so it is not refused for good like every other unwritable state,
and an object-replacing restore re-authorizes the executed action.  Compare: the same spend with a detail whose
__str__ raises TypeError (refused for good)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Lazy:
    def __init__(self, exc):
        self.exc = exc

    def __str__(self):
        raise self.exc("not rendered")


for exc in (NotImplementedError, TypeError):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    world = o.world
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run-{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                              family=ActionFamily.EXPLORE, realized=2.0, detail=Lazy(exc))

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        seen = "read"
    except Exception as exc_:
        seen = f"{type(exc_).__name__}: {str(exc_)[:120]}"
    o.ledgers[lid] = before                                    # the execution side restores (object replaced)
    try:
        gateway.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as exc_:
        again = f"refused ({str(exc_)[:90]})"
    print(f"detail __str__ raises {exc.__name__}: after the spend: {seen}")
    print(f"   after the restore: {again}; executor calls {len(calls)}")
