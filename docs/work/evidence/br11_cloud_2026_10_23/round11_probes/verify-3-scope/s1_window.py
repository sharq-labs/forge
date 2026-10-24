"""verify-3-scope s1: characterize F11-1's trigger window and the owner's own handling of the deep state.
For each depth: does the OWNER write down / read back / checkpoint the experiment (to_json, from_dict(to_json),
from_dict(to_dict), json round trip), what Python-recursive operations fail, and what the reader does (seq order)."""
import copy, json, sys
sys.argv = [sys.argv[0]]
F = "/tmp/claude-0/-home-user-forge/e352a8b8-4d77-5787-bd23-1bcc1dda83b7/scratchpad/review_r11/F-round10-rewrites-deep/f1102_readback_escape_redispatch.py"
src = open(F).read().split("for order in")[0]
ns = {"__file__": F, "__name__": "f1102"}
exec(compile(src, F, "exec"), ns)
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.scientific.serialization import to_json
from engcore.scientific.experiments.experiment import ScientificExperiment

def owner_ops(depth):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    exp = o.experiments[eid]
    exp.metadata["trace"] = ns["deep"](depth)
    res = {}
    for name, fn in [("to_json", lambda: to_json(exp)),
                     ("from_dict(to_json)", lambda: ScientificExperiment.from_dict(json.loads(to_json(exp)))),
                     ("from_dict(to_dict)", lambda: ScientificExperiment.from_dict(exp.to_dict())),
                     ("copy.deepcopy(exp)", lambda: copy.deepcopy(exp)),
                     ("deepcopy(json.loads(to_json))", lambda: copy.deepcopy(json.loads(to_json(exp)))),
                     ("repr(to_dict)", lambda: repr(exp.to_dict()))]:
        try:
            fn(); res[name] = "ok"
        except RecursionError:
            res[name] = "RecursionError"
        except Exception as exc:  # noqa: BLE001
            res[name] = type(exc).__name__
    return res

print("recursionlimit", sys.getrecursionlimit(), sys.version.split()[0])
for depth in (3, 450, 490, 500, 600, 2000, 9000, 20000):
    print(depth, owner_ops(depth))
    try:
        print("    reader seq:", ns["run"]("seq", depth))
    except Exception as exc:  # noqa: BLE001
        print("    reader seq: probe raised", type(exc).__name__, str(exc)[:100])
