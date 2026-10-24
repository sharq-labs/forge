"""verify-1-scope for R11-C-F1: where does the RecursionError come from, what is the depth window, does the owner
itself handle the content, does the re-dispatch need the crashed intermediate verifications, and can a proposer reach
the trigger through the shipped intake?"""
import json, sys, traceback

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import DispatchRefused, ExecutionDesk, FeasibleActionSpace
from engcore.scientific import to_json
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]


def nested(depth):
    root = node = {}
    for _ in range(depth):
        node["parent"] = {}
        node = node["parent"]
    return root


def admit_unbound(depth, extra_frames=0):
    o = ax.owned("battery")
    o.experiments["side.campaign"] = ax.experiment("side.campaign", 10, 1)
    gw = ExecutionDesk(o.authorities(), lambda a: "ran", accept_synthetic=True).gateway()
    o.experiments["side.campaign"].metadata["provenance"] = nested(depth)

    def call(n):
        if n:
            return call(n - 1)
        return gw.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
    try:
        return call(extra_frames).status.value, None
    except Exception as exc:  # noqa: BLE001
        tb = traceback.extract_tb(exc.__traceback__)
        ours = [f"{f.filename.split('/src/')[-1]}:{f.lineno}" for f in tb if "owners.py" in f.filename]
        return f"RAISED {type(exc).__name__}", ours[-1:] + [f"{tb[-1].filename.split('/')[-1]}:{tb[-1].lineno}"]


print("python", sys.version.split()[0], "recursion limit", sys.getrecursionlimit())
print("(a) where it raises, and the threshold (baseline stack)")
lo = None
for d in range(400, 520, 10):
    out, where = admit_unbound(d)
    if out.startswith("RAISED") and lo is None:
        lo = d
        print(f"  depth {d}: {out} at {where}")
    elif d % 50 == 0:
        print(f"  depth {d}: {out}")
print(f"  first raising depth (step 10): {lo}")
print("(a2) with the caller 300 frames deeper")
for d in (150, 200, 250, 300):
    print(f"  depth {d}: {admit_unbound(d, 300)[0]}")
print("(b) the owner itself at depth 600 / 5000 / 20000: to_json, from_dict, to_json of rebuilt")
for d in (600, 5000, 20000):
    e = ax.experiment("x", 10, 1)
    e.metadata["p"] = nested(d)
    try:
        t = to_json(e)
        r = ScientificExperiment.from_dict(json.loads(t))
        ok = to_json(r) == t
        print(f"  depth {d}: owner writes and reads back: {ok}")
    except Exception as exc:  # noqa: BLE001
        print(f"  depth {d}: owner FAILS {type(exc).__name__}")
print("(b2) unbound side experiment at depth 20000 (beyond the owner's own encoder): admission ->",
      admit_unbound(20000)[0])


def redispatch(depth, mind_requests):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    calls = []

    def executor(authorization):
        calls.append(1)
        exp = o.experiments[eid]
        exp.record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        exp.metadata["provenance"] = nested(depth)

    gateway = ExecutionDesk(o.authorities(), executor, accept_synthetic=True).gateway()
    space = FeasibleActionSpace.build(o.world)
    r = gateway.admit(space, o.propose("simulate_pulse", *SIM))
    checkpoint = o.experiments[eid].to_dict()
    gateway.dispatch(r.admitted)
    seen = []
    for _ in range(mind_requests):
        try:
            a = gateway.admit(space, o.propose("simulate_pulse", *SIM))
            seen.append(f"{a.status.value}")
        except Exception as exc:  # noqa: BLE001
            seen.append(f"RAISED {type(exc).__name__}")
    o.experiments[eid] = ScientificExperiment.from_dict(checkpoint)
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:60]})"
    except Exception as exc:  # noqa: BLE001
        d = f"RAISED {type(exc).__name__}"
    print(f"  depth {depth}, {mind_requests} Mind requests on the spent state {seen}: re-dispatch after restore: {d}; "
          f"executor ran {len(calls)}")


print("(c) re-dispatch: with and without intermediate Mind requests")
for depth in (3, 600, 20000):
    for n in (0, 1):
        redispatch(depth, n)
