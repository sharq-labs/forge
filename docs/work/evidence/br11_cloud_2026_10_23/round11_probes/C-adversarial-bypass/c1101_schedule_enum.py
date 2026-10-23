"""R11-C c1101: exhaustive interleavings of two (and sampled three) verifications of one following BudgetReader with
an execution-side SPEND and RESTORE, through the public reader API (BudgetReader.following(accounts), reader.pinned()).

Each verification Vi has three controlled steps: T (it starts: pinned() is called and its ticket is taken; it then
blocks inside accounts() BEFORE it takes the mapping), H (it takes the mapping = is handed the current account
objects; it then blocks inside accounts() before returning), R (accounts() returns; the reader reads back and compares,
and the verification runs until it finishes or blocks in the bounded wait).  The execution side's SPEND settles a charge
(in place, or on a copy that replaces the mapping entry) and its RESTORE replaces the mapping entry with the pre-spend
copy (sria.campaign's restore).

Safety invariant checked: a verification handed the account after the RESTORE, when another verification was handed
it between SPEND and RESTORE (and read it back, i.e. the spend object is unchanged), never decides on the account
(it must be refused).  Also counted: refusals of verifications that could decide (liveness)."""
import itertools
import random
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

BudgetReader.WAIT_S = 5.0
import os
MUTANT = os.environ.get("MUTANT") == "1"


def waiting_in_compare(th: threading.Thread) -> bool:
    f = sys._current_frames().get(th.ident)
    names = []
    while f is not None:
        names.append(f.f_code.co_name)
        f = f.f_back
    return "_observe_all" in names and "wait" in names


def settle_until(th, cond, timeout=3.0):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.002)
    return False


def run(order, n, spend_mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    eid = next(iter(o.experiments))
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    exp_checkpoint = o.experiments[eid].to_dict()
    gates = {i: {"T": threading.Event(), "H": threading.Event(), "R": threading.Event(),
                 "entered": threading.Event(), "handed": threading.Event()} for i in range(n)}
    handed_state = {}
    state = {"phase": "S0"}

    def accounts():
        name = threading.current_thread().name
        if not name.startswith("V"):
            return (dict(o.ledgers), dict(o.experiments))
        i = int(name[1:])
        g = gates[i]
        g["entered"].set()
        g["H"].wait(10)
        mapping = (dict(o.ledgers), dict(o.experiments))
        handed_state[i] = state["phase"]
        g["handed"].set()
        g["R"].wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    if MUTANT:
        reader._changed.wait_for = lambda pred, timeout=None: True      # mutant: no wait (detector control)
    out = {}

    def verify(i):
        try:
            cur = reader.pinned()
            rec = (cur.read(OwnerKind.EXPERIMENT, eid) if spend_mode == "exp"
                   else cur.read(OwnerKind.BUDGET_LEDGER, lid))
            out[i] = ("ACCEPT", rec.revision)
        except OwnerUnavailable as exc:
            out[i] = ("REFUSED", str(exc)[:60])

    threads = {i: threading.Thread(target=verify, args=(i,), name=f"V{i}", daemon=True) for i in range(n)}
    for ev in order:
        if ev == "SPEND":
            if spend_mode == "exp":
                o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                               detail="x"))
            elif spend_mode == "inplace":
                o.ledgers[lid].settle(charge_id="run-1", action_id="a", iteration=1, family=ActionFamily.EXPLORE,
                                      realized=2.0)
            else:
                spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
                spent.settle(charge_id="run-1", action_id="a", iteration=1, family=ActionFamily.EXPLORE, realized=2.0)
                o.ledgers[lid] = spent
            state["phase"] = "S1"
        elif ev == "RESTORE":
            if spend_mode == "exp":
                o.experiments[eid] = ScientificExperiment.from_dict(exp_checkpoint)
            else:
                o.ledgers[lid] = BudgetLedger.from_dict(before.to_dict())
            state["phase"] = "S0r"
        else:
            step, i = ev[0], int(ev[1:])
            if step == "T":
                threads[i].start()
                assert settle_until(threads[i], gates[i]["entered"].is_set)
            elif step == "H":
                gates[i]["H"].set()
                assert settle_until(threads[i], gates[i]["handed"].is_set)
            else:
                gates[i]["R"].set()
                settle_until(threads[i], lambda: not threads[i].is_alive() or waiting_in_compare(threads[i]))
    for i in range(n):
        threads[i].join(15)
    # what each verification's read-back saw
    pos = {e: k for k, e in enumerate(order)}
    seen = {}
    for i in range(n):
        h, r = pos[f"H{i}"], pos[f"R{i}"]
        if h > pos["RESTORE"]:
            seen[i] = "S0r"
        elif spend_mode in ("inplace", "exp"):
            seen[i] = "S1" if r > pos["SPEND"] else "S0"
        else:
            seen[i] = "S1" if h > pos["SPEND"] else "S0"
    bad = []
    spend_read = [j for j in range(n) if seen[j] == "S1"]
    for i in range(n):
        if seen[i] == "S0r" and spend_read and out[i][0] == "ACCEPT":
            bad.append(i)
    return out, seen, bad


def orders(n):
    evs = [f"{s}{i}" for i in range(n) for s in "THR"] + ["SPEND", "RESTORE"]
    seen = set()
    for perm in itertools.permutations(range(len(evs))):
        pass
    # generate linear extensions of the partial order T_i<H_i<R_i, SPEND<RESTORE
    def rec(prefix, remaining):
        if not remaining:
            yield list(prefix)
            return
        for e in sorted(remaining):
            ok = True
            if e.startswith("H") and f"T{e[1:]}" in remaining:
                ok = False
            if e.startswith("R") and f"H{e[1:]}" in remaining:
                ok = False
            if e == "RESTORE" and "SPEND" in remaining:
                ok = False
            if ok:
                prefix.append(e)
                remaining.remove(e)
                yield from rec(prefix, remaining)
                remaining.add(e)
                prefix.pop()
    yield from rec([], set(evs))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    sample = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    allorders = list(orders(n))
    if sample:
        random.seed(11)
        allorders = random.sample(allorders, sample)
    print(f"{len(allorders)} orders, {n} verifications")
    for mode in (sys.argv[3].split(",") if len(sys.argv) > 3 else ("inplace", "replace", "exp")):
        nbad = nref = nacc = 0
        bads = []
        t0 = time.perf_counter()
        for order in allorders:
            out, handed, bad = run(order, n, mode)
            if bad:
                nbad += 1
                bads.append((order, out, handed))
            for i in range(n):
                if out[i][0] == "ACCEPT":
                    nacc += 1
                else:
                    nref += 1
        print(f"[{mode}] orders with a rollback decided after a handed spend: {nbad}; accepts {nacc}, refusals {nref}"
              f" ({time.perf_counter() - t0:.1f} s)")
        for b in bads[:5]:
            print("   BAD", b)
