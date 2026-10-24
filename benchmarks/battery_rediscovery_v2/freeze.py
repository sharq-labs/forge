"""Freeze battery_rediscovery_v2 before the candidate runs.

    python -m benchmarks.battery_rediscovery_v2.freeze           # writes PLAN.json and PLAN.sha256
    python -m benchmarks.battery_rediscovery_v2.freeze --check   # exit 1 if any frozen file changed

There is no amendment mechanism.  If a defect is found after the seal, v2 is INVALIDATED and a v3 is created.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

from engcore.mind.repsem import RoleTable

from .candidate import arms, common
from .candidate.common import load_pack, write_json
from .evaluator import conclusion as cr

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REL = "benchmarks/battery_rediscovery_v2"
FROZEN_GLOBS = ("candidate/*.py", "candidate/pack/*.json", "evaluator/*.py", "evaluator/*.json", "*.py", "tests/*.py",
                "MUTATION_REPORT_pre_run.json")
IMPORTED_FROZEN = sorted(
    [ROOT / "benchmarks" / "battery_rediscovery_v1" / "candidate" / f
     for f in ("__init__.py", "common.py", "model.py", "baselines.py", "mind_arm.py")]
    + [ROOT / "benchmarks" / "battery_rediscovery_v1" / f for f in ("__init__.py", "leakage.py", "mutation.py")]
    + [ROOT / "benchmarks" / "mind_repsem_v1" / f for f in ("__init__.py", "arms.py", "fixtures.py")]
    + list((ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py"))
    + list((ROOT / "src" / "engcore" / "mind" / "repsem").glob("*.py"))
    + [ROOT / "src" / "engcore" / "mind" / "__init__.py", ROOT / "src" / "engcore" / "hybrid_uq" / "identifiability.py"])
PIDS = ("Q1", "Q2")
EXPECTED_OUTPUTS = (
    [f"results/candidate/{a}__{p}.json" for a in arms.ALL_ARMS for p in PIDS]
    + [f"results/candidate/OLD_MIND_TRACES__{p}.json" for p in PIDS]
    + ["results/candidate/TIMINGS.json", "results/ACCESS_LOG.json", "results/LEAKAGE_PRE_SEAL.json", "results/SEAL.json",
       "results/replay/REPLAY.json", "results/ACCESS_LOG_REPLAY.json", "MUTATION_REPORT_post_seal.json",
       "results/LEAKAGE_POST_SEAL.json", "results/TRUTH.json", "results/EVALUATION.json", "results/EVALUATION.md"])

BASE_COMMIT = "8603463936b3e4010ac2a541a7663976fae97703"
REPAIR_COMMIT = "cac1c584d8056720cc2c83f63fe93d3b32a83151"
REPAIR_TESTS_COMMIT = "db4397446774d789c92f7e0a20338f097d51e430"
MIND_SOURCE_COMMIT = "e2b8037c881847a497c32f7ca56f82b95b493727"


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rel(p: pathlib.Path) -> str:
    return str(p.resolve().relative_to(ROOT)).replace("\\", "/")


def frozen_digests() -> dict[str, str]:
    files = set()
    for g in FROZEN_GLOBS:
        files |= {p for p in HERE.glob(g) if p.is_file()}
    files |= set(IMPORTED_FROZEN)
    return {_rel(p): _sha(p) for p in sorted(files)}


def structural_assessability(spec: dict[str, Any]) -> dict[str, str]:
    """Which questions can be decided at all, from the pack's declarations alone (no data, no fit)."""
    noise = spec["measurement_noise"]
    sigma, bound = noise.get("sigma"), noise.get("half_width")
    sets = spec.get("sets") or {}
    out = {"MODEL_ADEQUACY": "ASSESSABLE: a declared adequacy bar (risk policy) needs no measurement uncertainty"
           if spec.get("adequacy_bar") else "NOT_ASSESSABLE: no bar"}
    out["IDENTIFIABILITY"] = ("ASSESSABLE: declared measurement uncertainty" if sigma is not None else
                              "NOT_ASSESSABLE unless near-structural non-identifiability: no declared measurement "
                              "uncertainty, so practical identifiability cannot be shown")
    for axis, set_name in (("WITHIN_CELL_GENERALIZATION", "within_unit_heldout"), ("CROSS_CELL_TRANSFER", "cross_unit_heldout")):
        out[axis] = ("ASSESSABLE: declared bar and applicability domain" if sets.get(set_name)
                     else "NOT_ASSESSABLE: no such held-out set is supplied")
    out["MODEL_DISCREPANCY"] = ("ASSESSABLE: a declared Type-B bound on the measurement error" if sigma is not None and bound
                                else "NOT_ASSESSABLE: the measurement uncertainty is UNKNOWN and the plan defines no "
                                     "defensible bound")
    return out


