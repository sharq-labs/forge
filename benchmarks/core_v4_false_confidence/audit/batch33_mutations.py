"""Batch-33 guard mutations (I-07 part B, R-19: the spot-checked rows): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch33_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

GE = "src/engcore/hybrid_uq/_grid_evidence.py"
RO = "src/engcore/hybrid_uq/router.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch33.py"

MUTATIONS = [
    # --- the seed is the verifier's --------------------------------------
    Mutation(
        "B33a", f"{GE}::_spot_check_rows",
        "        hashlib.sha256(nonce if nonce is not None else secrets.token_bytes(32)).digest(), dtype=np.uint32))\n",
        "        hashlib.sha256(nonce or np.ascontiguousarray(ll, dtype=\"<f8\").tobytes()).digest(), dtype=np.uint32))\n",
        f"{T}::test_r19_the_draw_is_not_a_function_of_the_grids_own_bytes",
        "R-19's mechanism restored exactly: the seed becomes a digest of the grid's own log-likelihood, so a "
        "forger nudges one far-tail node by 1e-9 -- which moves no posterior weight and passes every other "
        "check -- until the draw misses the bulk. The audit measured TWO attempts"),
    Mutation(
        "B33b", f"{GE}::grid_is_this_evidence",
        "    rows = _spot_check_rows(grid, calibration, nonce=nonce)\n",
        "    rows = _spot_check_rows(grid, calibration, nonce=b\"\\x00\" * 32)\n",
        f"{T}::test_r19_the_draw_is_not_a_function_of_the_grids_own_bytes",
        "the nonce is pinned to a constant inside the binding, so every verifier in the world draws the same "
        "rows and the supplier only has to search once, ever. A hard-coded nonce is worse than the grid's own "
        "bytes: it never even changes. The reproduction was moved onto `grid_is_this_evidence` while running: "
        "it first called the row chooser directly, which cannot see a nonce pinned at the call site"),
    # --- the sample is weight-proportional and sized ---------------------
    Mutation(
        "B33c", f"{GE}",
        "SPOT_CHECK_WEIGHTED_ROWS = 17\n",
        "SPOT_CHECK_WEIGHTED_ROWS = 4\n",
        f"{T}::test_r19_the_sample_size_is_computed_from_a_stated_detection_probability",
        "the count goes back to four, which is the 0.75^4 = 32% escape the audit computed for a 25% tampered "
        "bulk EVEN WITHOUT grinding. The number is ceil(ln(1-0.99)/ln(1-0.25)) and a mutation that changes it "
        "changes the detection probability the rule claims"),
    Mutation(
        "B33d", f"{GE}::_spot_check_rows",
        "        rows.update(int(r) for r in stream.choice(pool, size=draw, replace=False, p=weight[pool] / total))\n",
        "        rows.update(int(r) for r in stream.choice(pool, size=draw, replace=False))\n",
        f"{T}::test_r19_the_draw_lands_where_the_posterior_weight_is",
        "the draw becomes UNIFORM over admissible nodes. On the audited 19881-node grid the posterior bulk is "
        "a small fraction of the box, so 17 uniform draws mostly land where there is no weight -- and "
        "tampering that moves a reported moment has to move weight, which is why weight is the measure. The "
        "reproduction was strengthened while running: it compared against the top 25% of node COUNT, which is "
        "a quarter of the box and which a uniform draw hits just as often. It now uses the nodes holding 95% "
        "of the posterior MASS, under a tenth of this grid"),
    Mutation(
        "B33e", f"{GE}::_spot_check_rows",
        "    refused = np.flatnonzero(~usable)\n    if refused.size:\n",
        "    refused = np.flatnonzero(~usable)\n    if False:\n",
        f"{T}::test_r19_an_inadmissible_node_the_model_admits_is_caught",
        "the inadmissible sample goes. Such a node carries ZERO posterior weight, so the weighted draw can "
        "never reach one -- and marking a quarter of the support refused deletes that mass from the posterior "
        "without touching a single likelihood, which is the half of the audited gap that defeats containment"),
    # --- every face --------------------------------------------------------
    Mutation(
        "B33f", f"{GE}::_spot_check_rows",
        "    if shape is not None and int(np.prod(shape)) == count:\n",
        "    if False:\n",
        f"{T}::test_r19_the_highest_node_of_every_face_is_checked",
        "the faces stop being checked. `grid_containment` is decided by the largest log-likelihood on each "
        "face, and a CONTAINED posterior has almost no weight there -- so those are precisely the nodes a "
        "weighted draw is least likely to reach and precisely the ones a supplier would lower"),
    # --- the rebuilt table gets the same rule -----------------------------
    Mutation(
        "B33g", f"{RO}::_require_table_agrees_with_forward",
        "        hashlib.sha256(nonce if nonce is not None else secrets.token_bytes(32)).digest(), dtype=np.uint32))\n",
        "        hashlib.sha256(nonce if nonce is not None else np.ascontiguousarray(table.values, dtype=\"<f8\").tobytes()).digest(),\n"
        "        dtype=np.uint32))\n",
        f"{T}::test_r19_the_rebuilt_table_check_no_longer_seeds_from_the_table",
        "the rebuilt-table check goes back to seeding from the table's own values, which is the sentence the "
        "audit spends on it: 'a rebuild table_builder can do the same'. Fixing one path and not the other "
        "leaves the attack on whichever one the caller happens to use. The reproduction was strengthened "
        "while running: it looked for one exact substring, and this mutation wraps the same digest of "
        "`table.values` in a `nonce if nonce is not None else ...` that does not contain it. It now asserts "
        "over the whole seed expression that the TABLE is not in it"),
    Mutation(
        "B33h", f"{RO}::_require_table_agrees_with_forward",
        "        rows.update(int(r) for r in stream.choice(pool, size=draw, replace=False, p=weight[pool] / total))\n",
        "        rows.update(int(r) for r in stream.choice(pool, size=draw, replace=False))\n",
        f"{T}::test_r19_an_honest_rebuild_still_routes",
        "EXPECTED SURVIVED, and the reason is the finding. The rebuild path's weighted draw has no forgery "
        "reproduction of its own in this repository: the audit demonstrated the attack on the SUPPLIED grid "
        "and asserted the rebuild's exposure in one sentence without a measurement. So the uniform draw is "
        "indistinguishable here, and the honest control is all that runs. Building that forgery needs a "
        "table_builder that answers with a sharpened model, which is a fixture this batch does not have -- "
        "recorded so the gap is declared rather than implied",
        expect="SURVIVED"),
]

_CHANGED_FILES = (GE, RO)


def _existing():
    out = []
    for identifier, spec, old, new, attribution in M.MUTATIONS:
        if spec.partition("::")[0] not in _CHANGED_FILES:
            continue
        files = [word for word in attribution.replace(",", " ").split() if word.startswith("tests/")]
        if not files:
            continue
        out.append(Mutation(identifier, spec, old, new, files[0], f"pinned: {attribution}"))
    return out


def main() -> int:
    scratch = scratch_from_environment()
    status = run(MUTATIONS, label="BATCH33", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH33_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 33 changed ---", flush=True)
    status |= run(existing, label="BATCH33_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH33_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
