"""Batch-45 guard mutations (I-28 part B, R-71's finding 102): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch45_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

G = "src/engcore/inference/grid.py"
U = "src/engcore/uq/admission.py"
T = "tests/test_core_scientific_audit_batch45.py"

MUTATIONS = [
    Mutation(
        "B45a", f"{G}::AdmittedForwardTable.__post_init__",
        "                if parse_admission_ref(ref) is None:\n",
        "                if False:\n",
        f"{T}::test_r71_a_table_whose_admission_records_are_free_strings_is_refused",
        "finding 102 restored: any non-empty string is an admission record again, so a table of fabricated "
        "values with refs ('forged', 'x') produces a posterior -- the audited case exactly"),
    Mutation(
        "B45b", f"{G}::parse_admission_ref",
        "    if parts[0].strip() not in ADMISSION_ROUTES:\n",
        "    if False:\n",
        f"{T}::test_r71_a_record_naming_no_declared_route_is_refused",
        "a record may name a route the admission boundary does not have, which is what makes the route "
        "unreadable: the two routes are not equally strong evidence and a consumer gates on which one"),
    Mutation(
        "B45c", f"{G}::parse_admission_ref",
        "    if any(not part.strip() for part in parts):\n",
        "    if False:\n",
        f"{T}::test_r71_a_record_with_an_empty_part_is_refused",
        "a record with a blank verification or binding reference passes, so the form is satisfied by "
        "punctuation"),
    Mutation(
        "B45d", f"{G}::parse_admission_ref",
        "    if len(parts) != len(_ADMISSION_REF_PARTS):\n",
        "    if False:\n",
        f"{T}::test_r71_a_record_with_the_wrong_number_of_parts_is_refused",
        "REPOINTED while running these mutations: the audited 'forged' ref is refused by the route check "
        "as well, so the count is only visible on a record whose route IS declared and whose remaining "
        "parts are missing or multiplied -- a half-written record, which is what a truncated cache or a "
        "hand-assembled string produces"),
    Mutation(
        "B45e", f"{G}::AdmittedForwardTable.select_observations",
        "        if self.observation_units:\n",
        "        if False:\n",
        f"{T}::test_r71_reusing_a_table_with_another_units_set_is_refused",
        "finding 102's second half restored: the keys match and the units are never checked, so 1500 "
        "milliohm compared against a table in ohm gives a MAP of 1.5 -- a factor of 1000 nobody declared"),
    Mutation(
        "B45f", f"{G}::AdmittedForwardTable.select_observations",
        "            if declared != supplied:\n",
        "            if False:\n",
        f"{T}::test_r71_reusing_a_table_with_another_units_set_is_refused",
        "the units are read and then not compared, which is the shape I-16's round is about: a finding "
        "measured and discarded one line later"),
    Mutation(
        "B45h", f"{U}::_validate_binding",
        "    if not table.observation_units:\n",
        "    if False:\n",
        f"{T}::test_r71_predictive_admission_refuses_an_unbound_table",
        "the predictive-admission route accepts a table bound to nothing again -- and that is the path "
        "where a table decides which posterior nodes are predictively supported"),
    Mutation(
        "B45i", f"{G}::require_bound_forward_table",
        "    if not table.observation_units:\n",
        "    if False:\n",
        f"{T}::test_r71_the_admission_path_refuses_an_unbound_table",
        "the public bound-table requirement stops requiring anything, so a caller who asks the question "
        "gets yes"),
]

_CHANGED_FILES = (G, U)


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
    status = run(MUTATIONS, label="BATCH45", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH45_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 45 changed ---", flush=True)
    status |= run(existing, label="BATCH45_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH45_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
