"""Break each calibration/UQ/validation guard once, on purpose, and watch it fail.

Why this is a separate script rather than entries in ``tests/mutation_guards.py``
---------------------------------------------------------------------------------
That runner is itself inside certified scope and is pinned by the Core
certificate. Adding a ``MUTATIONS`` entry for a guard written this round would
invalidate the certification snapshot, so guards added between certifications
are exercised by a targeted apply/revert script -- the same arrangement the
EI/RI/FM/SP families already use. **These are NOT part of the certified 79 and
are never added to that count.**

What it does
------------
For each mutation: apply an exact textual edit to a source file IN PLACE,
run the test that names the guard, require it to go RED, then restore the file
and verify the restore by SHA-256 against the bytes read before the edit. A
mutation whose restore does not verify aborts the whole run, because every
result after it would be measured against a tree nobody can describe.

An unmutated CONTROL runs first. Without it a RED result says nothing: it could
be the mutation, or it could be a suite that was already failing.

    python -X utf8 benchmarks/calibration_uq/audit/mutations.py [--only CAL-1,UQ-2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
BASETEMP = "D:/fbt_mut"

SPLIT = "src/engcore/inference/split.py"
PARAMETERS = "src/engcore/inference/parameters.py"
CALIBRATION = "src/engcore/inference/calibration.py"
STUDY = "src/engcore/studies/calibration_study.py"
GRID = "src/engcore/inference/grid.py"
ADEQUACY = "src/engcore/adequacy/predictive.py"

T_SPLIT = "tests/inference/test_observation_split.py"
T_PARAM = "tests/inference/test_parameter_identity.py"
T_CAL = "tests/inference/test_tcr_calibration.py"
T_UQ = "tests/inference/test_tcr_heldout_uq.py"
T_EVID = "tests/inference/test_reproducibility_and_evidence.py"

#: (id, file, [(old, new), ...], test target, what the guard is)
MUTATIONS: tuple[tuple[str, str, list[tuple[str, str]], str, str], ...] = (
    (
        "CAL-1", SPLIT,
        [(
            "        shared_keys = sorted(set(self.calibration.keys) & set(self.held_out.keys))",
            "        shared_keys = []",
        )],
        f"{T_SPLIT}::test_an_observation_in_both_halves_is_refused",
        "calibration/held-out overlap stops being refused",
    ),
    (
        "CAL-2", PARAMETERS,
        [('IDENTITY_FIELDS = (\n    "name",\n    "unit",', 'IDENTITY_FIELDS = (\n    "name",')],
        f"{T_PARAM}::test_same_label_different_unit_is_not_the_same_parameter",
        "a parameter's unit stops being part of its identity",
    ),
    (
        "CAL-3", PARAMETERS,
        [("        if not self.bounds.contains(value):", "        if False:")],
        f"{T_PARAM}::test_a_value_outside_physical_bounds_is_refused_not_downweighted",
        "a value outside the declared physical bounds is accepted",
    ),
    (
        "CAL-4", STUDY,
        [("    if p_value < HELD_OUT_CHI_SQUARE_ALPHA:", "    if False:")],
        f"{T_UQ}::test_a_misspecified_model_converges_and_is_rejected",
        "held-out validation always passes, so convergence becomes adequacy",
    ),
    (
        "CAL-5", SPLIT,
        [(
            '        given = str(posterior_dataset_id).strip()\n'
            '        if given == self.calibration.dataset_id:',
            '        return\n'
            '        given = str(posterior_dataset_id).strip()\n'
            '        if given == self.calibration.dataset_id:',
        )],
        f"{T_SPLIT}::test_a_posterior_conditioned_on_the_heldout_set_is_refused",
        "the posterior's dataset identity stops being checked",
    ),
    (
        "UQ-1", STUDY,
        [(
            "            observation_sigma=observation_sigma,\n"
            "        )\n"
            "        quantified = posterior_predictive_uq(",
            "            observation_sigma=None,\n"
            "        )\n"
            "        quantified = posterior_predictive_uq(",
        )],
        f"{T_UQ}::test_parameter_and_measurement_uncertainty_are_separately_reported",
        "the declared observation sigma is dropped from the predictive interval",
    ),
    (
        "UQ-2", GRID,
        [(
            "        centered = self.points - self.mean\n"
            "        return centered.T @ (centered * self.weights[:, None])",
            "        return np.zeros((self.points.shape[1], self.points.shape[1]))",
        )],
        f"{T_CAL}::test_parameter_covariance_and_intervals_are_available",
        "the posterior reports zero parameter covariance",
    ),
    (
        "UQ-3", STUDY,
        [(
            "UNCERTAINTY_SOURCES = (\n"
            "    PARAMETER_UNCERTAINTY,\n"
            "    MEASUREMENT_UNCERTAINTY,\n"
            "    MODEL_DISCREPANCY_NOT_MODELLED,\n"
            ")",
            "UNCERTAINTY_SOURCES = (\n"
            "    PARAMETER_UNCERTAINTY,\n"
            "    MEASUREMENT_UNCERTAINTY,\n"
            ")",
        )],
        f"{T_UQ}::test_model_discrepancy_is_recorded_as_not_modelled",
        "one uncertainty source stops being named",
    ),
    (
        "UQ-4", STUDY,
        [("    low, high = wilson_interval(covered, total)\n    band_low",
          "    low = high = nominal\n    band_low")],
        f"{T_UQ}::test_coverage_classification_uses_the_interval_not_the_point",
        "nominal coverage is reported as though it were measured",
    ),
    (
        "UQ-5", CALIBRATION,
        [("    if ess < minimum_effective_points and worst_spacing >= 1.0:",
          "    if False:")],
        f"{T_UQ}::test_case_b_a_collapsed_posterior_is_a_grid_refusal",
        "a collapsed grid is allowed to claim precise parameters",
    ),
    (
        "VAL-1", STUDY,
        [(
            "    predictive_table = tcr_forward_table(\n"
            "        split.held_out,\n"
            "        [tuple(float(v) for v in row) for row in posterior.points],\n"
            "        reference_temperature=reference_temperature,\n"
            "        temperatures_by_condition=temperatures_by_condition,\n"
            "        counter=counter,\n"
            "    )\n"
            "\n"
            "    residuals: list[float] = []",
            "    predictive_table = tcr_forward_table(\n"
            "        split.calibration,\n"
            "        [tuple(float(v) for v in row) for row in posterior.points],\n"
            "        reference_temperature=reference_temperature,\n"
            "        temperatures_by_condition=temperatures_by_condition,\n"
            "        counter=counter,\n"
            "    )\n"
            "\n"
            "    residuals: list[float] = []",
        ),
         ("    for observation in split.held_out.observations:\n"
          "        spec = PredictiveObservableSpec(\n"
          "            observation_key=observation.key,\n"
          "            unit=OHM,\n"
          "            observation_sigma=observation_sigma,\n"
          "        )\n"
          "        assessment = assess_predictive_observation(",
          "    for observation in split.calibration.observations:\n"
          "        spec = PredictiveObservableSpec(\n"
          "            observation_key=observation.key,\n"
          "            unit=OHM,\n"
          "            observation_sigma=observation_sigma,\n"
          "        )\n"
          "        assessment = assess_predictive_observation(")],
        f"{T_UQ}::test_the_well_specified_model_passes_held_out_validation",
        "the calibration half is scored as though it were held out",
    ),
    (
        "VAL-2", ADEQUACY,
        [(
            "        mine, theirs = self._canonical(), other._canonical()\n"
            "        return tuple(\n"
            "            name for name in EVIDENCE_IDENTITY_FIELDS if mine.get(name) != theirs.get(name)\n"
            "        )",
            "        mine, theirs = self._canonical(), other._canonical()\n"
            "        return ()",
        )],
        f"{T_EVID}::test_two_assessments_of_different_evidence_cannot_be_compared",
        "evidence identity stops distinguishing two bodies of evidence",
    ),
)


def run_tests(target: str) -> tuple[bool, str]:
    """True when the target is GREEN."""
    proc = subprocess.run(
        [PYTHON, "-X", "utf8", "-m", "pytest", target, "-q",
         "-p", "no:cacheprovider", "--basetemp", BASETEMP],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    return proc.returncode == 0, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}

    print("CONTROL: the targets must be GREEN before anything is mutated")
    targets = sorted({m[3].split("::")[0] for m in MUTATIONS})
    control_ok = True
    for target in targets:
        ok, summary = run_tests(target)
        print(f"  {'GREEN' if ok else 'RED  '}  {target}  :: {summary}")
        control_ok &= ok
    if not control_ok:
        print("\nCONTROL RED -- a mutation result would say nothing. Stopping.")
        return 2
    print("CONTROL GREEN\n")

    results = []
    for identifier, relative, edits, target, description in MUTATIONS:
        if wanted and identifier not in wanted:
            continue
        path = ROOT / relative
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")

        mutated = text
        for old, new in edits:
            if old not in mutated:
                print(f"{identifier:6} STALE  pattern not found in {relative}")
                results.append(
                    {"id": identifier, "verdict": "STALE", "file": relative,
                     "description": description}
                )
                mutated = None
                break
            if mutated.count(old) != 1:
                print(f"{identifier:6} STALE  pattern is not unique in {relative}")
                results.append(
                    {"id": identifier, "verdict": "STALE", "file": relative,
                     "description": description}
                )
                mutated = None
                break
            mutated = mutated.replace(old, new, 1)
        if mutated is None:
            continue

        started = time.monotonic()
        # Bytes, not text: write_text on Windows would rewrite every line
        # ending and the restore digest below would then be comparing a
        # different file against itself.
        path.write_bytes(mutated.encode("utf-8"))
        try:
            green, summary = run_tests(target)
        finally:
            path.write_bytes(original)
            restored = hashlib.sha256(path.read_bytes()).hexdigest()
        # Checked OUTSIDE the finally: a `return` inside one swallows any
        # exception in flight, so a restore failure during a crash would have
        # hidden the crash and reported a tidy exit code instead.
        if restored != digest:
            print(f"\n{identifier}: RESTORE FAILED for {relative}. Stopping.")
            return 3
        seconds = time.monotonic() - started

        verdict = "SURVIVED" if green else "KILLED"
        print(f"{identifier:6} {verdict:9} {description}")
        print(f"       {target}")
        print(f"       {summary}  ({seconds:.1f}s)")
        results.append(
            {"id": identifier, "verdict": verdict, "file": relative,
             "target": target, "description": description, "summary": summary}
        )

    killed = sum(1 for r in results if r["verdict"] == "KILLED")
    survived = [r for r in results if r["verdict"] == "SURVIVED"]
    stale = [r for r in results if r["verdict"] == "STALE"]
    print(f"\n{killed}/{len(results)} mutations killed by the guard they name.")
    if survived:
        print("SURVIVORS (each needs a written classification):")
        for r in survived:
            print(f"  {r['id']}: {r['description']}")
    if stale:
        print("STALE patterns (the mutation no longer matches its source):")
        for r in stale:
            print(f"  {r['id']}: {r['file']}")

    out = ROOT / "benchmarks" / "calibration_uq" / "MUTATIONS.json"
    out.write_bytes(
        json.dumps(
            {"control": "GREEN", "killed": killed, "total": len(results),
             "survivors": [r["id"] for r in survived],
             "stale": [r["id"] for r in stale], "results": results},
            indent=2,
        ).encode("utf-8")
    )
    print(f"wrote {out}")
    return 0 if (not survived and not stale) else 1


if __name__ == "__main__":
    raise SystemExit(main())
