"""verify-3-scope s2: is F11-1's outcome (a handed spend whose verification fails closed without recording it, then a
restore re-dispatches) already reachable at aad2f69 through the DOCUMENTED residuals, with execution-side content and the
public API only (no introspection)?
  A  'moved while it was serialized' (refused for that verification only): the spent experiment's metadata holds a key
     (a str subclass) whose comparison raises RuntimeError while the owner sorts its keys (README §4 names a metadata
     key's comparison as execution-side code inside the owner's serialization).  seq and wait orders, as f1102.
  B  'a state no verification was handed': spend then restore with no verification between (depth-3 control content).
  C  F11-1 itself (deep 600), for side-by-side."""
import sys, threading, time
sys.argv = [sys.argv[0]]
F = "/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r11/F-round10-rewrites-deep/f1102_readback_escape_redispatch.py"
src = open(F).read().split("for order in")[0]
ns = {"__file__": F, "__name__": "f1102"}
exec(compile(src, F, "exec"), ns)
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
SIM, outcome = ns["SIM"], ns["outcome"]


class MovingKey(str):
    def __lt__(self, other):
        raise RuntimeError("dictionary changed size during iteration")
    __gt__ = __lt__
    def __hash__(self):
        return str.__hash__(self)
    def __eq__(self, other):
        return str.__eq__(self, other)


def run(order, content):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    saved = o.experiments[eid].to_dict()
    gate = {"p_handed": threading.Event(), "p_go": threading.Event()}

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "P":
            gate["p_handed"].set(); gate["p_go"].wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        exp = o.experiments[eid]
        exp.record(ScientificEvaluation(f"run-{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        if content == "moving-key":
            exp.metadata[MovingKey("zz")] = 1
            exp.metadata[MovingKey("aa")] = 2
        elif content == "deep":
            exp.metadata["trace"] = ns["deep"](600)

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    if order == "none":
        o.experiments[eid] = ScientificExperiment.from_dict(saved)
        return f"re-dispatch after the restore: {outcome(lambda: gateway.dispatch(r.admitted))} | executor ran {len(calls)}"
    if order == "seq":
        a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities) \
            if content != "deep" else None
        a = outcome(lambda: None) if a is None else f"{a.status.value} {','.join(a.codes())[:60]}"
        if content == "deep":
            a = outcome(lambda: admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities))
        o.experiments[eid] = ScientificExperiment.from_dict(saved)
        return f"verification on the spend: {a} | re-dispatch after the restore: " \
               f"{outcome(lambda: gateway.dispatch(r.admitted))} | executor ran {len(calls)}"
    out = {}
    p = threading.Thread(target=lambda: out.setdefault("P", outcome(lambda: reader.pinned())), name="P", daemon=True)
    p.start(); assert gate["p_handed"].wait(10)
    o.experiments[eid] = ScientificExperiment.from_dict(saved)
    w = {}
    dt = threading.Thread(target=lambda: w.setdefault("D", outcome(lambda: gateway.dispatch(r.admitted))), name="D",
                          daemon=True)
    dt.start()
    t0 = time.perf_counter(); names = []
    while time.perf_counter() - t0 < 5:
        f = sys._current_frames().get(dt.ident); names = []
        while f is not None:
            names.append(f.f_code.co_name); f = f.f_back
        if "_observe_all" in names and "wait" in names:
            break
        time.sleep(0.002)
    waited = "_observe_all" in names and "wait" in names
    gate["p_go"].set(); dt.join(10); p.join(10)
    return f"D waited for P: {waited} | P (handed the spend): {out.get('P')} | D (handed the restore): {w.get('D')} | " \
           f"executor ran {len(calls)}"


for content in ("control", "moving-key", "deep"):
    for order in ("none", "seq", "wait"):
        print(f"[{content:10s}] [{order:4s}] {run(order, content)}")
