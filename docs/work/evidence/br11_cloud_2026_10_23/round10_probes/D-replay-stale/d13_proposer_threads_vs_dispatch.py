"""R10-D d13: proposer threads calling the Mind-facing gateway.admit in a loop (the public API, no introspection) while
the execution side dispatches an admitted action: how many dispatch verifications are refused 'in flight'?"""
import threading, time, collections, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, admit, ExecutionDesk, DispatchRefused, MindWorldPort

SIM = ax.base("battery")["simulate_pulse"]
for n in (0, 1, 2, 4):
    o = ax.owned("battery")
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    a = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    world = o.world
    calls = []
    gw = ExecutionDesk(a, calls.append, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(world))
    r = port.request_admission(o.propose("simulate_pulse", *SIM, world=world), gw)
    stop = threading.Event()
    props = collections.Counter()

    def proposer():
        p = MindWorldPort(FeasibleActionSpace.build(world))
        while not stop.is_set():
            props[p.request_admission(o.propose("simulate_pulse", *SIM, world=world), gw).status.value] += 1
    ps = [threading.Thread(target=proposer, daemon=True) for _ in range(n)]
    [p.start() for p in ps]
    time.sleep(0.2)
    ok = refused = 0
    for i in range(40):
        try:
            gw.dispatch(r.admitted); ok += 1
        except DispatchRefused:
            refused += 1
    stop.set(); [p.join(5) for p in ps]
    print(f"{n} proposer threads: execution-side dispatch {ok} ok / {refused} refused; proposer admissions {dict(props)}")
