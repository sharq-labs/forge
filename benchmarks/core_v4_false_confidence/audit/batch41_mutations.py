"""Batch-41 guard mutations (I-20 part C, R-45's finding 90): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch41_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

U = "src/engcore/scientific/results/uncertainty.py"
D = "src/engcore/scientific/models/definition.py"
I = "src/engcore/hybrid_uq/identifiability.py"
T = "tests/test_core_scientific_audit_batch41.py"
TH = "tests/hybrid_uq/test_core_scientific_audit_batch41_identifiability.py"

MUTATIONS = [
    Mutation(
        "B41a", f"{U}::Uncertainty.to_dict",
        '            "schema": UNCERTAINTY_SCHEMA_V2 if records_source_kind else UNCERTAINTY_SCHEMA,\n',
        '            "schema": UNCERTAINTY_SCHEMA,\n',
        f"{T}::test_r45_an_uncertainty_that_records_where_the_number_came_from_declares_a_new_version",
        "finding 90's item 3 restored for CORE-016: the record carries the source kind under the version "
        "that predates it, so an older reader accepts it and drops the key -- and a NUMERICAL uncertainty "
        "comes back UNSPECIFIED, indistinguishable from one nobody was asked for"),
    Mutation(
        "B41b", f"{U}::Uncertainty.to_dict",
        '            "schema": UNCERTAINTY_SCHEMA_V2 if records_source_kind else UNCERTAINTY_SCHEMA,\n',
        '            "schema": UNCERTAINTY_SCHEMA_V2,\n',
        f"{T}::test_r45_an_uncertainty_that_records_nothing_new_keeps_its_bytes",
        "the opposite error: EVERY record claims the new version, so a record that carries nothing new "
        "changes its bytes and its digest for no reason, and stops being readable by the reader that wrote "
        "it. The control for the rule above"),
    Mutation(
        "B41c", f"{U}::Uncertainty.from_dict",
        '        if version == UNCERTAINTY_SCHEMA and "source_kind" in payload:\n',
        "        if False:\n",
        f"{T}::test_r45_the_old_version_carrying_the_new_key_is_refused",
        "the older version and the newer field coexist again, which is exactly the shape a re-emit produces "
        "when it keeps the field and loses the version. Accepting it makes the version string mean nothing"),
    Mutation(
        "B41d", f"{D}::ValidityAssessment.to_dict",
        '            "schema": VALIDITY_ASSESSMENT_SCHEMA_V3 if binds else VALIDITY_ASSESSMENT_SCHEMA_V2,\n',
        '            "schema": VALIDITY_ASSESSMENT_SCHEMA_V2,\n',
        f"{T}::test_r45_an_assessment_bound_to_an_operating_point_declares_a_new_version",
        "the audited chain restored at its source: the operating point rides under the version that predates "
        "it, so one load and re-emit through an older reader unbinds the assessment -- after which a result "
        "4700 K outside its assessed condition reads IN_DOMAIN, because the refusal has nothing to fire on"),
    Mutation(
        "B41e", f"{D}::ValidityAssessment.to_dict",
        '            "schema": VALIDITY_ASSESSMENT_SCHEMA_V3 if binds else VALIDITY_ASSESSMENT_SCHEMA_V2,\n',
        '            "schema": VALIDITY_ASSESSMENT_SCHEMA_V3,\n',
        f"{T}::test_r45_an_assessment_that_binds_nothing_keeps_its_bytes",
        "every assessment claims the new version, so a record that binds nothing moves its digest. This is "
        "why the bump is conditional, and it is the same rule this repository already applies to these keys"),
    Mutation(
        "B41f", f"{D}::ValidityAssessment.from_dict",
        "        if version != VALIDITY_ASSESSMENT_SCHEMA_V3:\n",
        "        if False:\n",
        f"{T}::test_r45_an_older_assessment_version_carrying_a_binding_is_refused",
        "an older version carrying a binding is read again, so a re-emit that keeps `evaluated` and loses "
        "the version is indistinguishable from an honest record"),
    Mutation(
        "B41g", f"{D}::ValidityAssessment.from_dict",
        "            carried = [key for key in _ASSESSMENT_BINDING_KEYS if payload.get(key)]\n",
        "            carried = []\n",
        f"{T}::test_r45_an_older_assessment_version_carrying_a_binding_is_refused",
        "the rule is reached and sees nothing: the keys it was written to look for are not looked for"),
    Mutation(
        "B41h", f"{I}::RoutedIdentifiability.to_dict",
        '        return {"schema": ROUTED_IDENTIFIABILITY_SCHEMA, "approximation_class": self.approximation_class.value,\n',
        '        return {"schema": ROUTED_IDENTIFIABILITY_SCHEMA_V1, "approximation_class": self.approximation_class.value,\n',
        f"{TH}::test_r45_a_current_record_still_round_trips",
        "finding 90's item 2 restored at the writer: the record goes back to claiming the version that "
        "predates CORE-004's two changes -- the conditioning definition and the explanation text -- and is "
        "then refused by the reader that just wrote it. Written as a NAME swap rather than as a new string, "
        "because the mutation digest ignores string tokens and an edited literal reports no code change"),
    Mutation(
        "B41i", f"{I}::RoutedIdentifiability.from_dict",
        '        if payload.get("schema") == ROUTED_IDENTIFIABILITY_SCHEMA_V1:\n',
        "        if False:\n",
        f"{TH}::test_r45_a_pre_core004_record_is_refused_for_the_reason_it_cannot_be_read",
        "the `/1` record falls through to the re-derivation, which reports that a verdict does not follow "
        "from numbers that give the same verdict -- a contradiction where the record is simply unreadable, "
        "and a reader sent looking for a defect that is not there"),
]

_CHANGED_FILES = (U, D, I)


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
    status = run(MUTATIONS, label="BATCH41", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH41_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 41 changed ---", flush=True)
    status |= run(existing, label="BATCH41_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH41_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
