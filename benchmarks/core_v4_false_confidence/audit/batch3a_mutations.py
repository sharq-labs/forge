"""Batch-3a guards, each disabled in place, its catching test run, the file restored and verified by digest.

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
T = "tests/test_core_scientific_audit_batch3a.py"

MUTATIONS = [
    ("B3a", "src/engcore/scientific/results/validation.py::ValidationReport.status",
     "        if ValidationOutcome.NOT_RUN in outcomes or not outcomes:\n", "        if not outcomes:\n",
     T + "::test_core013_a_report_with_a_check_that_never_ran_is_not_a_pass"),
    ("B3b", "src/engcore/scientific/results/validation.py::ValidationReport.evidence_basis",
     "        if attained & VALIDATION_LEVELS:\n", "        if attained:\n",
     T + "::test_core008_a_report_says_when_its_evidence_is_verification_only"),
    ("B3c", "src/engcore/mcp/evidence.py::CredibilityEvidenceReport.to_dict",
     '                "evidence_basis": ValidationReport(checks=tuple(self.validation)).evidence_basis,\n',
     '                "evidence_basis": "VALIDATED",\n',
     "tests/mcp/test_evidence.py::test_core008_a_verdict_resting_on_verification_alone_says_so_in_every_report"),
    ("B3d", "src/engcore/scientific/experiments/experiment.py::ScientificExperiment.best",
     "            and _established(e)\n", "            and True\n",
     T + "::test_core015_an_unassessed_or_unknown_candidate_is_never_best"),
    ("B3e", "src/engcore/scientific/experiments/experiment.py::_established",
     "        model_id in validity and validity[model_id].status is ValidityStatus.IN_DOMAIN for model_id, _version in models\n",
     "        model_id in validity for model_id, _version in models\n",
     T + "::test_core015_an_unassessed_or_unknown_candidate_is_never_best"),
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
        done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / ('b3_' + mid)}", test],
                              cwd=ROOT, capture_output=True, text=True)
        last = [l for l in done.stdout.splitlines() if l.strip()][-1]
        print(mid, test.split("::")[-1], "->", "KILLED" if done.returncode != 0 else "SURVIVED", "|", last, flush=True)
    finally:
        path.write_bytes(original)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
done = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={SCRATCH / 'b3_control'}",
                       *sorted({m[4] for m in MUTATIONS})], cwd=ROOT, capture_output=True, text=True)
print("CONTROL (unmutated)", "GREEN" if done.returncode == 0 else "RED", "|", [l for l in done.stdout.splitlines() if l.strip()][-1])
