"""Does the general class (a bound spend its owner cannot read back is not recorded; a restore then re-dispatches)
exist without round 9's plain rule?  Run at ceaf8cd and at c69e579 with metadata the core cannot serialize."""
import json, datetime, decimal
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific import to_json
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]

def run(label, meta):
    o = ax.owned("battery"); eid = next(iter(o.experiments)); auth = o.authorities()
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), auth)
    calls = []
    def executor(a):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"v02.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))
    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    ck = json.loads(to_json(o.experiments[eid]))
    gw.dispatch(r.admitted)
    try:
        to_json(o.experiments[eid]); ser = "to_json ok"
    except Exception as e:
        ser = f"to_json raises {type(e).__name__}"
    second = admit(space, o.propose("simulate_pulse", *SIM), auth)
    o.experiments[eid] = ScientificExperiment.from_dict(ck)
    try:
        gw.dispatch(r.admitted); again = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        s = str(exc); again = "refused " + s[s.find("("):][:60]
    print(f"{label:16s} {ser:28s} | on spend: {second.codes()} | after restore: {again} | ran {len(calls)}")

for label, meta in [("set", {"s": {1, 2}}), ("datetime", {"t": datetime.datetime(2026, 1, 1)}),
                    ("decimal", {"d": decimal.Decimal("1.5")}), ("bytes", {"b": b"x"}), ("int key", {"k": {1: "a"}})]:
    try:
        run(label, meta)
    except Exception as e:
        print(label, "error", type(e).__name__, str(e)[:100])