def plan() -> dict[str, Any]:
    problems = load_pack()
    prov = json.loads((HERE / "evaluator" / "PACK_PROVENANCE.json").read_bytes())
    mutation = json.loads((HERE / "MUTATION_REPORT_pre_run.json").read_bytes())
    fams = {pid: {k: f.to_dict() for k, f in arms.families_for(spec).items()
                  if k in (spec["declared_family"]["family_id"], spec["declared_family"]["rival"])}
            for pid, spec in problems.items()}
    return {
        "schema": "forge.battery_rediscovery_v2.plan/1", "id": "battery_rediscovery_v2", "task": "BR-BATT-REDISC-03",
        "status": "DEVELOPMENT fresh real-data confirmation: not formal, not certification, not a discovery claim",
        "sources": {"base_commit": BASE_COMMIT, "repsem_repair_commit": REPAIR_COMMIT,
                    "repsem_failing_first_tests_commit": REPAIR_TESTS_COMMIT,
                    "minimal_mind_source_commit": MIND_SOURCE_COMMIT,
                    "repair_result_carried_in": "READY_FOR_BATTERY_V2 on synthetic fixtures only (development evidence)",
                    "imported_frozen_files": {_rel(p): _sha(p) for p in IMPORTED_FROZEN}},
        "data": {
            "Q1": {"source": "public Li-ion aging archive, three sibling cells at 44 C (pseudonyms A, B, C); never used by "
                             "v0, v1 or the repsem repair", "raw": prov["Q1"]["raw_sha256"],
                   "archive_sha256": prov["Q1"]["archive_sha256"], "pack_sha256": prov["Q1"]["pack_sha256"]},
            "Q2": {"source": "the LG HG2 25 C HPPC discharge-pulse windows of the identifiability study, re-split by "
                             "state-of-charge set point (v1 split them by current level; the constant-current test "
                             "v1 held out is not used: its outcome is known)", "split": prov["Q2"]["split_sha256"],
                   "soc_groups_z0": prov["Q2"]["soc_groups"], "calibration_ranks": prov["Q2"]["calibration_ranks"],
                   "pack_sha256": prov["Q2"]["pack_sha256"]},
            "pack_manifest_sha256": _sha(HERE / "candidate" / "pack" / "MANIFEST.json"),
            "identity_map_sha256": _sha(HERE / "evaluator" / "IDENTITY_MAP.json"),
            "splits": {pid: {"calibration": [t["id"] for t in spec["sets"]["calibration"]],
                             **{f"{s}/{k}": [t["id"] for t in v] for s in ("within_unit_heldout", "cross_unit_heldout")
                                for k, v in (spec["sets"].get(s) or {}).items()}} for pid, spec in problems.items()}},
        "protocol_roles": {pid: {"role_table_digest": RoleTable.from_spec(spec).digest,
                                 "declarations": RoleTable.from_spec(spec).to_dict()["declarations"]}
                           for pid, spec in problems.items()},
        "uncertainty_inputs": {pid: spec["measurement_noise"] for pid, spec in problems.items()},
        "structural_assessability": {pid: structural_assessability(spec) for pid, spec in problems.items()},
        "model_space": {"families": fams, "fitted_ocv_knots_soc": list(common.FITTED_OCV_KNOTS_SOC),
                        "fitted_ocv_bounds_V": list(common.FITTED_OCV_BOUNDS_V),
                        "rule": "the candidate-visible model vocabulary is exactly the declared family and its declared "
                                "rival per problem; no model is added after the run"},
        "arms": {
            "OLD_MIND": "v1's Minimal Mind arm (engcore.mind.minimal byte-exact from the Mind source commit) on the v1 view",
            "REPRESENTATION_ONLY": "engcore.mind.repsem.assess under the v1 adapter's two-class legacy role table",
            "SEMANTIC_ROLES_ONLY": "the v1 Mind with its prediction probe posed by the declared roles (current settable, "
                                   "charge state never a free covariate, temperature passive); v1 answer vocabulary",
            "REPRESENTATION_PLUS_ROLES": "engcore.mind.repsem.assess under the pack's declared roles",
            "CAREFUL_BASELINE": "v1's careful baseline on the v1 view",
            "FIXED_FIT": "v1 reference baseline (context only)", "ALWAYS_FIT": "trivial (context only)",
            "ALWAYS_REFUSE": "trivial (context only)", "module": f"{REL}/candidate/arms.py (docstring frozen with it)"},
        "arm_roles": {"compared": list(arms.ARMS), "reference_only": list(arms.REFERENCE_ARMS)},
        "seeds_and_budgets": {"seeds": list(common.SEEDS), "primary_seed": common.PRIMARY_SEED,
                              "mind_budget_queries_per_probe": 40, "mind_tolerance_ln": 0.05,
                              "repsem_starts": "2^p + 1 (engine constant)", "repsem_max_nfev": 200,
                              "v1_baseline_fit_starts": 8,
                              "note": "deterministic arms give the same answers for every seed and run once"},
        "truth_protocol": {"module": f"{REL}/evaluator/reference.py", "margin": 1.10,
                           "computed": "only after the seal is verified (evaluator/truth.py refuses otherwise)",
                           "independence": "a separate implementation of the declared forward model and a denser oracle "
                                           "fit; it reads no candidate code or output",
                           "doc": "see the module docstring (frozen with it)"},
        "scoring": {"module": f"{REL}/evaluator/score.py", "doc": "see the module docstring (frozen with it)"},
        "hypotheses": {
            "H1": "REPRESENTATION_PLUS_ROLES reduces false refusal relative to OLD_MIND without increasing false support",
            "H2": "REPRESENTATION_PLUS_ROLES outperforms each single-layer arm on scientifically assessable axes",
            "H3": "REPRESENTATION_PLUS_ROLES moves toward the CAREFUL baseline on held-out real data",
            "operationalisation": "evaluator/conclusion.py docstring", "thresholds": cr.THRESHOLDS},
        "conclusion_rule": {"module": f"{REL}/evaluator/conclusion.py", "verdicts": list(cr.VERDICTS),
                            "amendments": "none: a post-seal defect invalidates v2 and requires v3"},
        "leakage": {"firewall": "leakage.py (v2 policy over v1's numeric/text engines)",
                    "scanner_sha256": _sha(HERE / "leakage.py"),
                    "numeric_engine_sha256": _sha(ROOT / "benchmarks" / "battery_rediscovery_v1" / "leakage.py"),
                    "mutation_report_pre_run_sha256": _sha(HERE / "MUTATION_REPORT_pre_run.json"),
                    "mutation_pre_run": {k: mutation[k] for k in ("status", "leak_mutations", "leaks_caught",
                                                                  "benign_controls", "benign_triggered")},
                    "blind_execution": "the candidate runs once, in a sandboxed subprocess under an audit hook, from a "
                                       "committed clean freeze; it may read only the candidate package, the pack, the "
                                       "imported frozen code and the engcore platform; outputs are write-only during the "
                                       "run; no truth exists until after the seal"},
        "candidate_visible": ["candidate/", *sorted(_rel(p) for p in IMPORTED_FROZEN if "leakage" not in p.name
                                                    and "mutation" not in p.name)],
        "threats_to_validity": [
            "the developer is NOT blind to history: v0/v1 per-instance answers and truths, the repsem gap map and fixtures, "
            "and the LG HG2 study's results (1RC with a measured OCV fits its pulses to about 12-13 mV) were known when "
            "this plan, the Q2 re-split and the bars were written; bars are inherited verbatim from the v1 pack "
            "(50/90 mV for the aging-archive class, 15/30 mV for the pulse class) to avoid choosing them",
            "Q2 is the same pulse windows as v1's P2, re-split: it is a new arrangement, not new data",
            "the Q1 data are fresh for this project's Mind work, but the archive's 44 C cells may have been used by "
            "earlier, unrelated battery flagship work; no number from such work is read here",
            "the Q1 design was chosen from protocol covariates (ambient, level, cycle order, recorded temperature ranges) "
            "before any fit; the applicability margins (1 C, 0.05 A, 0.02 charge state) are a declared scope policy, "
            "set after seeing covariate ranges but before any voltage was compared with a model",
            "a 24 C, 4 A problem was dropped before any fit because the causal capacity convention breaks there",
            "the frozen v1 baselines and Mind adapter implement v1's coarser domain rule (no charge-state range from "
            "calibration, no protocol-level check); the truth uses the pack's declared rule",
            "OLD_MIND and SEMANTIC_ROLES_ONLY cannot judge adequacy or discrepancy at all (v1 vocabulary)",
            "about ten scored instances in total: a single instance moves every hypothesis"],
        "expected_outputs": list(EXPECTED_OUTPUTS),
        "frozen_files": frozen_digests(),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--check":
        plan_ = json.loads((HERE / "PLAN.json").read_bytes())
        now = frozen_digests()
        bad = sorted(k for k in set(now) | set(plan_["frozen_files"]) if now.get(k) != plan_["frozen_files"].get(k))
        for k in bad:
            print("CHANGED:", k, file=sys.stderr)
        return 1 if bad else 0
    sha = write_json(HERE / "PLAN.json", plan())
    (HERE / "PLAN.sha256").write_bytes(f"{sha}  PLAN.json\n".encode())
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
