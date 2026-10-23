"""R10-C c1001: the round-9 ticket rule protects a spend handed to an EARLIER-started verification.  Mirror case: the
re-dispatch T1 STARTS first (ticket 1) but its accounts() takes its mapping only after the rollback (it waits inside the
execution side's accounts(), e.g. for an execution-side lock, before reading the mapping); a later-started verification
T2 (ticket 2) is handed the spent ledger BEFORE the rollback and compares after T1.  Only the public paths are used:
BudgetReader.following(accounts) with an execution-side accounts() callable, ExecutionDesk(...).gateway().dispatch.
Mirrors tests/mind/test_authority_review_r9.py::test_a_rollback_read_while_an_earlier_verification_holds_the_spend_
never_redispatches with the two verifications' start order swapped.

Variant "replace": the executor spends by replacing the ledger object, the execution side restores by replacing it.
Variant "inplace": the executor settles in place; the restore replaces the object (sria.campaign's restore)."""
import sys
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(variant: str) -> None:
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    t1_entered, t1_go = threading.Event(), threading.Event()
    t2_handed, t2_go = threading.Event(), threading.Event()
    log = []

    def accounts():
        name = threading.current_thread().name
        if name == "T1" and not t1_go.is_set():
            t1_entered.set()
            t1_go.wait(10)                       # waits (e.g. for an execution-side lock) BEFORE taking its mapping
        mapping = (dict(o.ledgers), dict(o.experiments))
        log.append((name, mapping[0][lid].revision))
        if name == "T2" and not t2_go.is_set():
            t2_handed.set()
            t2_go.wait(10)                       # handed the mapping, not yet read back / compared
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None, r.status
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)                                          # dispatched once (observes the unspent ledger)
    if variant == "replace":
        spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
        spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                     realized=2.0)
        o.ledgers[lid] = spent                                            # the executor spends (object replaced)
    else:
        o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=2.0)                               # the executor spends in place
    out = {}

    def t1():
        try:
            gateway.dispatch(r.admitted)
            out["T1"] = "DISPATCHED AGAIN"
        except DispatchRefused as exc:
            out["T1"] = f"refused: {str(exc)[:160]}"

    def t2():
        try:
            reader.pinned()
            out["T2"] = "pinned"
        except Exception as exc:  # noqa: BLE001
            out["T2"] = f"{type(exc).__name__}: {str(exc)[:120]}"

    th1 = threading.Thread(target=t1, name="T1", daemon=True)
    th1.start()
    assert t1_entered.wait(10)                                            # T1 has its ticket (1), no mapping yet
    th2 = threading.Thread(target=t2, name="T2", daemon=True)
    th2.start()
    assert t2_handed.wait(10)                                             # T2 (ticket 2) was handed the spend
    o.ledgers[lid] = before                                               # the execution side restores (replaces)
    t1_go.set()
    th1.join(10)                                                          # T1 maps the restore, compares first
    t2_go.set()
    th2.join(10)                                                          # T2 compares the spend afterwards
    try:
        gateway.dispatch(r.admitted)
        later = "DISPATCHED"
    except DispatchRefused as exc:
        later = f"refused: {str(exc)[:100]}"
    print(f"[{variant}] accounts() calls (thread, revision handed): {log}")
    print(f"[{variant}] T1 (started first, read the restore): {out.get('T1')}")
    print(f"[{variant}] T2 (started second, was handed the spend): {out.get('T2')}")
    print(f"[{variant}] executor ran {len(calls)} times; a later re-dispatch: {later}")


for v in ("replace", "inplace"):
    run(v)
