"""Freeze battery_rediscovery_v1 before the candidate runs.

    python -m benchmarks.battery_rediscovery_v1.freeze           # writes PLAN.json and PLAN.sha256
    python -m benchmarks.battery_rediscovery_v1.freeze --check   # exit 1 if any frozen file changed

There is no amendment mechanism.  If a defect is found after the seal, v1 is INVALIDATED and a v2 is created.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

from .candidate import baselines, mind_arm
from .candidate.common import load_pack, write_json
from .evaluator import conclusion as cr
from .evaluator import representability as rp

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V0 = HERE.parent / "battery_rediscovery_v0"
FROZEN_GLOBS = ("candidate/*.py", "candidate/pack/*.json", "evaluator/*.py", "evaluator/*.json", "*.py", "tests/*.py",
                "MUTATION_REPORT_pre_run.json", "V0_HISTORY.json")
MIND_FILES = sorted((ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py"))
COPIED_FROM_V0 = ("candidate/__init__.py", "candidate/common.py", "candidate/model.py", "candidate/baselines.py",
                  "candidate/mind_arm.py", "candidate/run.py", "candidate/pack/MANIFEST.json", "candidate/pack/P1.json",
                  "candidate/pack/P2.json", "sandbox_run.py", "build_pack.py", "evaluator/truth.py", "evaluator/score.py",
                  "evaluator/IDENTITY_MAP.json", "evaluator/PACK_PROVENANCE.json")
EVALUATOR_ONLY = ("evaluator/*", "leakage.py", "mutation.py", "build_pack.py", "freeze.py", "seal.py", "launch.py",
                  "v0_history.py", "V0_HISTORY.json", "MUTATION_REPORT_*.json", "results/EVALUATION.*",
                  "results/LEAKAGE_POST_SEAL.json")
EXPECTED_OUTPUTS = (
    [f"results/candidate/{a}__{p}.json" for a in ("MIND", "FIXED_FIT", "CAREFUL_BASELINE", "ALWAYS_FIT", "ALWAYS_REFUSE")
     for p in ("P1", "P2")] + ["results/candidate/MIND_TRACES__P1.json", "results/candidate/MIND_TRACES__P2.json",
                               "results/candidate/TIMINGS.json", "results/ACCESS_LOG.json", "results/LEAKAGE_PRE_SEAL.json",
                               "results/SEAL.json", "results/replay/REPLAY.json", "results/ACCESS_LOG_REPLAY.json",
                               "MUTATION_REPORT_post_seal.json", "results/LEAKAGE_POST_SEAL.json",
                               "results/EVALUATION.json", "results/EVALUATION.md"])


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def frozen_digests() -> dict[str, str]:
    files = set()
    for g in FROZEN_GLOBS:
        files |= {p for p in HERE.glob(g) if p.is_file()}
    files |= set(MIND_FILES)
    return {str(p.relative_to(ROOT)).replace("\\", "/"): _sha(p) for p in sorted(files)}


def plan() -> dict:
    v0_plan = json.loads((V0 / "PLAN.json").read_bytes())["frozen_files"]
    copied = {f: {"v1_sha256": _sha(HERE / f), "v0_plan_sha256": v0_plan.get(f"benchmarks/battery_rediscovery_v0/{f}")}
              for f in COPIED_FROM_V0}
    mutation = json.loads((HERE / "MUTATION_REPORT_pre_run.json").read_bytes())
    prov = json.loads((HERE / "evaluator" / "PACK_PROVENANCE.json").read_bytes())
    census = json.loads((V0 / "evaluator" / "CENSUS.json").read_bytes())
    raw = {r["path"]: r["external"]["sha256"] for r in census["rows"] if r.get("external", {}).get("sha256")}
    return {
        "schema": "forge.battery_rediscovery.plan/2",
        "id": "battery_rediscovery_v1", "task": "BR-BATT-REDISC-02",
        "status": "DEVELOPMENT clean confirmation: not formal, not certification, not a discovery claim",
        "v0": {"history_record_sha256": _sha(HERE / "V0_HISTORY.json"), "PREREGISTERED_RESULT": "LEAKAGE_INVALIDATED",
               "POST_SEAL_AMENDMENT_RESULT": "REPRESENTATION_BOTTLENECK", "CONFIRMED_RESULT": "NONE"},
        "hypotheses": {
            "H1": "the unchanged Minimal Mind arm underperforms CAREFUL_BASELINE primarily because its hypothesis/answer "
                  "representation cannot express enough of the scientifically correct battery judgments",
            "H0": "the gap remains after representation opportunities are controlled; representation alone does not "
                  "explain the Mind arm's weakness",
            "stance": "neither is preregistered as true"},
        "arms": {"MIND_V0_REPRESENTATION": "the v0 Mind arm (output label MIND), byte-identical candidate code",
                 "FIXED_FIT": "v0 baseline, byte-identical", "CAREFUL_BASELINE": "v0 baseline, byte-identical",
                 "ALWAYS_FIT": "trivial", "ALWAYS_REFUSE": "trivial"},
        "candidate_source": {"copied_from_v0_byte_exact": copied,
                             "mind_source_commit": "e2b8037c881847a497c32f7ca56f82b95b493727",
                             "mind_adapter": {"tolerance_ln": mind_arm.TOLERANCE_LN, "budget_max": mind_arm.BUDGET_MAX,
                                              "translation": mind_arm.TRANSLATION},
                             "seeds": {"primary": mind_arm.PRIMARY_SEED, "stability": list(mind_arm.STABILITY_SEEDS),
                                       "fit_starts": 8, "start_seed": 0}},
        "baseline_identities": {"careful_checks": {"max_sd_ln": baselines.MAX_SD_LN, "max_abs_corr": baselines.MAX_ABS_CORR,
                                                   "multistart_spread_ln": baselines.MULTISTART_SPREAD_LN,
                                                   "structured_lag1": baselines.STRUCTURED_LAG1}},
        "data": {"raw_sha256": raw, "split_data_sha256": {p: v["source_data_sha256"] for p, v in prov.items()},
                 "pack_sha256": {p: v["pack_sha256"] for p, v in prov.items()},
                 "splits": "the v0 pack, unchanged (same preregistered splits)"},
        "candidate_visible": ["benchmarks/battery_rediscovery_v1/candidate/**", "src/engcore/mind/minimal/*.py",
                              "the engcore platform modules the run imports (runtime-audited)"],
        "evaluator_only": [f"benchmarks/battery_rediscovery_v1/{g}" for g in EVALUATOR_ONLY],
        "leakage": {"scanner": "forge.battery_rediscovery.leakage_scanner@1.0.0", "scanner_sha256": _sha(HERE / "leakage.py"),
                    "mutation_report_pre_run_sha256": _sha(HERE / "MUTATION_REPORT_pre_run.json"),
                    "mutation_pre_run": {k: mutation[k] for k in ("status", "leak_mutations", "leaks_caught",
                                                                   "benign_controls", "benign_triggered")},
                    "post_seal": "the same scanner and mutation suite rerun with the protected values re-derived from "
                                 "the historical records (adds the Rint RMSEs); any failure is LEAKAGE_INVALIDATED"},
        "representability": {"capability": rp.CAPABILITY,
                             "reachable": {pid: rp.reachable(p) for pid, p in load_pack(HERE / "candidate" / "pack").items()},
                             "classification": "post-seal, from the historical truth and the frozen reachable sets only"},
        "scoring": "v0 evaluator/score.py outcome classes, byte-identical (CORRECT, CORRECT_REFUSAL, FALSE_SUPPORT, "
                   "FALSE_REJECT, UNSUPPORTED_DECISION, FALSE_REFUSE); truth from v0 evaluator/truth.py, byte-identical",
        "conclusion_rule": cr.RULE,
        "thresholds": cr.THRESHOLDS,
        "expected_outputs": EXPECTED_OUTPUTS,
        "amendments": "none permitted: a defect found after the seal marks v1 INVALIDATED and requires v2",
        "threats_to_validity": [
            "NOT an independent replication: the data, splits and candidate code are v0's, and the candidate is "
            "deterministic, so v1's candidate outputs are expected to equal v0's sealed outputs byte for byte. v1's "
            "value is a clean, unamended pipeline and a preregistered representability analysis, not new evidence about "
            "the data",
            "the developer is NOT blind: v0's per-instance answers and the historical truth were known when the "
            "capability table, the reachable-set rules and the thresholds were written. The thresholds were taken from "
            "the brief's own wording (majority = 0.5, a quarter = 0.25, half = 0.5); a reader should treat the conclusion "
            "as a structured restatement of v0 under a clean firewall, not as a blind confirmation",
            "the protected historical values used before the run come from v0's committed evaluation record, i.e. "
            "history already revealed; the candidate is firewalled, the evaluator is not blind",
            "REPRESENTABLE_APPROXIMATELY pools proxy paths of different fidelity; the exact-only subset has one instance"],
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
