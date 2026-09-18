"""Batch-56 guard mutations (I-29, R-65/R-66/R-69/R-70): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``. This batch is the Core Freeze V4 control
plane, so every guard here is a check about a CHECK -- which is exactly the kind the re-audit found
passing vacuously: a comparison of the live surface with itself, a supersession satisfied by any
exception, an assurance record read for its own figures.

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch56_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

F = "tools/certification/core_freeze_v4.py"
S = "tools/certification/api_surface_v4.py"
T = "tests/test_core_scientific_audit_batch56.py"
V = "tests/test_core_freeze_v4_manifest.py"

MUTATIONS = [
    Mutation(
        "B56a", f"{F}::stored_v1_frozen_snapshot",
        "    baseline = manifest[\"freeze\"][\"baseline_commit\"]\n",
        "    baseline = \"HEAD\"\n",
        f"{T}::test_r69_the_comparator_reads_the_v1_snapshot_as_it_was_committed",
        "finding 95 restored: the comparison reads the snapshot at HEAD rather than at the commit "
        "Core Freeze V1 recorded, so it is the live surface against the live surface and cannot "
        "fail. Written as a change to the COMMIT rather than to the f-string that formats it, "
        "because an edit inside an f-string changes no executable token on Python 3.11"),
    Mutation(
        "B56b", f"{F}::_parameter_problems",
        "        if name not in old and not parameter.get(\"has_default\"):\n",
        "        if False:\n",
        f"{T}::test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted",
        "a new argument with NO default reads as additive, so a change that breaks every caller "
        "passes the compatibility proof"),
    Mutation(
        "B56c", f"{F}::_parameter_problems",
        "        if parameter.get(\"kind\") != after.get(\"kind\"):\n",
        "        if False:\n",
        f"{T}::test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted",
        "a keyword-only argument may become positional-or-keyword again: the owner's FORBIDDEN list "
        "names parameter kind, and a caller's keyword call still works while the contract has moved"),
    Mutation(
        "B56d", f"{F}::_field_problems",
        "        if names_after.index(name) < max(\n"
        "                (names_after.index(kept) for kept in kept_after), default=-1):\n",
        "        if False:\n",
        f"{T}::test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted",
        "a new dataclass field may be inserted BEFORE the fields that existed, so every positional "
        "construction in every consumer silently moves by one"),
    Mutation(
        "B56e", f"{F}::_enum_problems",
        "    if before != after:\n",
        "    if False:\n",
        f"{T}::test_r69_a_reordered_enum_member_is_not_additive",
        "the members that existed before may be REORDERED, which is the owner's forbidden move and "
        "the half of finding 95 that is not an insertion"),
    Mutation(
        "B56f", f"{F}::_constant_problems",
        "            and live[\"size\"] > stored[\"size\"]:\n",
        "            and live[\"size\"] != stored[\"size\"]:\n",
        f"{T}::test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted",
        "a frozen container that SHRANK reads as additive, so EVIDENCE_IDENTITY_FIELDS losing a "
        "field -- two records that differ becoming one identity -- passes the proof"),
    Mutation(
        "B56g", f"{F}::is_the_core_refusal",
        "    return exception == required_exception and required_phrase in message\n",
        "    return bool(exception)\n",
        f"{T}::test_r70_the_supersession_check_names_the_rule_that_refuses_the_v3_fixtures",
        "finding 96 exactly: any exception counts as the refusal again, so deleting the rule and "
        "raising an ImportError in its place reads as the supersession holding"),
    Mutation(
        "B56h", f"{F}::v4_mutation_problems",
        "    if record.get(\"population_sha256\") != population.sha256:\n",
        "    if False:\n",
        f"{T}::test_r66_an_assurance_record_whose_figures_disagree_with_the_tree_is_refused",
        "finding 91's copied sha: a record may name a population the tree does not have"),
    Mutation(
        "B56i", f"{F}::v4_mutation_problems",
        "        if v2.sha256_bytes(log) != entry.get(\"execution_log_sha256\"):\n",
        "        if False:\n",
        f"{T}::test_r66_an_assurance_record_whose_figures_disagree_with_the_tree_is_refused",
        "a shard's recorded log digest is not compared with the transcript's own bytes, so one "
        "shard's evidence can stand in for another's"),
    Mutation(
        "B56j", f"{F}::v4_mutation_problems",
        "        problems += [f\"shard {index}: {problem}\" for problem in\n"
        "                     mp.v4_log_problems(log.decode(\"utf-8\", \"replace\"), population, selected)]\n",
        "        pass\n",
        f"{T}::test_r66_an_assurance_record_whose_figures_disagree_with_the_tree_is_refused",
        "the transcript is hashed and never READ, so a green flag beside a file that says nothing "
        "is accepted -- the record vouching for itself"),
    Mutation(
        "B56k", f"{S}::methods_of",
        "        if name.startswith(\"_\") and name not in RECORDED_DUNDERS:\n",
        "        if True:\n",
        f"{T}::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see",
        "finding 94 restored: no method is recorded at all, so deleting one moves no digest"),
    Mutation(
        "B56l", f"{S}::build",
        "            described[\"enum_members\"] = [\n"
        "                {\"name\": member.name, \"value\": member.value, \"position\": position}\n"
        "                for position, member in enumerate(value)\n"
        "            ]\n",
        "            described[\"enum_members\"] = [\n"
        "                {\"name\": member.name, \"value\": member.value}\n"
        "                for member in sorted(value, key=lambda m: m.name)\n"
        "            ]\n",
        f"{T}::test_r69_the_v4_surface_records_enum_member_positions",
        "the deep surface records members by name and NOT their positions, sorted -- which is the "
        "shape in which finding 95's 13 moved members are invisible"),
    Mutation(
        "B56m", f"{F}::descends_from",
        "    if not ancestor or not commit:\n        return False\n",
        "    if not ancestor or not commit:\n        return True\n",
        f"{T}::test_r65_a_candidate_that_descends_from_no_freeze_is_not_a_descendant",
        "R-65's first sentence: a freeze that descends from no previous freeze verifies, which is a "
        "fork presented as a contract"),
    Mutation(
        "B56n", f"{F}::api_facts",
        "        \"v2_additive_only_problems\": additive_only_problems(stored_v2[\"snapshot\"], live_v2),\n",
        "        \"v2_additive_only_problems\": additive_only_problems(live_v2, live_v2),\n",
        f"{T}::test_r69_the_v2_surface_is_compared_too_because_the_v1_contract_has_no_hybrid_uq",
        "finding 95's exact shape on the V2 surface: the comparison is made against the LIVE surface "
        "instead of the bytes V2 committed, so it cannot fail -- and the inserted members vanish with "
        "it. PAIRED, because the empty problem list alone is indistinguishable from an honest tree; "
        "what a reader can see is that the insertions stop being reported",
        also=((F + "::api_facts",
               "        \"v2_enum_insertions\": enum_insertions(stored_v2[\"snapshot\"], live_v2),\n",
               "        \"v2_enum_insertions\": enum_insertions(live_v2, live_v2),\n"),)),
]

_CHANGED_FILES = (F, S)


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
    status = run(MUTATIONS, label="BATCH56", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH56_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 56 changed ---", flush=True)
    status |= run(existing, label="BATCH56_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH56_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
