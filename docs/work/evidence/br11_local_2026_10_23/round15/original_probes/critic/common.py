import threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.port import MindWorldPort
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
SIM = ax.base("battery")["simulate_pulse"]


def desk(o, accounts, executor):
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, authorities, ExecutionDesk(authorities, executor, accept_synthetic=True).gateway(), r


def readmit_via_port(o, authorities, gateway):
    """As a Mind would: a fresh world from the owners, a MindWorldPort, request_admission, execute."""
    try:
        world = project_world(o.declaration, authorities)
    except OwnerUnavailable as exc:
        return "projection refused: " + str(exc)[:150]
    port = MindWorldPort(FeasibleActionSpace.build(world))
    res = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gateway)
    if res.admitted is None:
        return "admission refused: " + ",".join(res.codes())
    try:
        port.execute(res.admitted, gateway)
        return "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        return "dispatch refused: " + str(exc)[:150]
