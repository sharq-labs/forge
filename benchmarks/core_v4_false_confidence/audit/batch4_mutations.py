"""Batch-4 guards, each disabled in place, its catching test run, the file restored and verified by digest.

Not in tests/mutation_guards.py: that file is certification-pinned, so new guards join it in the Core Freeze V4 round.
Run from the repository root with SCRATCH set to a scratch directory.
"""
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

PY = sys.executable
SCRATCH = pathlib.Path(os.environ["SCRATCH"])
T = "tests/hybrid_uq/test_core_scientific_audit_batch4.py"

MUTATIONS = [
    ("B4a", "src/engcore/hybrid_uq/predictive.py::_prediction_domain_reasons",
     "        if x < low - slack or x > high + slack:\n", "        if False:\n",
     T + "::test_core006_an_extrapolated_prediction_is_downgraded_and_an_interpolated_one_is_not"),
    ("B4b", "src/engcore/hybrid_uq/predictive.py::_prediction_domain_reasons",
     "    if not observations or not spec.conditions:\n", "    if False:\n",
     T + "::test_core006_a_prediction_with_no_declared_domain_is_downgraded"),
    ("B4c", "src/engcore/hybrid_uq/predictive.py::linearized_predictive_uq",
     "        spec_reasons = reasons | _prediction_domain_reasons(spec, calibration_observations)\n",
     "        spec_reasons = set(reasons)\n",
     T + "::test_core006_an_extrapolated_prediction_is_downgraded_and_an_interpolated_one_is_not"),
    ("B4d", "src/engcore/adequacy/predictive.py::assess_predictive_observation",
     "        _require_posterior_conditioned_on_calibration(split, posterior, calibration_table)\n", "        pass\n",
     T + "::test_core007_a_held_out_point_inside_the_conditioning_set_is_refused_when_the_split_is_given"),
    ("B4e", "src/engcore/adequacy/predictive.py::compare_log_predictive_scores",
     "    if not all(item.content_bound for item in (*a, *b)):\n", "    if False:\n",
     T + "::test_core007_the_same_decisive_difference_on_unbound_evidence_names_no_preferred_model"),
    ("B4f", "src/engcore/adequacy/predictive.py::compare_log_predictive_scores",
     "    elif abs(delta) <= COMPARISON_MINIMUM_ABS_DELTA:\n", "    elif False:\n",
     T + "::test_core011_a_negligible_difference_names_no_preferred_model"),
    ("B4g", "src/engcore/hybrid_uq/predictive.py::RoutedPredictiveUncertainty.to_dict",
     '            "measurement_errors_assumed_independent": bool(self.measurement_errors_assumed_independent),\n', "",
     T + "::test_core012_every_routed_prediction_states_that_errors_are_assumed_independent"),
]

for mid, spec, old, new, test in MUTATIONS:
    path = ROOT / spec.partition("::")[0]
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    try:
        applied = M._apply(ROOT, spec, old, new)
        if isinstance(applied, str):
            print(mid, "->", applied, flush=True)
            continue
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / ('b4_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'b4_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
