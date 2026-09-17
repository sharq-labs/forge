"""Batch-27 guard mutations (I-22 part B, R-52: a ratio needs a ratio scale): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch27_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CO = "src/engcore/scientific/consensus.py"
OR = "src/engcore/scientific/oracles.py"
T = "tests/test_core_scientific_audit_batch27.py"

CANONICAL = "                common_unit.setdefault(str(name), canonical)\n"
FIRST_ROUTE = "                common_unit.setdefault(str(name), quantity.units)\n"

MUTATIONS = [
    # --- the compared unit is canonical, not the first route's -------------
    Mutation(
        "B27a", f"{CO}::CrossSolverConsensus.from_results", CANONICAL, FIRST_ROUTE,
        f"{T}::test_r52_the_verdict_does_not_depend_on_which_route_was_declared_first",
        "R-52 restored exactly, as CORE-018 left it: the first declared route that reports a name fixes "
        "the unit for every route, so 26.85 degC against 300.0000001 kelvin -- a ten-billionth of a "
        "kelvin apart -- disagrees one way round and agrees the other, against one tolerance"),
    Mutation(
        "B27b", f"{CO}::CrossSolverConsensus.from_results", CANONICAL, FIRST_ROUTE,
        f"{T}::test_r52_a_declared_floor_means_the_same_thing_in_either_order",
        "the same edit, seen by the OTHER half of the finding: a declared floor is a bare number read in "
        "the compared unit, so the same 1e-15 is worth 1e-15 A in one order and 1e-9 A in the other, and "
        "5e-10 A apart on a zero current becomes agreement"),
    Mutation(
        "B27c", f"{CO}::CrossSolverConsensus.from_results", CANONICAL, FIRST_ROUTE,
        f"{T}::test_r52_the_canonical_unit_is_the_kelvin_scale_and_the_pair_agrees",
        "and by the third: the pair that IS the same temperature stops being scored as agreeing at all "
        "when the Celsius route is declared first -- the too-strict direction, which costs a true "
        "agreement rather than inventing a false one"),
    # --- a relative difference needs a ratio scale -------------------------
    Mutation(
        "B27d", f"{CO}::CrossSolverConsensus.from_results",
        "                if not is_ratio_scale(canonical):\n",
        "                if False:\n",
        f"{T}::test_r52_a_comparison_on_an_affine_scale_is_refused_rather_than_taken",
        "the refusal goes. It is structurally unreachable under the canonical-unit rule -- a coherent SI "
        "base unit is always a ratio scale -- so the guard test substitutes the identity for the "
        "canonical map, which is what CORE-018 did, and a later common-unit rule that reintroduced an "
        "affine scale would otherwise be silent. That silence is the shape R-52 had"),
    # --- the operating point is compared on a ratio scale too --------------
    Mutation(
        "B27e", f"{OR}::_same_operating_point",
        "        canonical = base_unit(stated.units)\n"
        "        a, b = stated.magnitude_in(canonical), other.magnitude_in(canonical)\n",
        "        a, b = stated.magnitude_in(stated.units), other.magnitude_in(stated.units)\n",
        f"{T}::test_r52_an_operating_point_is_the_same_point_whatever_unit_states_it",
        "R-52's second site restored exactly: a 1e-9 RELATIVE tolerance applied on whatever scale the "
        "stated quantity used, so 0.02 degC and 0.020000001 degC -- four parts in a trillion apart on the "
        "kelvin scale -- are 'different operating points', and the CORE-009/CORE-014 binding that reads "
        "this predicate refuses a result for a difference no instrument could see"),
    Mutation(
        "B27f", f"{OR}::_same_operating_point",
        "        a, b = stated.magnitude_in(canonical), other.magnitude_in(canonical)\n",
        "        a, b = stated.magnitude_in(canonical), other.magnitude_in(stated.units)\n",
        f"{T}::test_r52_an_operating_point_is_the_same_point_whatever_unit_states_it",
        "only ONE side is canonicalised, which is worse than neither: the two magnitudes are then on "
        "different scales and the subtraction is meaningless rather than merely scale-dependent"),
    Mutation(
        "B27g", f"{CO}", "", "", f"{T}::x",
        "NOT MUTATED. `from_results`'s docstring and the floor's declaration comment are PROSE, and "
        "`mutation_guards._code_digest` ignores COMMENT and STRING tokens, so either edit reports "
        "MUTATION CHANGED NO CODE. What the docstring says is asserted directly instead, by "
        f"{T}::test_r52_the_docstring_no_longer_claims_each_value_is_read_in_its_own_unit -- a test, not "
        "a mutation, because the defect being guarded against is prose that contradicts the code.",
        expect="SURVIVED"),
]

_CHANGED_FILES = (CO, OR)


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
    live = [m for m in MUTATIONS if m.id != "B27g"]
    print(f"NOT MUTATED: B27g -- {MUTATIONS[-1].note}", flush=True)
    status = run(live, label="BATCH27", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH27_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 27 changed ---", flush=True)
    status |= run(existing, label="BATCH27_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH27_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
