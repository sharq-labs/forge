"""Offline checks only: never query worlds, replay Mind, tune or modify source."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys

E = Path(__file__).resolve().parent
ROOT = E.parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tools.forge_blindfold_demo import semantic


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = json.loads((E / "v3/plan.json").read_bytes())
    assert all(digest(ROOT / f) == h for f, h in plan["sources"].items())
    before = json.loads((E / "before-sources.json").read_bytes())
    assert all(digest(ROOT / f) == h for f, h in before.items())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert head == plan["head"]
    results = E / "v3/results"
    rows, diagnostics = [], []
    for i in range(12):
        folder = results / f"job-{i:02}"
        row = json.loads((folder / "run.json").read_bytes())
        assert row["status"] == "VALID" and row["tier_bound"] == "development"
        assert len(row["universes"]) == 6 and all(u["independent_agrees"] for u in row["universes"])
        payloads = [json.loads(p.read_bytes()) for p in (folder / "traces").glob("*.json")]
        # Imported helper only checks identity; it does not execute the Mind.
        from tools.forge_mind_diagnosis import join_traces
        assert len(join_traces(row, payloads)) == 6
        ds = json.loads((folder / "diagnostics.json").read_bytes())
        assert len(ds) == 6 and all(d["replay"]["status"] == "VERIFIED" for d in ds)
        rows.append(row)
        diagnostics.extend(ds)
    assert semantic(rows[0]) == semantic(json.loads((results / "control/run.json").read_bytes()))
    old = ROOT / "docs/work/evidence/mind_full_v03_readiness_2026_10_20_v1/v3/results/runs.jsonl"
    old_keys = {json.loads(line)["key_digest"] for line in old.read_text().splitlines()}
    keys = {r["key_digest"] for r in rows}
    assert len(keys) == 12 and not keys & old_keys
    receipt = json.loads((E / "v3/run-command.json").read_bytes())
    assert receipt["plan_sha256"] == digest(E / "v3/plan.json")
    children = json.loads((results / "receipts.json").read_bytes())
    assert len(children) == 13 and all(c["exit_code"] == 0 for c in children)
    assert digest(old) == json.loads((results / "offline-summary.json").read_bytes())["prior_run_records_sha256"]
    result = dict(status="OFFLINE_CHECKS_PASS_NOT_FORMAL", head=head,
                  original_outer_exit_code=receipt["exit_code"],
                  limitation="original postprocessing path failed; no campaign rerun",
                  existing_python_files_unchanged=len(before), source_pins_match=True,
                  new_world_sets=12, disjoint_from_prior_world_sets=len(old_keys),
                  primary_cards=72, stored_replay_reports=72, semantic_control="MATCH",
                  outcomes={kind: dict(collections.Counter(
                      d["universe"]["answer"] for d in diagnostics if d["universe"]["kind"] == kind))
                            for kind in sorted({d["universe"]["kind"] for d in diagnostics})})
    (E / "finalization.json").write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
