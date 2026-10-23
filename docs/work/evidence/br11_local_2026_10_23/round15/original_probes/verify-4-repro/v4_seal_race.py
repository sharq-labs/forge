"""Skeptic re-implementation of F15-F1.  Same interleaving, written independently, with extra checks:
(a) the reader is sealed before GOOD compares; (b) GOOD was in flight (ticket taken) before the seal;
(c) control A: no BAD seal -> GOOD (handed restored S0 after S1 was never handed) is the accepted residual case;
(d) control B: BAD handed S1 as a dict (read back) -> GOOD is refused as behind;
(e) mode 'seq': BAD seals with GOOD not in flight -> GOOD refused (the seal works sequentially)."""
import threading, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]

def run(mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    inside, go = threading.Event(), threading.Event()
    log = []
    def accounts():
        name = threading.current_thread().name
        if name == "GOOD" and mode != "seq":
            inside.set(); assert go.wait(10)
        ledgers = dict(o.ledgers)
        if name == "BAD":
            log.append(("BAD handed charges", len(o.ledgers[lid].charges)))
            if mode in ("race", "seq"):
                return types.MappingProxyType(ledgers), dict(o.experiments)
            return ledgers, dict(o.experiments)
        if name == "GOOD":
            log.append(("GOOD handed charges", len(o.ledgers[lid].charges), "sealed", reader._sealed is not None))
        return ledgers, dict(o.experiments)
    calls = []
    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail="plain")
    reader = BudgetReader.following(accounts)
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    assert r.admitted is not None
    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gw.dispatch(r.admitted)
    assert len(calls) == 1
    out = {}
    def good():
        try:
            gw.dispatch(r.admitted); out["good"] = "DISPATCHED AGAIN"
        except Exception as exc:
            out["good"] = f"refused {type(exc).__name__}: {str(exc)[:140]}"
    def bad():
        try:
            reader.pinned(); out["bad"] = "pinned"
        except OwnerUnavailable as exc:
            out["bad"] = "refused: " + str(exc)[:90]
    if mode == "seq":
        tb = threading.Thread(target=bad, name="BAD"); tb.start(); tb.join(10)
        o.ledgers[lid] = s0
        tg = threading.Thread(target=good, name="GOOD"); tg.start(); tg.join(10)
    else:
        tg = threading.Thread(target=good, name="GOOD", daemon=True); tg.start()
        assert inside.wait(10)
        inflight_before = sorted(reader._in_flight)
        tb = threading.Thread(target=bad, name="BAD"); tb.start(); tb.join(10)
        if mode == "race":
            print(f"[{mode}] in flight when BAD started: {inflight_before}; after BAD: {sorted(reader._in_flight)}")
        o.ledgers[lid] = s0
        go.set(); tg.join(10)
    print(f"[{mode}] BAD: {out.get('bad')}")
    print(f"[{mode}] sealed: {reader._sealed is not None}")
    print(f"[{mode}] log: {log}")
    print(f"[{mode}] GOOD: {out.get('good')}")
    print(f"[{mode}] executor calls = {len(calls)}")

for mode in ("race", "race", "race", "seq", "dict"):
    run(mode)
    print()
