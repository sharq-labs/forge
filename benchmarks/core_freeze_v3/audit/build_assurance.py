"""Measure and assemble the Core Freeze V3 assurance record.

    python -X utf8 benchmarks/core_freeze_v3/audit/build_assurance.py suites
    python -X utf8 benchmarks/core_freeze_v3/audit/build_assurance.py formal --logs <shard0.log> <shard1.log> <shard2.log> <shard3.log>
    python benchmarks/core_freeze_v3/audit/build_assurance.py trust            (never under -X utf8)
    python -X utf8 benchmarks/core_freeze_v3/audit/build_assurance.py freeze --candidate <commit>

Every number in certification/core_freeze_v3_assurance.json is read from an evidence file committed beside
this script, and every evidence file is checked, not trusted:

* SUITES.json -- the suites the verifier requires, each run by this script on the recorded commit. On a
  recertification SOURCE commit the four certificate/freeze self-checks read the previous certificate by
  construction, so they are deselected exactly as the CI source gates deselect them
  (tools/certification/recertification_scope.CERTIFICATE_SELF_CHECKS) and run on the certificate child.
* FORMAL_SHARD_<i>.log -- the formal harness transcripts, normalised to LF before hashing (a Windows capture
  is CRLF and git stores LF, so a hash of the raw capture would never verify from a clone). Each is checked
  with tools.certification.mutation_population.log_problems against the canonical population's shard.
* TRUST_MUTATIONS.json -- the trust-hardening runner's own result, including its unmutated control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_freeze_v3"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SUITES = {
    "FAST": ["tests", "-n", "4", "-m", "not expensive"],
    "hybrid_uq_focused": ["tests/hybrid_uq", "tests/test_core_v2_compatibility.py"],
    "audit_regressions": None,  # every tests/**/test_audit_*.py, resolved at run time
    "api_snapshot_v1": ["tests/test_core_api_snapshot.py"],
    "api_snapshot_v2": ["tests/test_core_v2_api_snapshot.py"],
    "freeze_manifest_v1": ["tests/test_core_freeze_manifest.py", "tests/test_core_freeze_policy.py"],
    "freeze_manifest_v3": ["tests/test_core_freeze_v3_manifest.py", "tests/test_core_freeze_v2_manifest.py"],
    "certificate": ["tests/test_core_certificate.py", "tests/test_recertification_scope.py", "tests/test_hardening_assurance.py",
                    "tests/test_certification_mutation_population.py", "tests/test_certification_control_plane.py",
                    "tests/test_mutation_harness.py", "tests/test_trust_mutation_attribution.py"],
}


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write_json(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def run_suites(basetemp: str) -> None:
    from tools.certification.recertification_scope import CERTIFICATE_SELF_CHECKS

    commit = git("rev-parse", "HEAD")
    results = {}
    for name, args in SUITES.items():
        if args is None:
            args = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.glob("tests/**/test_audit_*.py"))
        # pytest creates --basetemp with parents=False, so its parent must exist before the first
        # test asks for tmp_path (the same trap that made the mutation harness's control red).
        pathlib.Path(basetemp).mkdir(parents=True, exist_ok=True)
        deselect = [item for check in CERTIFICATE_SELF_CHECKS for item in ("--deselect", check)]
        cmd = [sys.executable, "-X", "utf8", "-m", "pytest", *args, "-q", "-p", "no:cacheprovider",
               f"--basetemp={basetemp}/{name}", *deselect]
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [line for line in done.stdout.splitlines() if " passed" in line or " failed" in line or " error" in line]
        summary = lines[-1].strip("= ").strip() if lines else "?"
        results[name] = {"exit_code": done.returncode, "green": done.returncode == 0, "summary_line": summary,
                         "deselected_certificate_child_self_checks": list(CERTIFICATE_SELF_CHECKS)}
        print(f"{name:22} exit {done.returncode}  {summary}", flush=True)
    write_json(ROUND / "SUITES.json", {"commit": commit, "suites": results})


def record_formal(logs: list[str], shard_commits: list[str]) -> None:
    from tools.certification import mutation_population as formal

    population = formal.canonical_population(ROOT)
    shards = []
    for index, source in enumerate(logs):
        text = pathlib.Path(source).read_bytes().decode("utf-8").replace("\r\n", "\n")
        problems = formal.log_problems(text, population, population.shard(index))
        if problems:
            raise SystemExit(f"shard {index} transcript does not support the claim: {problems}")
        target = ROUND / f"FORMAL_SHARD_{index}.log"
        target.write_bytes(text.encode("utf-8"))
        measured = git("rev-parse", shard_commits[index]) if shard_commits else git("rev-parse", "HEAD")
        shards.append({"index": index, "selected": len(population.shard(index)), "log": target.name,
                       "log_sha256": sha256(text.encode("utf-8")), "measured_at": measured})
    # A shard re-run after a change to ITS mutations only is legitimate evidence only if nothing a
    # mutation or its suites read moved between the commits the shards were measured at.
    if shard_commits and len(set(shard_commits)) > 1:
        from tools.certification import mutation_population as _mp  # noqa: F401
        import runpy
        targets = list(runpy.run_path(str(ROOT / "tests" / "mutation_guards.py"), run_name="probe")["TARGETS"])
        first = shard_commits[0]
        for other in shard_commits[1:]:
            moved = git("diff", "--name-only", first, other, "--", "src", *targets)
            if moved:
                raise SystemExit(f"shards measured at {first} and {other} saw different source or suites: {moved}")
    write_json(ROUND / "FORMAL_MUTATIONS.json", {
        "commit": git("rev-parse", "HEAD"), "population_sha256": population.sha256, "population": population.count,
        "shard_count": len(logs), "killed": sum(s["selected"] for s in shards), "control": "GREEN", "shards": shards})


def record_trust() -> None:
    result = ROUND / "TRUST_MUTATIONS.json"
    done = subprocess.run([sys.executable, "benchmarks/trust_hardening/audit/mutations.py", "--json", str(result)],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(done.stdout[-3000:])
    if done.returncode != 0:
        raise SystemExit("the trust-hardening population did not pass with a green control")
    payload = json.loads(result.read_bytes())
    payload["commit"] = git("rev-parse", "HEAD")
    payload["control"] = "GREEN"
    write_json(result, payload)


def freeze(candidate: str) -> None:
    from tools.certification import core_freeze_v3 as v3

    manifest = (ROOT / v3.MANIFEST_PATH).read_bytes()
    suites = json.loads((ROUND / "SUITES.json").read_bytes())
    formal = json.loads((ROUND / "FORMAL_MUTATIONS.json").read_bytes())
    trust = json.loads((ROUND / "TRUST_MUTATIONS.json").read_bytes())
    for shard in formal["shards"]:
        if sha256((ROUND / shard["log"]).read_bytes()) != shard["log_sha256"]:
            raise SystemExit(f"{shard['log']} does not match its recorded digest")
    missing = [s for s in v3.REQUIRED_SUITES if s not in suites["suites"]]
    if missing:
        raise SystemExit(f"SUITES.json lacks required suites {missing}")
    record = {
        "schema": v3.ASSURANCE_SCHEMA, "tag": v3.TAG, "candidate_commit": candidate, "manifest_sha256": sha256(manifest),
        "suites": suites["suites"], "suites_commit": suites["commit"],
        "mutations": {
            "formal": {k: formal[k] for k in ("control", "population", "population_sha256", "killed", "shard_count", "commit")},
            "trust": {"control": trust["control"], "population": trust["population"], "killed": trust["killed"],
                      "survived": trust["survived"], "invalid": trust["invalid"], "commit": trust["commit"]},
        },
        "evidence": {path.name: sha256(path.read_bytes()) for path in sorted(ROUND.glob("*"))
                     if path.is_file() and path.suffix in (".json", ".log")},
        "audit": "docs/audits/MAIN_AUDIT_2026-09-15.md",
    }
    write_json(ROOT / v3.ASSURANCE_PATH, record)
    print("wrote", v3.ASSURANCE_PATH)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["suites", "formal", "trust", "freeze"])
    ap.add_argument("--logs", nargs="*")
    ap.add_argument("--shard-commits", nargs="*",
                    help="the commit each shard transcript was measured at, in shard order")
    ap.add_argument("--candidate")
    ap.add_argument("--basetemp", default="D:/fbt-v3")
    args = ap.parse_args()
    if args.which == "suites":
        run_suites(args.basetemp)
    elif args.which == "formal":
        record_formal(args.logs or [], args.shard_commits or [])
    elif args.which == "trust":
        record_trust()
    else:
        freeze(git("rev-parse", args.candidate))


if __name__ == "__main__":
    main()
