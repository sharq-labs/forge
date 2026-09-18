"""Batch-53 guard mutations (I-25 part B; R-63, R-73): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch53_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

X = "src/engcore/scientific/fields/transfer.py"
O = "src/engcore/inference/field_observation.py"
T = "tests/test_core_scientific_audit_batch53.py"

MUTATIONS = [
    Mutation(
        "B53a", f"{X}::FieldTransferContract._require_the_verdict_follows_from_the_records",
        "        if self._STRENGTH[self.verdict] > self._STRENGTH[ceiling]:\n",
        "        if False:\n",
        f"{T}::test_r63_a_component_mismatch_cannot_read_back_as_compatible",
        "finding 77 restored: a payload computed as REFUSED for 1 component against 3 reads back as "
        "COMPATIBLE with may_cross_directly True, which is the whole of what this record exists to be"),
    Mutation(
        "B53b", f"{X}::FieldTransferContract._require_the_verdict_follows_from_the_records",
        "        elif self.producer_fingerprint != self.consumer_fingerprint:\n",
        "        elif False:\n",
        f"{T}::test_r63_two_different_supports_cannot_read_back_as_compatible",
        "invented fingerprints stop being checked against the verdict, so two supports that are not one "
        "support carry a COMPATIBLE crossing"),
    Mutation(
        "B53c", f"{X}::FieldTransferContract._require_the_verdict_follows_from_the_records",
        "        elif self.producer.location is not self.consumer.location:\n",
        "        elif False:\n",
        f"{T}::test_r63_two_locations_cannot_read_back_as_compatible",
        "node values and cell values on one geometry become directly crossable, where moving between "
        "them is an interpolation somebody has to declare"),
    Mutation(
        "B53d", f"{X}::FieldTransferContract._require_the_verdict_follows_from_the_records",
        "        elif self.producer.unit != self.consumer.unit:\n",
        "        elif False:\n",
        f"{T}::test_r63_two_units_cannot_read_back_as_compatible",
        "two units of one dimension become COMPATIBLE, which says the conversion is not needed"),
    Mutation(
        "B53e", f"{O}::FieldObservationOperator._require_the_probe_is_on_the_support",
        "            if target < low - allowance or target > high + allowance:\n",
        "            if False:\n",
        f"{T}::test_r73_a_probe_outside_the_support_is_refused",
        "finding 104's probe claim restored: a probe declared 2 m and -5 m from a 10 mm plate silently "
        "reads a corner node, and the observation enters a calibration as a value at a different place"),
    Mutation(
        "B53f", f"{O}::FieldObservationOperator._require_the_region_is_the_declared_one",
        "        if region.mesh_id != self.region_mesh_id or edge != self.region_edge:\n",
        "        if False:\n",
        f"{T}::test_r73_a_region_mean_refuses_a_region_whose_content_is_not_the_declared_one",
        "finding 104's region claim restored: the same operator and digest read the left edge or the "
        "right edge depending on which region object is supplied"),
    Mutation(
        "B53g", f"{O}::FieldObservationOperator._require_the_region_is_the_declared_one",
        "        if not self.region_mesh_id or not self.region_edge:\n",
        "        if False:\n",
        "tests/inference/test_field_observation_spike.py::test_a_region_mean_refuses_a_region_it_did_not_name",
        "expect=SURVIVED, and recorded as such: an operator that declares no region content is refused "
        "the region it cannot check, and removing that refusal leaves the ID check standing -- which is "
        "what the in-tree test asserts. The rule it protects is the audited one and is killed by B53f; "
        "this edit says what the second branch does NOT protect on its own",
        expect="SURVIVED"),
    Mutation(
        "B53h", f"{O}::FieldObservationOperator._values_of_the_field_it_names",
        "        if dimensionality(unit) != dimensionality(self.unit):\n",
        "        if False:\n",
        f"{T}::test_r73_a_typed_field_of_the_named_id_in_another_dimension_is_refused",
        "a velocity field read through a temperature operator comes back as a Quantity in kelvin, which "
        "is the unit on this record being an assertion about an array nobody checked. REPOINTED while "
        "running these mutations: the audited field differs in BOTH its id and its unit, so the id rule "
        "answers it too; the case only this rule sees carries the declared id in another dimension"),
    Mutation(
        "B53i", f"{O}::FieldObservationOperator._values_of_the_field_it_names",
        "        if field_id != self.field_id:\n",
        "        if False:\n",
        f"{T}::test_r73_a_typed_field_of_another_id_in_the_named_unit_is_refused",
        "and the field id likewise: any typed field is read under this operator's declared name. "
        "REPOINTED for the same reason as B53h; the case only this rule sees carries another id in the "
        "declared unit"),
]

_CHANGED_FILES = (X, O)


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
    status = run(MUTATIONS, label="BATCH53", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH53_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 53 changed ---", flush=True)
    status |= run(existing, label="BATCH53_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH53_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
