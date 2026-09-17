"""Batch-36 guard mutations (I-14 part D, R-22(a): the observation count): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch36_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

LG = "src/engcore/hybrid_uq/local_gaussian.py"
SP = "src/engcore/inference/split.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch36.py"

MUTATIONS = [
    Mutation(
        "B36a", f"{LG}::_require_reasons_follow_measurements",
        "        elif int(head) != n:\n",
        "        elif False:\n",
        f"{T}::test_r22a_editing_the_observation_count_is_refused",
        "R-22(a) restored exactly: the count goes back to agreeing with nothing, so raising 10 to 40 turns "
        "chi-square 30 from a DOWNGRADE on 10 degrees of freedom into a plausible fit on 38 and the record "
        "reads back SUPPORTED. The whole point of repeating the count in the clear is this comparison"),
    Mutation(
        "B36b", f"{LG}::RouteDiagnostics.from_dict",
        "            if not str(payload.get(\"observation_content_digest\", \"\")):\n",
        "            if False:\n",
        f"{T}::test_r22a_a_record_with_no_digest_under_the_new_schema_is_refused",
        "the digest becomes optional under the schema it was added for, so an absent field no longer "
        "distinguishes an old record from an edited one -- which is exactly what the bump was for. A schema "
        "version that does not make its own field mandatory has bought nothing"),
    Mutation(
        "B36c", f"{LG}",
        "        observation_content_digest=observation_set_content_digest(observations),\n",
        "        observation_content_digest=\"\",\n",
        f"{T}::test_r22a_a_record_carries_the_digest_of_the_observations_it_was_fitted_to",
        "the route stops writing the digest, so every record it produces carries the `/3` schema and the "
        "`/2` shape -- a rule that is present in the reader and absent from the writer, which is the "
        "shape this whole round keeps finding"),
    Mutation(
        "B36d", f"{LG}::require_posterior_matches_observations",
        "    if carried and carried != expected:\n",
        "    if False:\n",
        f"{T}::test_r22a_the_route_binds_its_own_record_to_the_observations_it_used",
        "the digest half of the production check goes and only the count is compared, so a record fitted to "
        "one set of six observations passes against any other set of six. The count is checkable from the "
        "record alone; the digest is the half that needs the observations, and it is the half that binds. It first survived because this function ALSO re-checked `calibration_content_digest`, which caught the same forgery -- so the new binding was being credited to an old one. That third check was removed: one rule per function"),
    Mutation(
        "B36e", f"{LG}::require_posterior_matches_observations",
        "    if int(posterior.diagnostics.observations) != counted:\n",
        "    if False:\n",
        f"{T}::test_r22a_an_older_records_count_is_still_checked_against_the_observations",
        "the count half goes. A forger who edits the count AND the digest to agree with each other passes "
        "the record-level check, and this is the only thing that then notices the pair matches no "
        "observation set that exists. Repointed while running: given a digest the count is REDUNDANT -- the digest states the count -- so the forgery it first named was caught by the digest check and this mutation survived. The case the count check is actually for is a `/2` record, whose digest is empty and carries no count at all"),
    Mutation(
        "B36f", f"{SP}::observation_set_content_digest",
        "    for digest in sorted(observation_content_digest(row) for row in rows):\n",
        "    for digest in (observation_content_digest(row) for row in rows):\n",
        f"{T}::test_r22a_the_same_evidence_in_another_order_is_the_same_digest",
        "the set digest becomes order-dependent, so the same rows imported in another order are two "
        "contents -- which contradicts the per-observation digest's own stated rule, that the same reading "
        "relabelled is the same reading"),
    Mutation(
        "B36g", f"{SP}::observation_set_content_digest",
        "    return f\"{len(rows)}:{inner.hexdigest()}\"\n",
        "    return inner.hexdigest()\n",
        f"{T}::test_r22a_an_observation_set_digests_its_count_and_its_content",
        "the count leaves the field, and with it the only thing a reader holding ONLY a record can check. A "
        "digest cannot be compared with a count without the observations, which is why the count is in the "
        "clear and why that is the design rather than a redundancy"),
    Mutation(
        "B36h", f"{SP}::observation_set_content_digest",
        "        inner.update(digest.encode(\"ascii\"))\n",
        "        pass\n",
        f"{T}::test_r22a_a_different_reading_is_a_different_digest",
        "the digest stops depending on the observations at all -- every set of six rows digests identically "
        "-- so the field carries a count and a constant. A binding to nothing, which passes every check "
        "written against its FORM"),
]

_CHANGED_FILES = (LG, SP)


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
    status = run(MUTATIONS, label="BATCH36", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH36_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 36 changed ---", flush=True)
    status |= run(existing, label="BATCH36_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH36_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
