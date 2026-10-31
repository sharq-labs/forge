"""Bounded development mutation checks, NOT the certified OD-3 population.

Run only in a disposable, clean native clone; source bytes are restored after
each mutant. Every mutant must compile and produce exit 1 with named failures.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

MUTANTS = (
    ("shared_depot_marker_bypass", "runtime_assets_v4.py",
     'identity["shared_depots"] = [shared_depot_identity(entry) for entry in entries[1:]]',
     'identity["shared_depots"] = []',
     "test_v04_runtime_assets.py::test_loaded_depot_is_bound_even_without_the_optional_cache_marker"),
    ("sysimage_digest_bypass", "runtime_assets_v4.py", 'if manifest["sysimage_sha256"] != sha(image):', "if False:",
     "test_v04_runtime_assets.py::test_changed_asset_refuses[test.so]"),
    ("late_completion_admitted", "deadline_v4.py", "if finished > cutoff:", "if False:",
     "test_v04_deadline.py::test_a_completed_record_in_the_cutoff_race_is_retained_but_never_valid"),
    ("reused_pid_included", "telemetry_v4.py", "if start_time(pid) != born:", "if False:",
     "test_v04_telemetry.py::test_reused_pid_cannot_contribute_memory_threads_or_loaded_images"),
    ("unsolicited_diagnostics", "isolated_host.py", "if not self._diagnostics:", "if False:",
     "test_v04_performance.py::test_unrequested_diagnostics_are_not_a_new_protocol_channel"),
    ("private_tmp_not_required", "isolated_host.py", 'and o["private_tmp"]', "and True",
     "test_v04_isolation.py::test_outside_verification_fails_closed_on_any_missing_property"),
    ("missing_traces_equal", "analyse.py",
     "if len(expected) != 6 or len(set(expected)) != 6 or sorted(seen) != sorted(expected):", "if False:",
     "test_v04_performance_analysis.py::test_equal_missing_evidence_never_becomes_exact_equivalence[all]"),
    ("duplicate_tasks_collapse", "analyse.py", "if key(record) in indexed:", "if False:",
     "test_v04_performance_analysis.py::test_duplicate_and_missing_tasks_do_not_collapse_into_a_complete_comparison"),
    ("empty_comparison_passes", "analyse.py", "not matched or missing or extra or incomplete",
     "missing or extra or incomplete",
     "test_v04_performance_analysis.py::test_duplicate_and_missing_tasks_do_not_collapse_into_a_complete_comparison"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = pathlib.Path.cwd()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise RuntimeError("mutation clone must start clean")
    out = pathlib.Path(args.out).resolve()
    if out.is_relative_to(root):
        raise ValueError("evidence must be outside the mutation clone")
    out.mkdir(exist_ok=False, parents=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root / "src"), OPENBLAS_NUM_THREADS="1")
    base = [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
            "-o", "pythonpath=" + str(root / "src")]
    tests = ["tests/genesis_lite/" + item[4] for item in MUTANTS]
    control = subprocess.run([*base, *tests], env=env, capture_output=True, text=True)
    (out / "control.log").write_text(control.stdout + control.stderr)
    if control.returncode != 0:
        raise RuntimeError("CONTROL RED; mutants not executed")
    results = []
    for name, module, old, new, test in MUTANTS:
        path = root / ("tools/genesis_performance" if module == "analyse.py" else "benchmarks/genesis_lite") / module
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        source = original.decode()
        if source.count(old) != 1:
            raise RuntimeError(f"ambiguous mutation anchor: {name}")
        mutated = source.replace(old, new)
        compile(mutated, str(path), "exec")
        try:
            path.write_text(mutated)
            run = subprocess.run([*base, "tests/genesis_lite/" + test], env=env, capture_output=True, text=True)
            transcript = run.stdout + run.stderr
            (out / (name + ".log")).write_text(transcript)
            results.append({"name": name, "exit_code": run.returncode,
                            "killed": run.returncode == 1 and "FAILED tests/genesis_lite/" in transcript,
                            "source_before_sha256": before})
        finally:
            path.write_bytes(original)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    (out / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results))
    if not all(item["killed"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
