"""Independent repro of R11-C-F1 at HEAD.  World and space built BEFORE any account moves (so the proposer's world is
not rebuilt over the deep state: only the gateway's own verification reads it).  Optional argv[2]=='mutant' replaces
owners.copy.deepcopy with a JSON round trip (C parser) to show the reader-side deepcopy is the cause."""
import json, sys, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace
from engcore.mind.world import owners as OW
from engcore.scientific import to_json
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

if len(sys.argv) > 2 and sys.argv[2] == "mutant":
    OW.copy = types.SimpleNamespace(deepcopy=lambda x: json.loads(json.dumps(x)))
    print("MUTANT: owners.copy.deepcopy -> json round trip")

SIM = ax.base("battery")["simulate_pulse"]
DEPTH = int(sys.argv[1])

def nested(depth):
    root = node = {}
    for _ in range(depth):
        node["parent"] = {}
        node = node["parent"]
    return root

def attempt(f):
    try:
        return f()
    except DispatchRefused as exc:
        return f"DispatchRefused({str(exc)[:60]})"
    except Exception as exc:  # noqa: BLE001
        return f"RAISED {type(exc).__name__}"

# (A) an unbound side account goes deep; the world never reads it
o = ax.owned("battery")
o.experiments["side.campaign"] = ax.experiment("side.campaign", 10, 1)
gw = ExecutionDesk(o.authorities(), lambda a: "ran", accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(o.world)
p = o.propose("simulate_pulse", *SIM)
r0 = gw.admit(space, p)
print("(A) before:", r0.status.value)
side = o.experiments["side.campaign"]
side.metadata["provenance"] = nested(DEPTH)
t = to_json(side); back = ScientificExperiment.from_dict(json.loads(t))
print("    owner writes/reads back the side state:", json.loads(to_json(back))["accounting"] == json.loads(t)["accounting"])
print("    admit (world never reads side) ->", attempt(lambda: gw.admit(space, p).status.value))
print("    dispatch of an earlier admission ->", attempt(lambda: (gw.dispatch(r0.admitted), "DISPATCHED")[1]))

# (B) the bound account's spend carries deep provenance; Mind admits on spent state; restore; re-dispatch
o = ax.owned("battery")
eid = next(iter(o.experiments))
calls = []
def executor(authorization):
    calls.append(1)
    exp = o.experiments[eid]
    exp.record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    exp.metadata["provenance"] = nested(DEPTH)
auth = o.authorities()
reader = next(r for r in auth.readers if type(r).__name__ == "BudgetReader") if hasattr(auth, "readers") else None
gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(o.world)
r = gw.admit(space, o.propose("simulate_pulse", *SIM))
print("(B) first admission:", r.status.value, "| bound experiment:", eid)
checkpoint = o.experiments[eid].to_dict()
gw.dispatch(r.admitted)
print("    executor ran", len(calls), "| owner to_dict of spent state ok:", bool(o.experiments[eid].to_dict()))
for i in range(2):
    print(f"    Mind admission {i+1} on spent state ->", attempt(lambda: str(gw.admit(space, o.propose('simulate_pulse', *SIM)).codes())))
if reader is not None:
    print("    reader seen len:", {k: len(v) for k, v in reader._seen.items()}, "| diverged:", list(reader._diverged))
o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)
print("    re-dispatch after restore ->", attempt(lambda: (gw.dispatch(r.admitted), "DISPATCHED AGAIN")[1]), "| executor ran", len(calls))
