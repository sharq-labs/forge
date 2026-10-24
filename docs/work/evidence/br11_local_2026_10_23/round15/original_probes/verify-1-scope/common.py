import threading, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
import engcore.mind.world.owners as owners_mod

SIM = ax.base("battery")["simulate_pulse"]

def solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))

def desk(o, accounts, executor):
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, authorities, ExecutionDesk(authorities, executor, accept_synthetic=True).gateway(), r

def refused(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return False
    except DispatchRefused as exc:
        return "REFUSED: " + str(exc)[:160]

def readmitted(o, authorities, gateway):
    try:
        world = project_world(o.declaration, authorities)
    except OwnerUnavailable as exc:
        return "projection refused: " + str(exc)[:120]
    result = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    if result.admitted is None:
        return "not admitted"
    x = refused(gateway, result.admitted)
    return x or "ADMITTED AND DISPATCHED"

class SelfFillingNote:
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"

def settle(ledger, charge_id, detail="observed"):
    ledger.settle(charge_id=charge_id, action_id="simulate_pulse" if charge_id.startswith("run") else "other",
                  iteration=1, family=ActionFamily.EXPLORE, realized=0.5, detail=detail)
