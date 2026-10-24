import json, subprocess, sys
CHECKOUTS = dict(arg.split("=", 1) for arg in sys.argv[1:])
SNIPPET = ("import json; from benchmarks.mind_gen2_world_v1 import cases as C, run_benchmark as rb; "
           "r=rb.performance(C.load()['cases'], repeats=25); "
           "print(json.dumps({'P50': r['FEASIBILITY_P50_MS'], 'P95': r['FEASIBILITY_P95_MS']}))")
for i in range(4):
    for key, path in CHECKOUTS.items():
        out = subprocess.run([sys.executable, "-c", SNIPPET], cwd=path, capture_output=True, text=True, check=True,
                             env={"PYTHONPATH": f"{path}/src:{path}", "PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin"})
        print(key, i, out.stdout.strip().splitlines()[-1], flush=True)
