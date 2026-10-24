"""R11-F f1102: round 10 left part of the experiment read-back OUTSIDE the try that classifies a read-back failure
(owners.py:409 `back = copy.deepcopy(back)`, and owners.py:405 `_sha_json(rebuilt)` / `_history(...)`).  At c69e579
the whole read-back was inside one try (OwnerUnavailable for that verification).  An experiment the owner writes down
(to_json) and reads back (from_dict) but whose JSON nesting is deeper than the reader's own Python deepcopy can copy
raises RecursionError out of _account -> _read_back -> _observe_all, BEFORE the comparison: the state handed over is
never compared, never recorded, and never refused for good.  The verification raises (fail-safe for itself), and the
ticket leaves through pinned()'s finally, so a verification WAITING for it (round 10's bounded wait) proceeds and
decides as if the handed state did not exist.

Through ExecutionDesk.gateway(), two orders:
  seq : dispatch #1 executes; the executor records an observation and a deep run trace (metadata); a Mind admission is
        verified on that state (raises); the execution side restores the pre-run checkpoint; re-dispatch.
  wait: dispatch #1 executes and spends; D (re-dispatch, handed the restore) compares while P (handed the spend) is in
        flight; D waits for P (bounded wait); P's read-back raises; D decides.
Control: the same with a shallow trace (depth 3)."""
import sys
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def deep(n):
    x = {"leaf": 1}
    for i in range(n):
        x = {f"k{i}": x}
    return x


def outcome(fn):
    try:
        fn()
        return "DISPATCHED"
    except DispatchRefused as exc:
        return f"refused ({str(exc)[:70]})"
    except Exception as exc:  # noqa: BLE001
        return f"RAISED {type(exc).__name__}"


def run(order, depth):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    saved = o.experiments[eid].to_dict()                         # the execution side's pre-run checkpoint
    gate = {"p_handed": threading.Event(), "p_go": threading.Event()}

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "P":
            gate["p_handed"].set()
            gate["p_go"].wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    calls = []

    def executor(authorization):
        calls.append(1)
        exp = o.experiments[eid]                                 # the run records its observation and its trace
        exp.record(ScientificEvaluation(f"run-{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                        detail="the executed pulse"))
        exp.metadata["trace"] = deep(depth)

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    # the execution side's own owner reads the spent state back (it is an ordinary, readable record)
    owner_ok = ScientificExperiment.from_dict(__import__("json").loads(
        __import__("engcore.scientific", fromlist=["to_json"]).to_json(o.experiments[eid]))).attempts
    if order == "seq":
        a = outcome(lambda: admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities))
        o.experiments[eid] = ScientificExperiment.from_dict(saved)     # restore the pre-run checkpoint
        d = outcome(lambda: gateway.dispatch(r.admitted))
        return f"owner reads spent state back: {owner_ok} attempts | a verification on the spend: {a} | " \
               f"re-dispatch after the restore: {d} | executor ran {len(calls)}"
    out = {}
    p = threading.Thread(target=lambda: out.setdefault("P", outcome(lambda: reader.pinned())), name="P", daemon=True)
    p.start()
    assert gate["p_handed"].wait(10)                             # P holds the spent state, in flight
    o.experiments[eid] = ScientificExperiment.from_dict(saved)   # restore
    waiting = {}

    def d_run():
        waiting["D"] = outcome(lambda: gateway.dispatch(r.admitted))

    dt = threading.Thread(target=d_run, name="D", daemon=True)
    dt.start()
    import time
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 5:                          # wait until D is waiting in its comparison
        f = sys._current_frames().get(dt.ident)
        names = []
        while f is not None:
            names.append(f.f_code.co_name)
            f = f.f_back
        if "_observe_all" in names and "wait" in names:
            break
        time.sleep(0.002)
    d_waiting = "_observe_all" in names and "wait" in names
    gate["p_go"].set()                                           # P now reads back the spent state
    dt.join(10)
    p.join(10)
    return f"D was waiting for P: {d_waiting} | P (handed the spend): {out.get('P')} | D (re-dispatch, handed the " \
           f"restore): {waiting.get('D')} | executor ran {len(calls)}"


for order in ("seq", "wait"):
    for depth in (3, int(sys.argv[1]) if len(sys.argv) > 1 else 600):
        print(f"[{order}] trace depth {depth}: {run(order, depth)}")
