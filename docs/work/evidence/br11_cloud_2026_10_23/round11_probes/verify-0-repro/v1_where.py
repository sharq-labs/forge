"""Where exactly does the RecursionError escape, and do the owner's own write/read-back steps succeed at that depth?"""
import json, sys, traceback, copy
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace
from engcore.scientific import to_json
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]

def nested(depth):
    root = node = {}
    for _ in range(depth):
        node["parent"] = {}
        node = node["parent"]
    return root

DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 500
o = ax.owned("battery")
o.experiments["side.campaign"] = ax.experiment("side.campaign", 10, 1)
gw = ExecutionDesk(o.authorities(), lambda a: "ran", accept_synthetic=True).gateway()
exp = o.experiments["side.campaign"]
exp.metadata["provenance"] = nested(DEPTH)

# The owner's own steps, at the top of the stack
t = to_json(exp); print("to_json ok, len", len(t))
w = json.loads(t); print("json.loads ok")
r = ScientificExperiment.from_dict(json.loads(t)); print("from_dict ok")
b = json.loads(to_json(r)); print("to_json(rebuilt) ok; accounting equal:", b["accounting"] == w["accounting"])
try:
    exp.to_dict(); print("exp.to_dict ok")
except RecursionError as e:
    print("exp.to_dict RecursionError")
try:
    copy.deepcopy(b); print("deepcopy at top of stack ok")
except RecursionError:
    print("deepcopy at top of stack RecursionError")

try:
    res = gw.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
    print("admit ->", res.status.value, res.codes())
except RecursionError as exc:
    tb = traceback.extract_tb(exc.__traceback__)
    # print the frames outside copy.py, plus the first copy.py frame
    print("admit RAISED RecursionError; frames (non-copy):")
    first_copy = None
    for fr in tb:
        if fr.filename.endswith("copy.py"):
            if first_copy is None:
                first_copy = fr
                print("   ", fr.filename.split('/')[-1], fr.lineno, fr.name, "<- first copy.py frame")
            continue
        print("   ", "/".join(fr.filename.split('/')[-3:]), fr.lineno, fr.name, "|", fr.line)
    print("total frames", len(tb))
