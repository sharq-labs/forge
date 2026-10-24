"""Threshold vs caller stack depth: the same admission called from F extra Python frames."""
import sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import ExecutionDesk, FeasibleActionSpace
SIM = ax.base("battery")["simulate_pulse"]
def nested(depth):
    root = node = {}
    for _ in range(depth):
        node["parent"] = {}
        node = node["parent"]
    return root
def at_depth(frames, f):
    return f() if frames == 0 else at_depth(frames - 1, f)
for frames in (0, 200, 400):
    lo = None
    for depth in range(50, 600, 25):
        o = ax.owned("battery")
        o.experiments["side.campaign"] = ax.experiment("side.campaign", 10, 1)
        gw = ExecutionDesk(o.authorities(), lambda a: "ran", accept_synthetic=True).gateway()
        space = FeasibleActionSpace.build(o.world); p = o.propose("simulate_pulse", *SIM)
        o.experiments["side.campaign"].metadata["provenance"] = nested(depth)
        try:
            at_depth(frames, lambda: gw.admit(space, p))
        except RecursionError:
            lo = depth; break
    print(f"caller extra frames {frames}: first metadata depth that raises -> {lo}")
