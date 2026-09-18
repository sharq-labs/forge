"""Batch-16 guard mutations (I-24, boundary completeness per edge): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch16_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CO = "src/engcore/scientific/fields/conditions.py"
C2 = "src/engcore/domains/thermal_models/conduction2d.py"
T = "tests/test_core_scientific_audit_batch16.py"

MUTATIONS = [
    Mutation(
        "B16a", f"{CO}::require_complete_boundary",
        "        if edge in seen:\n",
        "        if False:\n",
        f"{T}::test_r56_two_conditions_on_one_edge_under_two_region_ids_are_refused",
        "R-56, the audited case: two conditions on one edge under two region ids are accepted again, and "
        "one of them is imposed with nothing in the record to say which"),
    Mutation(
        "B16b", f"{CO}::require_complete_boundary",
        "        edge = BoundaryEdge(region.edge)\n",
        "        edge = condition.region_id\n",
        f"{T}::test_r56_a_dirichlet_and_a_neumann_on_one_edge_are_refused",
        "R-56 exactly: the uniqueness check goes back to keying by the NAME a caller chose, so two names "
        "for one edge read as two edges"),
    Mutation(
        "B16c", f"{CO}::require_complete_boundary",
        "    missing = [edge.value for edge in BoundaryEdge if edge not in seen]\n",
        "    missing = [r.edge.value for r in by_id.values() if r.edge not in seen]\n",
        f"{T}::test_r56_a_region_set_that_misses_an_edge_is_not_a_complete_boundary",
        "R-56: completeness goes back to measuring the caller's own region list against itself, so one "
        "region and one condition read as a complete boundary"),
    Mutation(
        "B16d", f"{CO}::require_complete_boundary",
        "    if missing:\n",
        "    if False:\n",
        f"{T}::test_r56_the_refusal_names_the_edges_that_have_no_condition",
        "an unconditioned edge stops being refused at all, which is the under-determined problem a solver "
        "answers anyway"),
    Mutation(
        "B16e", f"{C2}::SteadyConductionProblem.edges",
        "            if edge in chosen:\n",
        "            if False:\n",
        f"{T}::test_r56_the_problems_edge_map_refuses_a_collision_instead_of_choosing_a_winner",
        "R-56: the consumer goes back to last-wins, which is where the silent winner was actually chosen"),
    Mutation(
        "B16f", f"{CO}::require_complete_boundary",
        "        seen[edge] = (condition.name, condition.region_id)\n",
        "        pass\n",
        f"{T}::test_r56_a_boundary_conditioned_once_per_edge_is_still_complete",
        "nothing is recorded as seen, so a complete boundary reads as an empty one -- the control that the "
        "completeness check is not vacuously satisfied"),
]

_CHANGED_FILES = (CO, C2)


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
    status = run(MUTATIONS, label="BATCH16", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH16_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 16 changed ---", flush=True)
    status |= run(existing, label="BATCH16_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH16_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
