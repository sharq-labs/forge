"""Seal FORGE Mind Generation 1 as a reference (BR-BATT-REDISC-04, Part A).

    python -m benchmarks.battery_rediscovery_v3.gen1_reference --write   # docs/discovery/mind_gen1_reference.json
    python -m benchmarks.battery_rediscovery_v3.gen1_reference --check   # exit 1 if any bound file differs

Every identity is read from git objects at ``GEN1_COMMIT`` (the battery_rediscovery_v2 head), never from the working
tree, so the record is reproducible from history alone.  ``--check`` then requires the working tree to hold exactly those
bytes for every bound file: v3 runs the GEN1 code only if this check passes.  Nothing here rewrites a v0, v1 or v2 file.

Bound per file: the git blob id and the sha256 of the committed bytes.  Bound per component directory: the git tree id.
Benchmark records (PLAN, SEAL, TRUTH, EVALUATION) are bound by the sha256 of their committed bytes, and their verdicts
are copied verbatim from the committed EVALUATION.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "docs" / "discovery" / "mind_gen1_reference.json"
SCHEMA = "forge.mind.gen1_reference/1"

GEN1_BRANCH = "research/battery-rediscovery-v2"
GEN1_COMMIT = "b8160e2101884b9f8018d4d3be5e1a80a8004b2d"

MIND_SOURCE_COMMIT = "e2b8037c881847a497c32f7ca56f82b95b493727"
REPSEM_TESTS_COMMIT = "db4397446774d789c92f7e0a20338f097d51e430"
REPSEM_REPAIR_COMMIT = "cac1c584d8056720cc2c83f63fe93d3b32a83151"
REPSEM_HEAD_COMMIT = "8603463936b3e4010ac2a541a7663976fae97703"

#: (component, role, directory or None, files)
COMPONENTS: tuple[tuple[str, str, str | None, tuple[str, ...]], ...] = (
    ("minimal_mind", "Minimal Mind source (engcore.mind.minimal), byte-exact from the Mind source commit",
     "src/engcore/mind/minimal",
     tuple(f"src/engcore/mind/minimal/{f}" for f in (
         "__init__.py", "competition.py", "experiments.py", "falsifier.py", "outcome_model.py", "problem.py",
         "runner.py", "stopping.py", "structures.py", "trace.py")) + ("src/engcore/mind/__init__.py",)),
    ("repsem", "representation + semantic-roles repair (engcore.mind.repsem): roles, scoped claims, named refusals, "
               "ScientificHypothesis, role-typed family binding, deterministic assessment and replay",
     "src/engcore/mind/repsem",
     tuple(f"src/engcore/mind/repsem/{f}" for f in (
         "__init__.py", "assess.py", "claims.py", "families.py", "hypothesis.py", "roles.py"))),
    ("platform_dependencies", "engcore modules the Gen1 judgments call directly (identifiability classifier and its "
                              "status vocabulary); not Gen1 code, bound so that a platform change is visible",
     None, ("src/engcore/hybrid_uq/identifiability.py", "src/engcore/inference/calibration.py")),
    ("v1_adapters_and_baselines", "battery_rediscovery_v1 candidate: the Minimal Mind adapter (mind_arm), the problem "
                                  "view, the 1RC model, and the CAREFUL / FIXED_FIT / ALWAYS_FIT / ALWAYS_REFUSE baselines",
     "benchmarks/battery_rediscovery_v1/candidate",
     tuple(f"benchmarks/battery_rediscovery_v1/candidate/{f}" for f in (
         "__init__.py", "common.py", "model.py", "baselines.py", "mind_arm.py")) + (
         "benchmarks/battery_rediscovery_v1/__init__.py",)),
    ("repsem_ablation_adapters", "the repsem ablation arms reused by v2 (role-posed load pool) and its fixtures",
     None, tuple(f"benchmarks/mind_repsem_v1/{f}" for f in ("__init__.py", "arms.py", "fixtures.py"))),
    ("v2_primary_adapters", "battery_rediscovery_v2 candidate package: the five compared arms and three reference arms, "
                            "the v1 problem view, the declared Thevenin families, pack loading, the answer vocabulary, "
                            "run and replay",
     "benchmarks/battery_rediscovery_v2/candidate",
     tuple(f"benchmarks/battery_rediscovery_v2/candidate/{f}" for f in (
         "__init__.py", "arms.py", "common.py", "families.py", "run.py", "views.py")) + (
         "benchmarks/__init__.py", "benchmarks/battery_rediscovery_v2/__init__.py")),
    ("leakage_firewall", "scanner v1 (numeric/text engines) and firewall v2 (candidate-material policy, provenance, "
                         "runtime audit) with their mutation suites and sandbox",
     None, ("benchmarks/battery_rediscovery_v1/leakage.py", "benchmarks/battery_rediscovery_v1/mutation.py",
            "benchmarks/battery_rediscovery_v2/leakage.py", "benchmarks/battery_rediscovery_v2/mutation.py",
            "benchmarks/battery_rediscovery_v2/sandbox_run.py")),
    ("v2_reference_protocol", "battery_rediscovery_v2 evaluator: reference truth protocol, scoring, conclusion rule",
     None, tuple(f"benchmarks/battery_rediscovery_v2/evaluator/{f}" for f in (
         "reference.py", "score.py", "conclusion.py", "truth.py"))),
)

BENCHMARKS: tuple[tuple[str, str, dict[str, str], tuple[str, ...]], ...] = (
    ("battery_rediscovery_v0", "BR-BATT-REDISC-01",
     {"freeze": "085d9a7c686d707edf70af29a8e9f6086791875d", "seal": "e1be5910081f531e19637697e3d103bc2953f12e",
      "evaluation": "986cc43ceb385bdf8138bbc3d41cc1d68e0b1f9e", "amendment_01": "dbf1794c6c0d2b0109f401773155e550ee57fd1f"},
     ("PLAN.json", "results/SEAL.json", "results/EVALUATION.json", "results/AMENDMENT_01.json",
      "results/EVALUATION_AMENDMENT_01.json")),
    ("battery_rediscovery_v1", "BR-BATT-REDISC-02",
     {"freeze": "53e6a6dbccab6fb697be994b12872140efc4a6c0", "seal": "c0613435f3af3d2979ffa5b4dfc26dfe3ac0f9a1",
      "evaluation": "d516e68185a700166c968de1bf0fa96930e27b93"},
     ("PLAN.json", "results/SEAL.json", "results/EVALUATION.json")),
    ("battery_rediscovery_v2", "BR-BATT-REDISC-03",
     {"freeze": "f62299863cc75ac367861ed8f28b10cc6b292e81", "seal": "ee3a6946e302c0fa56d55a1b3314e99f70aff65d",
      "replay": "6a75d816f7ed76ce31c89a00bcf80110dc716c2e", "evaluation": "625f5fea5867e4adf0c73df6c7544b37a1680b91"},
     ("PLAN.json", "results/SEAL.json", "results/replay/REPLAY.json", "results/TRUTH.json", "results/EVALUATION.json",
      "MUTATION_REPORT_pre_run.json", "MUTATION_REPORT_post_seal.json")),
    ("mind_repsem_v1", "BR-MIND-REPSEM-01",
     {"failing_first_tests": REPSEM_TESTS_COMMIT, "repair": REPSEM_REPAIR_COMMIT, "freeze_recheck": REPSEM_HEAD_COMMIT},
     ("results/ABLATION.json", "results/GAP_MAP.json")),
)

STATUS = {"GENERATION": 1, "IMPLEMENTED": "YES", "TESTED": "YES", "MEASURED": "YES", "REAL_DATA_SIGNAL": "YES",
          "SCIENTIFICALLY_VERIFIED": "NO", "CERTIFIED": "NO", "FORMAL": "NO"}

V2_STANDING = {
    "verdict_as_recorded": "REAL_DATA_IMPROVEMENT_CONFIRMED",
    "described_as": "REAL_DATA_IMPROVEMENT_CONFIRMED_BY_PREREGISTERED_V2_RULE",
    "EVIDENCE_STRENGTH": "LIMITED_SMALL_N",
    "limitations": [
        "only 5 decided-truth instances",
        "only 2 decided held-out instances",
        "one answer flip can materially change the result (H3 rests on 2 held-out instances)",
        "Q1's fitted 1RC is physically degenerate: R1 on its 1 ohm upper bound, tau ~5200 s",
        "Q2 reuses the LG HG2 pulse windows previously seen in v1 (re-split by SOC set point, not new data)",
        "the combined arm and the independent reference converged to effectively the same optimum (held-out rmse "
        "agrees to ~1e-11): this shows correct implementation on real data, not that the 1RC model is physically right",
        "the win is mostly structural: OLD_MIND and SEMANTIC_ROLES_ONLY cannot judge adequacy or discrepancy (v1 "
        "vocabulary) and REPRESENTATION_ONLY is refused at binding by design",
        "regression pack, SCIENTIFIC tier and certification were NOT RUN",
    ],
    "not_promoted": "v2 is not verified science and is not strengthened by this record",
}

CAPABILITY = {
    "what_gen1_is": "the Minimal Mind loop (engcore.mind.minimal, BR-MIND-01) plus the representation and semantic-roles "
                    "repair (engcore.mind.repsem, BR-MIND-REPSEM-01), driven by the battery_rediscovery_v2 adapters on "
                    "declared Thevenin 1RC / Rint families with a measured or a fitted piecewise-linear OCV",
    "questions": ["MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER",
                  "MODEL_DISCREPANCY"],
    "problem_schema": "forge.mind.repsem.problem/1",
    "pack_manifest_schema": "forge.battery_rediscovery_v2.pack_manifest/1",
    "arm_output_schema": "forge.battery_rediscovery_v2.arm_output/1",
    "compared_arms": ["OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                      "CAREFUL_BASELINE"],
    "reference_arms": ["FIXED_FIT", "ALWAYS_FIT", "ALWAYS_REFUSE"],
    "seeds": [0, 1, 2], "primary_seed": 0,
    "replay_format": {
        "arm_outputs": "content digest (sha256 of canonical JSON) of every (arm, problem) output, re-executed from the "
                       "pack (benchmarks.battery_rediscovery_v2.candidate.run.replay_all)",
        "repsem": "engcore.mind.repsem.replay: re-assess under the recorded roles and require byte identity (EXACT)",
        "minimal_mind_traces": "benchmarks.battery_rediscovery_v1.candidate.mind_arm.replay_traces over the "
                               "forge.mind.minimal.trace/1 hash chain (VERIFIED)",
    },
    "not_in_gen1": ["ScientificWorld", "ActionSpace", "HypothesisPortfolio", "SearchTree", "AttemptMemory",
                    "Ax/BoTorch", "PySINDy/PySR", "ModelCritic", "mechanism reasoning"],
}


def _git(*args: str, binary: bool = False) -> Any:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    return out if binary else out.decode().strip()


def _commit() -> str:
    full = _git("rev-parse", f"{GEN1_COMMIT}^{{commit}}")
    if full != GEN1_COMMIT:
        raise RuntimeError(f"GEN1 commit {GEN1_COMMIT} is not in this repository")
    return full


def _blob(commit: str, path: str) -> dict[str, str]:
    raw = _git("show", f"{commit}:{path}", binary=True)
    return {"git_blob": _git("rev-parse", f"{commit}:{path}"), "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": str(len(raw))}


def _vocabularies() -> dict[str, Any]:
    from benchmarks.battery_rediscovery_v2.candidate import common  # noqa: PLC0415
    from engcore.mind.repsem import CLAIM_TYPES, ClaimState, Disposition, RefusalReason, RoleSource, VariableRole  # noqa: PLC0415

    return {"dispositions": list(common.DISPOSITIONS), "non_committal": list(common.NON_COMMITTAL),
            "repsem_dispositions": [d.value for d in Disposition], "claim_states": [s.value for s in ClaimState],
            "claim_types": sorted(str(getattr(c, "value", c)) for c in CLAIM_TYPES),
            "refusal_reasons": [r.value for r in RefusalReason],
            "scientific_roles": [r.value for r in VariableRole], "role_sources": [s.value for s in RoleSource],
            "axes": list(common.AXES)}


def _verdict(raw: bytes) -> str | None:
    c = json.loads(raw).get("conclusion")
    if isinstance(c, dict):
        return c.get("verdict") or c.get("conclusion")
    return c


def build() -> dict[str, Any]:
    commit = _commit()
    comps = {}
    for name, role, directory, files in COMPONENTS:
        comps[name] = {"role": role, "git_tree": _git("rev-parse", f"{commit}:{directory}") if directory else None,
                       "directory": directory, "files": {p: _blob(commit, p) for p in files}}
    benches = {}
    for name, task, commits, records in BENCHMARKS:
        base = f"benchmarks/{name}"
        recs = {r: _blob(commit, f"{base}/{r}") for r in records}
        entry: dict[str, Any] = {"task": task, "commits": commits, "records": recs}
        plan_sha = (base + "/PLAN.sha256")
        if (ROOT / plan_sha).exists():
            entry["plan_sha256_file"] = _git("show", f"{commit}:{plan_sha}").split()[0]
        ev = f"{base}/results/EVALUATION.json"
        if "results/EVALUATION.json" in records:
            entry["verdict"] = _verdict(_git("show", f"{commit}:{ev}", binary=True))
        if "results/EVALUATION_AMENDMENT_01.json" in records:
            entry["verdict_amendment_01"] = _verdict(_git("show", f"{commit}:{base}/results/EVALUATION_AMENDMENT_01.json",
                                                          binary=True))
        if "results/SEAL.json" in records:
            seal = json.loads(_git("show", f"{commit}:{base}/results/SEAL.json", binary=True))
            entry["seal"] = {"status": seal.get("status"), "code_commit": seal.get("code_commit"),
                             "plan_sha256": seal.get("plan_sha256"),
                             "sealed_outputs": {k: v for k, v in sorted((seal.get("outputs") or {}).items())}}
        benches[name] = entry
    benches["battery_rediscovery_v0"]["standing"] = (
        "preregistered LEAKAGE_INVALIDATED (audit false positive); AMENDMENT_01 reading REPRESENTATION_BOTTLENECK is a "
        "disclosed post-seal amendment, not a clean confirmation")
    benches["battery_rediscovery_v1"]["standing"] = ("REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY; same data as v0, the "
                                                     "developer knew v0's answers: not blind, not an independent replication")
    benches["battery_rediscovery_v2"]["standing"] = V2_STANDING
    benches["mind_repsem_v1"]["standing"] = "READY_FOR_BATTERY_V2 on synthetic fixtures only (development evidence)"
    return {"schema": SCHEMA, "generation_status": dict(STATUS),
            "reference": {"branch": GEN1_BRANCH, "commit": commit, "tree": _git("rev-parse", f"{commit}^{{tree}}"),
                          "minimal_mind_source_commit": MIND_SOURCE_COMMIT,
                          "repsem_failing_first_tests_commit": REPSEM_TESTS_COMMIT,
                          "repsem_repair_commit": REPSEM_REPAIR_COMMIT, "repsem_head_commit": REPSEM_HEAD_COMMIT,
                          "pushed": False, "note": "local research branch; identities are git object ids, so they hold "
                                                   "for any clone that contains the commit"},
            "capability": CAPABILITY, "vocabularies": _vocabularies(), "components": comps, "benchmarks": benches}


def bound_files(record: dict[str, Any]) -> dict[str, str]:
    out = {p: e["sha256"] for c in record["components"].values() for p, e in c["files"].items()}
    return out


def check(record: dict[str, Any]) -> list[str]:
    bad = []
    for path, sha in sorted(bound_files(record).items()):
        p = ROOT / path
        if not p.exists():
            bad.append(f"missing: {path}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            bad.append(f"changed: {path}")
    if build() != record:
        bad.append("the record differs from a rebuild from git history")
    return bad


def write(record: dict[str, Any]) -> str:
    raw = (json.dumps(record, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        print(write(build()))
        return 0
    bad = check(json.loads(OUT_JSON.read_bytes()))
    for b in bad:
        print("GEN1:", b, file=sys.stderr)
    print("GEN1_REFERENCE", "INTACT" if not bad else "BROKEN")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
