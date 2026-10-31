"""Public DEVELOPMENT software controls, never a formal/Blindfold measurement.

No root file is accepted or read. Campaign worlds come from a published fixed
fixture key, enabling exact A/B software comparison. This is intentionally NOT
independent hidden evaluation. Precompilation uses only synthetic_fit below,
which imports no world generator, result, root, escrow or discovered equation.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import multiprocessing as mp
import os
import pathlib
import time
from datetime import datetime, timezone

from . import isolated_host as ih


def synthetic_fit(card, client, *, seed=0):
    """Standalone public analytic arrays, full registered search budgets."""
    import tempfile
    import numpy as np
    from pysr import PySRRegressor
    from .arms_v3 import PYSR_SETTINGS
    from .arms_v4 import PYSR_UNITS_SETTINGS
    from pysr.julia_import import jl

    which = card["fixture_arm"]
    x = np.linspace(1.0, 3.0, 32)
    X = np.column_stack((x, 1.0 + np.sin(x) ** 2))
    units = which == "pysr_units"
    y = np.log(2.0 + X[:, 0] / X[:, 1]) if units else 2.0 + X[:, 0] / X[:, 1]
    with tempfile.TemporaryDirectory(prefix="public-pysr-fit-") as scratch:
        model = PySRRegressor(**(PYSR_UNITS_SETTINGS if units else PYSR_SETTINGS), deterministic=True,
                              parallelism="serial", random_state=seed, progress=False, verbosity=0,
                              output_directory=scratch)
        model.fit(X, y, variable_names=["x0", "x1"], **({"X_units": ["m", "m"], "y_units": "1"} if units else {}))
        equations = [(int(r["complexity"]), float(r["loss"]), str(r["sympy_format"]))
                     for _, r in model.equations_.iterrows()]
    info = {"equations": equations, "julia": str(jl.VERSION), "threads": int(jl.seval("Threads.nthreads()")),
            "gc_threads": int(jl.seval("Threads.ngcthreads()")),
            "image": str(jl.seval("unsafe_string(Base.JLOptions().image_file)")),
            "symbolic_regression": str(jl.seval("string(Base.pkgversion(SymbolicRegression))"))}
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": json.dumps(info)}


def _work(item):
    arm, index, mode, env, extra = item
    exposed = ih.exposures(extra)
    hidden = ih.hidden_paths(exposed=exposed)
    if mode == "fit":
        host = ih.IsolatedProposerHost(hidden, exposed=exposed, env=env)
        try:
            result = host.propose("benchmarks.genesis_lite.performance_v4:synthetic_fit",
                                  {"universe_id": f"public-fit-{index}", "fixture_arm": arm}, index, None)
        finally:
            host.close()
        return {"arm": arm, "index": index, "status": "PUBLIC_FIT_COMPLETED", "outside": host.outside,
                "runtime_diagnostic": json.loads(result["rationale"]), "operator_timings": [host.timing]}
    from .harness_v4 import run_one_v4
    from .pilot_v4 import ROSTER
    key = hashlib.sha256(f"FORGE public performance software control v1/{index}".encode()).digest()
    return run_one_v4(arm, ROSTER[arm][0], master_seed=key, campaign_id=f"public-perf-{index}",
                       presentation="anonymous", seed=index, hidden=hidden, exposed=exposed, env=env)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=("fit", "campaign"), default="fit")
    ap.add_argument("--arms", nargs="+", default=["pysr_units", "pysr_symbolic"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--env", nargs="*", default=[])
    ap.add_argument("--expose", nargs="*", default=[])
    args = ap.parse_args()
    if args.workers < 1 or args.repeats < 1:
        ap.error("workers and repeats must be positive")
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=False)
    from .pilot_v4 import _git, environment_manifest
    from .telemetry_v4 import ProcessSampler, usage
    start = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    host_before = host_state()
    cpu_before = usage()
    sampler = ProcessSampler(os.getpid(), interval=0.5)
    env = dict(item.split("=", 1) for item in args.env)
    manifest = {"label": "PUBLIC_DEVELOPMENT_SOFTWARE_CONTROL_NOT_BLINDFOLD", "git_head": _git("rev-parse", "HEAD"),
                "dirty": bool(_git("status", "--porcelain")), "arguments": vars(args),
                "environment": environment_manifest(ih.hidden_paths(exposed=ih.exposures(args.expose)), ih.exposures(args.expose), env),
                "parent_thread_env": {k: os.environ.get(k) for k in ih.THREAD_ENV},
                "started_utc": started_utc,
                "cpuinfo": pathlib.Path("/proc/cpuinfo").read_text(),
                "boot_id": pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    items = [(a, i, args.mode, env, args.expose) for i in range(args.repeats) for a in args.arms]
    preflight_seconds = time.perf_counter() - start
    with cf.ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as pool:
        futures = {pool.submit(_work, item): item for item in items}
        with (output / "runs.jsonl").open("w") as stream:
            for future in cf.as_completed(futures):
                try:
                    rec = future.result()
                except Exception as exc:
                    item = futures[future]
                    rec = {"arm": item[0], "index": item[1], "status": "WORKER_FAILED",
                           "reasons": [f"{type(exc).__name__}: {exc}"]}
                    if item[2] == "campaign":
                        rec.update(seed=item[1], campaign_id=f"public-perf-{item[1]}", presentation="anonymous")
                stream.write(json.dumps(rec, sort_keys=True) + "\n")
                stream.flush()
                print(json.dumps({"arm": rec["arm"], "status": rec["status"], "elapsed": time.perf_counter() - start}), flush=True)
    summary = {"elapsed_seconds": time.perf_counter() - start, "completed": len(items), "workers": args.workers,
               "preflight_seconds": preflight_seconds, "elapsed_includes_manifest_preflight": True,
               "runs_sha256": hashlib.sha256((output / "runs.jsonl").read_bytes()).hexdigest(),
               "resources": sampler.close(), "host_before": host_before, "host_after": host_state(),
               "cpu": {k: v - cpu_before[k] for k, v in usage().items()}}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


def host_state():
    mem = dict(line.split(":", 1) for line in pathlib.Path("/proc/meminfo").read_text().splitlines())
    vm = dict(line.split() for line in pathlib.Path("/proc/vmstat").read_text().splitlines())
    return {"load_average": os.getloadavg(), "mem_available_kib": int(mem["MemAvailable"].split()[0]),
            "swap_free_kib": int(mem["SwapFree"].split()[0]),
            "oom_kill": int(vm["oom_kill"]), "swap_in_pages": int(vm["pswpin"]), "swap_out_pages": int(vm["pswpout"])}


if __name__ == "__main__":
    main()
