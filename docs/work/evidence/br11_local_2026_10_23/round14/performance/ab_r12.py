"""Round-12 fix A/B, interleaved: the BR1.1 tree before the fix (owners.py at d40aff44) and after it.

Usage: python ab_r12.py pre=<tree> post=<tree>.  Per round and tree, in a fresh interpreter: (1) owner verification
and admission through a following budget reader on the battery fixture, 200 timed admissions after 20 warm-ups (p50,
p95 ms); (2) the overloaded large-account desk (b1209: 8 threads x 6 admissions, an unbound 2500-evaluation experiment
extended every 0.1 s); (3) the same at 1000 evaluations.  Prints one JSON line per measurement."""
import json
import subprocess
import sys

TREES = dict(arg.split("=", 1) for arg in sys.argv[1:])
ADMIT = r"""
import json, statistics, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, admit
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
space = FeasibleActionSpace.build(o.world)
lat, ver = [], []
for i in range(220):
    t0 = time.perf_counter(); reader.pinned(); t1 = time.perf_counter()
    r = admit(space, o.propose("simulate_pulse", *SIM), auth); t2 = time.perf_counter()
    assert r.feasible
    if i >= 20:
        ver.append((t1 - t0) * 1e3); lat.append((t2 - t1) * 1e3)
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
print(json.dumps({"budget_pin_p50": q(ver, .5), "budget_pin_p95": q(ver, .95), "admission_p50": q(lat, .5),
                  "admission_p95": q(lat, .95)}))
"""
for i in range(5):
    for key, path in TREES.items():
        env = {"PYTHONPATH": f"{path}/src:{path}", "PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin"}
        out = subprocess.run([sys.executable, "-c", ADMIT], cwd=path, capture_output=True, text=True, check=True, env=env)
        print(json.dumps({"tree": key, "round": i, "kind": "admission", **json.loads(out.stdout.strip().splitlines()[-1])}),
              flush=True)
        for e in ("2500", "1000"):
            out = subprocess.run([sys.executable, sys.argv[0].replace("ab_r12.py", "b1209_p24_instrumented.py"),
                                  "8", "6", e, "0.1"], cwd=path, capture_output=True, text=True, env=env)
            print(json.dumps({"tree": key, "round": i, "kind": f"desk_E{e}", "out": out.stdout.strip()[-400:],
                              "err": out.stderr.strip()[-300:]}), flush=True)
