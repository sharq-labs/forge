"""BR1's own harness on BR1's 515 frozen cases, alternately on BR1's code, the round-7 review SHA and BR1.1's head,
five times each (repeats=25)."""
import json, subprocess, sys
CHECKOUTS = dict(arg.split("=", 1) for arg in sys.argv[1:])
SNIPPET = ("import json; from benchmarks.mind_gen2_world_v1 import cases as C, run_benchmark as rb; "
           "r=rb.performance(C.load()['cases'], repeats=25); s=r.get('REFERENCE_SOLVER_MS'); "
           "print(json.dumps({'WORLD_BUILD_MS': r['WORLD_BUILD_MS'], 'ACTIONSPACE_BUILD_MS': r['ACTIONSPACE_BUILD_MS'], "
           "'FEASIBILITY_P50_MS': r['FEASIBILITY_P50_MS'], 'FEASIBILITY_P95_MS': r['FEASIBILITY_P95_MS'], "
           "'SOLVER': s['median'] if isinstance(s, dict) else s}))")
runs = {k: [] for k in CHECKOUTS}
for i in range(5):
    for key, path in CHECKOUTS.items():
        out = subprocess.run([sys.executable, "-c", SNIPPET], cwd=path, capture_output=True, text=True, check=True,
                             env={"PYTHONPATH": f"{path}/src:{path}", "PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin"})
        runs[key].append(json.loads(out.stdout.strip().splitlines()[-1]))
        print(key, i, runs[key][-1], flush=True)
print(json.dumps(runs))
