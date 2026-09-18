"""Batch-57 guard mutations (I-23, R-62/R-74): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``. The guards here are one rule read in three
places, so the mutations are about what happens when that rule stops being one: a quantization that
is not applied, a sign that survives, and a comparison that keeps its own tolerance.

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch57_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

Q = "src/engcore/scientific/units/quantity.py"
MESH = "src/engcore/scientific/fields/mesh.py"
TR = "src/engcore/scientific/fields/transfer.py"
PA = "src/engcore/inference/parameters.py"
T = "tests/test_core_scientific_audit_batch57.py"

MUTATIONS = [
    Mutation(
        "B57a", f"{Q}::canonical_magnitude",
        "    return float(f\"{magnitude:.{digits - 1}e}\")\n",
        "    return magnitude\n",
        f"{T}::test_i23_one_rule_states_how_much_of_a_float_is_identity",
        "the quantization goes, so the rule returns the raw conversion again and 7 mm is not 0.7 cm: "
        "identity is back to whichever float the conversion happened to land on"),
    Mutation(
        "B57b", f"{Q}::canonical_magnitude",
        "    if magnitude == 0.0:\n",
        "    if False:\n",
        f"{T}::test_r74_a_negative_zero_bound_is_one_value_in_both_directions",
        "R-74's sign: `-0.0` keeps its sign through the rule, so one bound is two digests while "
        "`differences()` says there is no difference"),
    Mutation(
        "B57c", f"{MESH}::StructuredMesh._canonical",
        "            \"length_x\": repr(canonical_magnitude(self.length_x, CANONICAL_LENGTH)),\n",
        "            \"length_x\": repr(self.length_x.magnitude_in(CANONICAL_LENGTH)),\n",
        f"{T}::test_r62_the_same_rectangle_stated_in_two_units_is_one_support",
        "R-62 restored on the fingerprint: one extent is hashed from the raw conversion, so the same "
        "rectangle stated in two units is two supports and a field produced on one cannot be read on "
        "the other"),
    Mutation(
        "B57d", f"{TR}::_same_geometry",
        "        canonical_magnitude(getattr(left, name), CANONICAL_LENGTH)\n"
        "        == canonical_magnitude(getattr(right, name), CANONICAL_LENGTH)\n",
        "        abs(getattr(left, name).magnitude_in(CANONICAL_LENGTH)\n"
        "            - getattr(right, name).magnitude_in(CANONICAL_LENGTH))\n"
        "        <= 1e-12 * max(1.0, abs(getattr(left, name).magnitude_in(CANONICAL_LENGTH)))\n",
        f"{T}::test_r62_the_transfer_check_reads_geometry_the_way_the_fingerprint_does",
        "the audited tolerance comes back: absolute 1e-12 m below one metre, so two rectangles 5e-5 "
        "apart relatively are one geometry and a projection is offered for a difference no "
        "projection can close"),
    Mutation(
        "B57e", f"{PA}::ParameterIdentity._canonical",
        "            \"lower\": canonical_magnitude(self.bounds.lower, self.unit),\n",
        "            \"lower\": self.bounds.lower.magnitude_in(self.unit),\n",
        f"{T}::test_r74_a_bound_restated_in_another_unit_is_the_same_parameter",
        "R-74 restored on the parameter: the lower bound is read raw, so the same admissible range "
        "stated in millivolts is a different parameter identity"),
    Mutation(
        "B57f", f"{Q}::canonical_magnitude",
        "    if not math.isfinite(magnitude):\n",
        "    if True:\n",
        f"{T}::test_i23_one_rule_states_how_much_of_a_float_is_identity",
        "every magnitude is returned unquantized behind the infinity branch, which is the same defect "
        "as B57a arriving by the other door -- and is why the branch is written for infinities only"),
]

_CHANGED_FILES = (Q, MESH, TR, PA)


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
    status = run(MUTATIONS, label="BATCH57", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH57_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 57 changed ---", flush=True)
    status |= run(existing, label="BATCH57_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH57_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
