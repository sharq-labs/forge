"""Freeze battery_rediscovery_v3 before the candidate runs.

    python -m benchmarks.battery_rediscovery_v3.freeze           # writes PLAN.json and PLAN.sha256
    python -m benchmarks.battery_rediscovery_v3.freeze --check   # exit 1 if any frozen file changed

Refuses to write unless the GEN1 reference is intact (every GEN1 file byte-identical to the sealed record), the pre-run
mutation report is PASS and the pre-run static leakage audit of the candidate material is PASS.  There is no amendment
mechanism: a post-seal defect invalidates v3 and requires a v4.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

from benchmarks.battery_rediscovery_v2 import freeze as v2freeze
from benchmarks.battery_rediscovery_v2.candidate import arms, common
from benchmarks.battery_rediscovery_v2.candidate.common import load_pack, write_json
from engcore.mind.repsem import RoleTable, VariableRole

from . import gen1_reference, leakage, mutation
from .evaluator import conclusion as cr
from .evaluator import diagnostics, reference_b

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REL = "benchmarks/battery_rediscovery_v3"
PACK = HERE / "CandidateBundle"
VAULT = HERE / "EvaluatorVault"
FROZEN_GLOBS = ("*.py", "evaluator/*.py", "tests/*.py", "CandidateBundle/*.json", "EvaluatorVault/*.json",
                "MUTATION_REPORT_pre_run.json", "LEAKAGE_PRE_RUN.json")
EXTRA_FROZEN = ("docs/discovery/mind_gen1_reference.json", "docs/discovery/MIND_GEN1_REFERENCE.md",
                "benchmarks/battery_rediscovery_v2/evaluator/reference.py",
                "benchmarks/battery_rediscovery_v2/evaluator/score.py",
                "benchmarks/battery_rediscovery_v2/build_pack.py",
                "benchmarks/battery_rediscovery_v2/tests/synthetic_pack.py")
AXES = common.AXES
HELDOUT = {"WITHIN_CELL_GENERALIZATION": "within_unit_heldout", "CROSS_CELL_TRANSFER": "cross_unit_heldout"}


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rel(p: pathlib.Path) -> str:
    return str(p.resolve().relative_to(ROOT)).replace("\\", "/")


def gen1_files() -> list[str]:
    rec = json.loads((ROOT / "docs" / "discovery" / "mind_gen1_reference.json").read_bytes())
    return sorted(gen1_reference.bound_files(rec))


def frozen_digests() -> dict[str, str]:
    files = set()
    for g in FROZEN_GLOBS:
        files |= {p for p in HERE.glob(g) if p.is_file()}
    files |= {ROOT / f for f in (*EXTRA_FROZEN, *gen1_files())}
    return {_rel(p): _sha(p) for p in sorted(files)}


def instances(problems: dict[str, Any], primary: list[str], bridge: list[str]) -> dict[str, list[dict[str, Any]]]:
    def rows(pids):
        return [{"key": f"{pid}/{axis}", "problem": pid, "axis": axis,
                 "heldout": axis in HELDOUT and bool((problems[pid].get("sets") or {}).get(HELDOUT[axis]))}
                for pid in pids for axis in AXES]
    return {"primary": rows(primary), "bridge": rows(bridge)}


def model_space(spec: dict[str, Any]) -> dict[str, Any]:
    roles = RoleTable.from_spec(spec)
    fam = spec["declared_family"]
    fams = {k: f.to_dict() for k, f in arms.families_for(spec).items() if k in (fam["family_id"], fam["rival"])}
    return {"family_id": fam["family_id"], "rival": fam["rival"], "equations": fam["equations"],
            "state_variables": roles.names(VariableRole.STATE_VARIABLE),
            "latent_parameters": roles.names(VariableRole.LATENT_PARAMETER),
            "requested_parameters": spec["requested_parameters"], "parameter_bounds": fam["parameter_bounds"],
            "fixed_protocol_conditions": roles.names(VariableRole.FIXED_PROTOCOL_CONDITION),
            "controlled_inputs": roles.names(VariableRole.CONTROLLED_INPUT),
            "observable_mapping": {"observable": spec["observable"], "measurement": roles.names(VariableRole.MEASUREMENT)},
            "nuisance": roles.names(VariableRole.NUISANCE_VARIABLE),
            "ocv_representation": fam["ocv"]["status"], "ocv": {k: v for k, v in fam["ocv"].items() if k != "knots_z_V"},
            "ocv_knot_count": len(fam["constants"].get("ocv_knots", fam["constants"].get("ocv_knots_soc", []))),
            "applicability_domain": {k: v for k, v in spec["applicability"].items()},
            "declared_families": fams, "role_table_digest": roles.digest}


def plan() -> dict[str, Any]:
    gen1_bad = gen1_reference.check(json.loads((ROOT / "docs" / "discovery" / "mind_gen1_reference.json").read_bytes()))
    if gen1_bad:
        raise SystemExit(f"GEN1 reference is not intact: {gen1_bad[:5]}")
    problems = load_pack(PACK)
    elig = json.loads((VAULT / "ELIGIBILITY.json").read_bytes())
    census = json.loads((VAULT / "CENSUS.json").read_bytes())
    mut = json.loads((HERE / "MUTATION_REPORT_pre_run.json").read_bytes())
    pre = json.loads((HERE / "LEAKAGE_PRE_RUN.json").read_bytes())
    if mut["status"] != "PASS" or pre["status"] != "PASS":
        raise SystemExit("the pre-run mutation report or the pre-run leakage audit is not PASS")
    primary, bridge = elig["primary_problems"], elig["bridge_problems"]
    inst = instances(problems, primary, bridge)
    return {
        "schema": "forge.battery_rediscovery_v3.plan/1", "id": "battery_rediscovery_v3", "task": "BR-BATT-REDISC-04",
        "status": "DEVELOPMENT baseline of the sealed GEN1 Mind: not formal, not certification, not a discovery claim",
        "gen1": {"reference_record": "docs/discovery/mind_gen1_reference.json",
                 "reference_record_sha256": _sha(ROOT / "docs" / "discovery" / "mind_gen1_reference.json"),
                 "gen1_commit": gen1_reference.GEN1_COMMIT, "check": "INTACT",
                 "behaviour_change": "NONE: the candidate is benchmarks.battery_rediscovery_v2.candidate.run, imported "
                                     "unchanged and called with --pack CandidateBundle"},
        "census": {"record_sha256": _sha(VAULT / "CENSUS.json"), "counts": census["counts"],
                   "primary_units": sorted(r["unit"] for r in census["rows"] if r["primary_class"] == "ELIGIBLE_PRIMARY_V3"),
                   "screen": census["screen"]},
        "eligibility": {"record_sha256": _sha(VAULT / "ELIGIBILITY.json"), "primary_problems": primary,
                        "bridge_problems": bridge, "refused_problems": elig["refused_problems"],
                        "rules": "build_pack.py docstring (frozen with it); structural only, fixed before any fit"},
        "data": {"pack_manifest_sha256": _sha(PACK / "MANIFEST.json"),
                 "identity_map_sha256": _sha(VAULT / "IDENTITY_MAP.json"),
                 "pack_provenance_sha256": _sha(VAULT / "PACK_PROVENANCE.json"),
                 "extract_manifest_sha256": _sha(VAULT / "EXTRACT_MANIFEST.json"),
                 "splits": {pid: {"calibration": [t["id"] for t in spec["sets"]["calibration"]],
                                  **{f"{s}/{k}": [t["id"] for t in v] for s in ("within_unit_heldout", "cross_unit_heldout")
                                     for k, v in (spec["sets"].get(s) or {}).items()}} for pid, spec in problems.items()}},
        "instances": inst,
        "instance_counts": {"primary": len(inst["primary"]), "primary_heldout": sum(r["heldout"] for r in inst["primary"]),
                            "bridge": len(inst["bridge"])},
        "model_space": {pid: model_space(spec) for pid, spec in problems.items()},
        "model_space_rule": "the candidate-visible model vocabulary is exactly each problem's declared family and declared "
                            "rival; no model is added after the run",
        "uncertainty_inputs": {pid: spec["measurement_noise"] for pid, spec in problems.items()},
        "structural_assessability": {pid: v2freeze.structural_assessability(spec) for pid, spec in problems.items()},
        "arms": {"compared": list(arms.ARMS), "reference_only": list(arms.REFERENCE_ARMS),
                 "definition": "benchmarks/battery_rediscovery_v2/candidate/arms.py (GEN1, unchanged)",
                 "identical_inputs": "every arm reads the same CandidateBundle problem; no arm reads another's output"},
        "seeds_and_budgets": {"seeds": list(common.SEEDS), "primary_seed": common.PRIMARY_SEED,
                              "mind_budget_queries_per_probe": 40, "mind_tolerance_ln": 0.05,
                              "repsem_starts": "2^p + 1 (engine constant)", "repsem_max_nfev": 200,
                              "v1_baseline_fit_starts": 8, "source": "v2 PLAN.json seeds_and_budgets (GEN1 constants)"},
        "truth_protocol": {
            "reference_a": {"module": "benchmarks/battery_rediscovery_v2/evaluator/reference.py",
                            "sha256": _sha(ROOT / "benchmarks" / "battery_rediscovery_v2" / "evaluator" / "reference.py"),
                            "shares_with_candidate": ["scipy.optimize.least_squares(method='trf')",
                                                      "engcore.hybrid_uq.identifiability.classify"]},
            "reference_b": {"module": f"{REL}/evaluator/reference_b.py", "sha256": _sha(HERE / "evaluator" / "reference_b.py"),
                            "shares_with_candidate": ["engcore.hybrid_uq.identifiability.classify (only when a noise is "
                                                      "declared)"], "doc": "module docstring (frozen with it)"},
            "agreement_rule": "evaluator/truth.py docstring: equal truths decide, any disagreement is UNSCORED "
                              "(REFERENCE_DISAGREEMENT)",
            "computed": "only after the seal AND the sandboxed replay are committed (truth.verify_seal refuses otherwise); "
                        "launch.py refuses to run the candidate once a TruthBundle exists",
            "per_axis_basis": {"MODEL_ADEQUACY": "A and B agree on calibration residuals at their own optima (B independent)",
                               "IDENTIFIABILITY": "structural (no declared noise) or near-structural/ambiguity (B "
                                                  "independent); a classifier-decided truth is IMPLEMENTATION_CORRELATED",
                               "WITHIN_CELL_GENERALIZATION": "direct held-out measurement criterion: held-out voltages "
                                                             "against each reference's prediction (B independent)",
                               "CROSS_CELL_TRANSFER": "as within, on the partner cell",
                               "MODEL_DISCREPANCY": "structural when no noise is declared; else bound from each "
                                                    "reference's own covariance"}},
        "degeneracy_diagnostics": {"module": f"{REL}/evaluator/diagnostics.py", "thresholds": diagnostics.THRESHOLDS,
                                   "dimensions": ["FIT_OK", "PARAMETER_DEGENERACY", "IDENTIFIABILITY_LIMIT",
                                                  "MODEL_DISCREPANCY"],
                                   "rule": "recorded per problem, never collapsed into a score and never changing a truth; "
                                           "candidate SUPPORTED answers on degenerate fits are reported"},
        "scoring": {"module": "benchmarks/battery_rediscovery_v2/evaluator/score.py (outcome table, GEN1-era)",
                    "instances": "PLAN.instances.primary only; the bridge is reported separately"},
        "statistics": {"module": f"{REL}/evaluator/stats.py", "interval": "Wilson score 95 %",
                       "paired": "exact two-sided sign test on discordant pairs vs OLD_MIND and vs CAREFUL_BASELINE"},
        "hypotheses": {"H1": "REPRESENTATION_PLUS_ROLES reduces FALSE_REFUSE relative to OLD_MIND without a material "
                             "increase in FALSE_SUPPORT",
                       "H2": "REPRESENTATION_PLUS_ROLES outperforms both single-layer arms on decided real-data instances",
                       "H3": "the combined arm retains useful held-out real-data performance across more than the v2 set",
                       "H4": "the apparent Gen1 improvement is robust to any single decided instance",
                       "not_preregistered_as_true": True, "operationalisation": "evaluator/conclusion.py docstring",
                       "thresholds": cr.THRESHOLDS},
        "conclusion_rule": {"module": f"{REL}/evaluator/conclusion.py", "verdicts": list(cr.VERDICTS),
                            "amendments": "none: a post-seal defect invalidates v3 and requires v4"},
        "leakage": {"firewall": f"{leakage.SCANNER_ID}@{leakage.SCANNER_VERSION}",
                    "scanner_sha256": _sha(HERE / "leakage.py"), "numeric_engine": leakage.NUMERIC_ENGINE,
                    "mutation_report_pre_run_sha256": _sha(HERE / "MUTATION_REPORT_pre_run.json"),
                    "mutation_pre_run": {k: mut[k] for k in ("status", "leak_mutations", "leaks_caught", "benign_controls",
                                                             "benign_triggered", "unmutated_carriers_clean")},
                    "runtime_negative_controls": [{"name": c["protected"], "expected": c["expected"], "caught": c["caught"]}
                                                  for c in mut["runtime_cases"]],
                    "pre_run_static_audit_sha256": _sha(HERE / "LEAKAGE_PRE_RUN.json"),
                    "pre_run_static_audit": pre["status"],
                    "protected_values": len(mutation.protected_values())},
        "process_blindness": [
            "CandidateBundle/ (candidate-visible), EvaluatorVault/ (identities, provenance, census, eligibility) and "
            "TruthBundle/ (written only by the evaluation) are separate directories; the runtime audit forbids the vault, "
            "the truth bundle, the v2 pack and every v0/v1/v2 results/evaluator directory",
            "order: freeze commit -> sandboxed candidate run (once) -> seal commit -> sandboxed replay -> post-seal mutation "
            "-> replay commit -> evaluation (truth computed here for the first time)",
            "launch.py refuses to execute the candidate if any TruthBundle file exists; truth.py refuses before the seal and "
            "the replay are committed",
            "no process in this session has computed a v3 reference fit on real data before the seal (dry runs use the "
            "synthetic pack only)"],
        "candidate_visible": ["CandidateBundle/", *sorted(_rel(p) for p in leakage.candidate_code_files()),
                              *sorted(_rel(p) for p in leakage.REPSEM_BENCH_FILES), "src/engcore/ (platform)"],
        "threats_to_validity": [
            "the developer is NOT blind to history: v0/v1/v2 answers and truths, the repsem gap map, the LG HG2 and NASA "
            "studies' results, the Kirkaldy cross-cell result for cells D/E and the BIG14 fade result were in the "
            "evaluator's context; units with a known 1RC/voltage outcome are SECONDARY or excluded, never primary",
            "the eligibility rules and decimation were written with knowledge of the files' protocol structure (segment "
            "durations, sampling, charge termination), never of a fit",
            "bars, bounds and scope margins are inherited verbatim from v1/v2 (pulse class 15/30 mV, aging-archive class "
            "50/90 mV); the GITT pulses are 288 s, much longer than the 10 s pulses the pulse class was set for",
            "the voltage uncertainty is UNKNOWN for every primary problem: identifiability and discrepancy can be decided "
            "only structurally, so those axes are mainly refusal tests",
            "the measured OCV comes from the calibration cell's own relaxed rests: held-out windows lie between knots "
            "(linear interpolation over ~8 % charge state), cross-cell windows use the calibration cell's OCV",
            "RPT0 and the latest RPT of one cell are two problems on the same cell; cross-cell windows of one problem are "
            "the partner's within-cell windows of another: instances are not all independent",
            "reference B shares the question semantics (bars, margins, domain rule) with reference A and with repsem; "
            "agreement shows implementation independence, not that the semantics are right",
            "the 4 C cell B0051 passes the charge-termination screen at 30.0 mA, the edge of the declared band"],
        "expected_outputs": expected_outputs(problems),
        "frozen_files": frozen_digests(),
    }


def expected_outputs(problems: dict[str, Any]) -> list[str]:
    pids = sorted(problems)
    return ([f"results/candidate/{a}__{p}.json" for a in arms.ALL_ARMS for p in pids]
            + [f"results/candidate/OLD_MIND_TRACES__{p}.json" for p in pids]
            + ["results/candidate/TIMINGS.json", "results/ACCESS_LOG.json", "results/LEAKAGE_PRE_SEAL.json",
               "results/SEAL.json", "results/replay/REPLAY.json", "results/ACCESS_LOG_REPLAY.json",
               "MUTATION_REPORT_post_seal.json", "results/LEAKAGE_POST_SEAL.json", "TruthBundle/TRUTH.json",
               "results/EVALUATION.json", "results/EVALUATION.md"])


def pre_run_audit() -> int:
    rep = leakage.audit(mutation.protected_values(), phase="pre_run")
    write_json(HERE / "LEAKAGE_PRE_RUN.json", rep)
    print("pre-run static audit", rep["status"])
    return 0 if rep["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--pre-run-audit":
        return pre_run_audit()
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
