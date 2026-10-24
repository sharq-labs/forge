"""Freeze the pilot plan before any arm sees the real pack: rules, scoring, conclusion rule and the digest of every file.

    python -m benchmarks.battery_rediscovery_v0.freeze           # writes PLAN.json and PLAN.sha256
    python -m benchmarks.battery_rediscovery_v0.freeze --check   # exit 1 if any frozen file changed

PLAN.json is committed before the first real run.  ``seal`` refuses to seal outputs produced by code whose digests
differ from the plan's.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

from .candidate import baselines, mind_arm
from .candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROZEN_GLOBS = ("candidate/*.py", "candidate/pack/*.json", "evaluator/*.py", "evaluator/*.json", "*.py", "tests/*.py")
MIND_FILES = sorted((ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py"))
MIND_SOURCE_COMMIT = "e2b8037c881847a497c32f7ca56f82b95b493727"
BASE_COMMIT = "12862b0b8821e2564d8c94853f31d44ced55eebf"


def frozen_digests() -> dict[str, str]:
    files = set()
    for g in FROZEN_GLOBS:
        files |= {p for p in HERE.glob(g) if p.is_file()}
    files |= set(MIND_FILES)
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def plan() -> dict:
    return {
        "schema": "forge.battery_rediscovery.plan/1",
        "id": "BR-BATT-REDISC-01",
        "status": "DEVELOPMENT pilot: not formal, not certification, not a discovery claim, not D5/N-1/Family-3a evidence",
        "base_commit": BASE_COMMIT,
        "mind": {"source_commit": MIND_SOURCE_COMMIT, "package": "engcore.mind.minimal", "copied_byte_exact": True,
                 "config": "FULL", "primary_seed": mind_arm.PRIMARY_SEED, "stability_seeds": list(mind_arm.STABILITY_SEEDS)},
        "problems": {
            "P1": "existing preregistered split, unchanged: calibration = early cycles of two sibling cells, within-cell "
                  "held-out = their next cycles, cross-cell held-out = early cycles of a third cell",
            "P2": "existing preregistered split, unchanged: calibration = pulses at two current levels; within-cell "
                  "held-out = pulses at two other levels + one constant-current discharge; no second cell"},
        "deviation_from_brief": "the brief prefers one primary + one held-out cell; P1 keeps its preregistered two-cell "
                                "calibration so that the comparison with history uses the identical split",
        "arms": ["MIND", "FIXED_FIT", "CAREFUL_BASELINE", "ALWAYS_FIT", "ALWAYS_REFUSE"],
        "existing_forge_baseline": "the strongest existing FORGE baseline is the historical preregistered pipeline itself; "
                                   "it IS the historical truth source, so it is the truth column, not an arm (it would "
                                   "agree with history by construction)",
        "fitting": {"model": "Thevenin 1RC, exact piecewise-constant update, backward hold", "starts": 8, "start_seed": 0,
                    "optimizer": "scipy least_squares trf, analytic Jacobian, log R0/R1/C1 (+ OCV table when fitted)",
                    "covariance": "SVD Gauss-Newton, null directions infinite, inflated by (1+rho)/(1-rho) for lag-1 rho"},
        "careful_checks": {"max_sd_ln": baselines.MAX_SD_LN, "max_abs_corr": baselines.MAX_ABS_CORR,
                           "bound_margin_ln": baselines.BOUND_MARGIN_LN,
                           "multistart_spread_ln": baselines.MULTISTART_SPREAD_LN,
                           "structured_lag1": baselines.STRUCTURED_LAG1},
        "mind_adapter": {"tolerance_ln": mind_arm.TOLERANCE_LN, "budget_max": mind_arm.BUDGET_MAX,
                         "min_soc": mind_arm.MIN_SOC, "translation": mind_arm.TRANSLATION,
                         "not_representable": mind_arm.NOT_REPRESENTABLE,
                         "probes": ["RELAXATION (identifiability)", "PREDICTION per held-out subset (within/cross)"]},
        "scoring": {
            "truth_vocabulary": ["SUPPORTED", "NOT_SUPPORTED", "NOT_ASSESSABLE"],
            "outcomes": {"CORRECT": "answer == decisive truth",
                         "CORRECT_REFUSAL": "non-committal answer (REVIEW/NOT_ASSESSABLE/REFUSED) where truth is "
                                            "NOT_ASSESSABLE",
                         "FALSE_SUPPORT": "SUPPORTED where truth is not SUPPORTED",
                         "FALSE_REJECT": "NOT_SUPPORTED where truth is SUPPORTED",
                         "UNSUPPORTED_DECISION": "NOT_SUPPORTED where truth is NOT_ASSESSABLE",
                         "FALSE_REFUSE": "non-committal answer where truth is decisive"},
            "best_baseline": "most CORRECT + CORRECT_REFUSAL; ties: fewer FALSE_SUPPORT, then fewer FALSE_REJECT + "
                             "UNSUPPORTED_DECISION, then name",
            "not_collapsed": "every axis, every outcome class and every secondary metric is reported separately",
            "secondary": ["parameter stability (multistart, forward-hold shift; Mind: disposition stability over seeds)",
                          "within-cell prediction error", "uncertainty calibration (95% coverage) where a measurement "
                          "uncertainty is declared", "observations/queries used", "replay completeness"]},
        "conclusion_rule": [
            "LEAKAGE_INVALIDATED if the pre-seal or post-seal leakage audit fails",
            "INCONCLUSIVE if the Mind did not run end to end on every problem, or a primary-seed Mind decision does not "
            "replay",
            "PROMISING_SIGNAL if the Mind's CORRECT + CORRECT_REFUSAL exceeds the best baseline's and its FALSE_SUPPORT "
            "does not",
            "BENCHMARK_TOO_EASY if a trivial arm (ALWAYS_FIT / ALWAYS_REFUSE) matches the best non-trivial arm's "
            "CORRECT + CORRECT_REFUSAL",
            "REPRESENTATION_BOTTLENECK if at least half of the Mind's scored answers are non-committal for a "
            "representation or interface cause (declared family not representable, probe problem refused, empty "
            "region, world refusals, passive-association of a covariate the protocol set, every rival refuted, or the "
            "Mind's own report that the rivals entertained do not contain the dependence)",
            "NO_MEASURED_ADVANTAGE otherwise"],
        "development_log": [
            "all development ran on synthetic problems with known parameters (tests/synthetic.py); no arm read the real "
            "pack before this plan was frozen",
            "dropped: an EXCITATION probe (step response vs |I|): on a synthetic single-current problem it turned 'no "
            "dependence on I' into 'R0 not identifiable', which is physically wrong (R0 = dV/I at one step)",
            "changed: the relaxation and the OCV-referenced load observables are divided by the driving current "
            "(impedance); the raw differences mixed two current levels into the Mind's replicate noise (sd 1.2 ln) "
            "and read the protocol's current level as a passive association",
            "changed: the Gauss-Newton covariance used a pseudo-inverse, which reports zero variance on null "
            "directions and would manufacture identifiability; it is now SVD-based with infinite null variance"],
        "threats_to_validity": [
            "the developer is NOT blind: the historical conclusions were known from session memory before the adapter "
            "and the baselines were designed; mitigated by copying the Mind byte-exact from a commit that predates "
            "this task, freezing every rule here before the first real run, and developing on synthetic data only",
            "P2 has one cell: its cross-cell truth is structural (no set supplied), not historical",
            "the historical MODEL_DISCREPANCY and P1 MODEL_ADEQUACY labels are derived from historical records by the "
            "rules in evaluator/truth.py, not stated verbatim as such",
            "the Mind's prediction probes cover only loaded samples at t_on >= median(dt)/tolerance; the fitting arms "
            "score every sample: the error statistics are not like for like"],
        "frozen_files": frozen_digests(),
    }


def main(argv: list[str]) -> int:
    if "--check" in argv:
        frozen = json.loads((HERE / "PLAN.json").read_bytes())["frozen_files"]
        now = frozen_digests()
        changed = sorted(k for k in set(frozen) | set(now) if frozen.get(k) != now.get(k))
        for k in changed:
            print("CHANGED", k)
        return 1 if changed else 0
    sha = write_json(HERE / "PLAN.json", plan())
    (HERE / "PLAN.sha256").write_bytes(f"{sha}  PLAN.json\n".encode())
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
