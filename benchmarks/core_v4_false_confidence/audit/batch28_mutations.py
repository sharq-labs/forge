"""Batch-28 guard mutations (I-22 part C, R-57: corners compared on one scale): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch28_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CD = "src/engcore/scientific/fields/conditions.py"
T = "tests/test_core_scientific_audit_batch28.py"

MUTATIONS = [
    Mutation(
        "B28a", f"{CD}::_require_corners_agree",
        "        return float(\n"
        "            Quantity(law.evaluate(x=x, y=y), law.unit).magnitude_in(canonical)\n"
        "        )\n",
        "        return float(law.evaluate(x=x, y=y))\n",
        f"{T}::test_r57_a_273_kelvin_corner_conflict_is_refused",
        "R-57 restored exactly: `evaluate` returns a magnitude in the LAW's own unit and the guard "
        "subtracts two numbers on two scales, so 300 kelvin meeting 300 degC -- 573.15 K, a 273.15 K "
        "contradiction at two corners -- is accepted, and the assembly then pins the corner to whichever "
        "edge it writes last"),
    Mutation(
        "B28b", f"{CD}::_require_corners_agree",
        "        return float(\n"
        "            Quantity(law.evaluate(x=x, y=y), law.unit).magnitude_in(canonical)\n"
        "        )\n",
        "        return float(law.evaluate(x=x, y=y))\n",
        f"{T}::test_r57_two_edges_that_agree_physically_are_accepted_however_they_are_spelled",
        "the same edit, seen by the other direction of the same defect: 300 kelvin meeting 26.85 degC is "
        "ONE temperature and was refused. A guard that refuses a correct declaration teaches a caller to "
        "restate it until the guard stops complaining, which is how a guard becomes a formality"),
    Mutation(
        "B28c", f"{CD}::_require_corners_agree",
        "    canonical = base_unit(definition.unit)\n",
        "    canonical = definition.unit\n",
        f"{T}::test_r57_the_same_physical_pair_gets_the_same_verdict_in_either_declaration",
        "the conversion survives but the target is the FIELD's declared unit, so a field declared in degC "
        "has a RELATIVE tolerance taken on a scale whose zero is a convention: 1000 degC against "
        "1000.00000115 degC is refused while the same physical pair in kelvin is accepted. The audited "
        "defect was two scales; this is the weaker version of the fix, and it is still wrong"),
    Mutation(
        "B28d", f"{CD}::_require_corners_agree",
        '        if law.unit == canonical:\n            return ""\n',
        '        if True:\n            return ""\n',
        f"{T}::test_r57_the_refusal_does_not_label_two_scales_with_one_unit",
        "the refusal stops saying what the caller actually wrote, so a reader of "
        "`prescribe 300 and 573.15 kelvin` goes looking for a 573.15 nobody typed. The audited message "
        "had the mirror fault -- it printed both numbers as written and labelled them with one unit"),
    Mutation(
        "B28e", f"{CD}::_require_corners_agree",
        "            tolerance = CORNER_AGREEMENT_REL_TOL * max(\n                1.0, abs(reference), abs(value)\n            )\n",
        "            tolerance = CORNER_AGREEMENT_REL_TOL * max(\n                1.0, abs(reference), abs(value)\n            ) * 1e9\n",
        f"{T}::test_r57_the_existing_cases_still_do_what_they_did",
        "the tolerance is widened by the nine orders this batch did NOT change, which is the thing a "
        "reader of this batch should most want to be sure of: a one-kelvin corner conflict is still a "
        "refusal and the tolerance is still 1e-9"),
]

_CHANGED_FILES = (CD,)


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
    status = run(MUTATIONS, label="BATCH28", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH28_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the file batch 28 changed ---", flush=True)
    status |= run(existing, label="BATCH28_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH28_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
