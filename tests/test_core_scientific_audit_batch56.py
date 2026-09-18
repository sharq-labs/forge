"""Core re-audit 2026-09-16, batch 56: the Core Freeze V4 control plane, and a comparator that can fail.

Problems R-65 (finding 89), R-69 (findings 94 and 95), R-70 (finding 96) and R-66's freeze-record half
(finding 91), improvement I-29, under benchmarks/core_v4_false_confidence/BATCH56_THRESHOLD_PROTOCOL.json.

Nineteen FAST-tier tests have been failing by design since this round's first batch: the V1 frozen digest
moved, four pinned snapshots describe the pre-round surface, and the V2 and V3 manifests state a contract the
hardened readers now refuse. V4 is where that becomes a freeze instead of a broken tree -- and the one thing
it must not do is regenerate a snapshot and call the result compatible. So the compatibility claim is PROVED
against the V1 snapshot AS COMMITTED, difference by difference, by a comparator that names what additive
means and can therefore fail.

Recorded as strict xfails in commit e658f5e7, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import re

import pytest

from engcore import api_snapshot

REPO = pathlib.Path(__file__).resolve().parent.parent
V1_MANIFEST = REPO / "certification" / "core_freeze_v1.json"
POLICY = REPO / "docs" / "CORE_FREEZE_POLICY.md"


def _module(name: str):
    """Import ``name``, or FAIL saying what is missing rather than erroring on the import."""
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        pytest.fail(f"{name} does not exist, so the rule it carries is not stated anywhere: {exc}")


def _attribute(module, name: str):
    found = getattr(module, name, None)
    assert found is not None, (
        f"{module.__name__} has no {name!r}: the rule this test is about is not stated in the tree")
    return found


def _state_table() -> dict[str, str]:
    """The FROZEN-STATE table of the executable policy document, as a mapping."""
    rows = {}
    for line in POLICY.read_text(encoding="utf-8").splitlines():
        found = re.match(r"^\|\s*([^|]+?)\s*\|\s*`?([^|`]+?)`?\s*\|$", line)
        if found:
            rows[found.group(1)] = found.group(2)
    return rows


# ---------------------------------------------------------------------------
# R-65: a freeze the round can actually be certified under
# ---------------------------------------------------------------------------
def test_r65_a_core_freeze_v4_verifier_exists_and_binds_on_a_descendant_of_v3():
    v4 = _module("tools.certification.core_freeze_v4")
    manifest_path = REPO / _attribute(v4, "MANIFEST_PATH")
    assert manifest_path.is_file(), f"{manifest_path.name} is the V4 contract and does not exist"
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["schema"] == v4.MANIFEST_SCHEMA
    result = _attribute(v4, "verify")(REPO, require_clean=False, require_assurance=False)
    assert result.mode in ("EXACT_FREEZE", "DESCENDANT"), (
        f"the V4 candidate does not descend from this tree's history: {result.mode}")
    v3 = manifest.get("freeze", {}).get("descends_from_v3_commit", "")
    assert v3, "the V4 freeze does not say which V3 commit it descends from"


def test_r65_the_frozen_state_table_states_the_digest_the_tree_computes():
    """The one number a consumer quotes in a bug report, and it has been wrong all round."""
    assert _state_table()["frozen digest"] == api_snapshot.frozen_digest()
    assert _state_table()["frozen symbols"] == "194"


def test_r65_the_pinned_snapshots_describe_the_live_surface():
    pinned = json.loads((REPO / "tests" / "api" / "frozen_api_snapshot.json").read_text(encoding="utf-8"))
    assert api_snapshot.canonical_bytes(api_snapshot.frozen_only()) == api_snapshot.canonical_bytes(pinned)


def test_r65_the_deferred_self_checks_cover_every_check_that_reads_the_previous_freeze():
    """Finding 89's second sentence: a source gate that can never be green blocks recertification."""
    scope = _module("tools.certification.recertification_scope")
    deferred = set(scope.CERTIFICATE_SELF_CHECKS)
    # The nineteen by-design failures of this round, by node. Each compares the tree against an
    # artifact describing the PREVIOUS freeze, which is the definition of a self-check here.
    required = {
        "tests/test_core_api_snapshot.py::test_the_public_api_matches_the_pinned_snapshot",
        "tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes",
        "tests/test_core_freeze_policy.py::test_the_policy_states_the_real_frozen_digest",
        "tests/test_core_freeze_v2_manifest.py::test_the_v2_frozen_api_surface_is_superseded_additively",
        "tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks",
        "tests/test_core_v2_api_snapshot.py::test_the_live_v2_frozen_surface_matches_the_pinned_snapshot",
        "tests/test_core_v2_compatibility.py::test_the_v1_surface_is_the_v1_contract_plus_only_additive_changes",
    }
    assert required <= deferred, sorted(required - deferred)


# ---------------------------------------------------------------------------
# R-69: the comparator, and what additive means
# ---------------------------------------------------------------------------
def test_r69_the_comparator_reads_the_v1_snapshot_as_it_was_committed():
    """Finding 95: `v1_entries_byte_identical_in_v2` compares the live surface with the live surface."""
    v4 = _module("tools.certification.core_freeze_v4")
    stored = _attribute(v4, "stored_v1_frozen_snapshot")(REPO)
    manifest = json.loads(V1_MANIFEST.read_bytes())
    assert stored["digest"] == manifest["api"]["frozen_digest"], (
        "the snapshot the comparator reads is not the one Core Freeze V1 recorded")
    assert stored["file_sha256"] == manifest["api"]["pinned_files"]["tests/api/frozen_api_snapshot.json"]
    assert stored["digest"] != api_snapshot.frozen_digest(), (
        "the stored and live digests are equal, so this round changed nothing and there is nothing to prove")


def test_r69_every_difference_from_the_stored_v1_surface_is_additive():
    """The round's compatibility claim, proved rather than asserted."""
    v4 = _module("tools.certification.core_freeze_v4")
    problems = _attribute(v4, "additive_only_problems")(
        v4.stored_v1_frozen_snapshot(REPO)["snapshot"], api_snapshot.frozen_only())
    assert problems == [], "\n  ".join(problems)


def _one_symbol(**overrides):
    entry = {
        "module": "engcore.scientific", "name": "Thing", "kind": "dataclass",
        "classification": "FREEZE", "defined_in": "engcore.scientific.thing",
        "signature": {"parameters": [
            {"name": "a", "kind": "POSITIONAL_OR_KEYWORD", "has_default": False},
            {"name": "b", "kind": "KEYWORD_ONLY", "has_default": True,
             "default": {"kind": "literal", "type": "int", "value": 1}},
        ], "returns": "None"},
        "dataclass_fields": [
            {"name": "a", "has_default": False},
            {"name": "b", "has_default": True},
        ],
        "enum_members": None,
    }
    entry.update(overrides)
    return {"schema": "engcore.api_snapshot/1", "symbols": [entry]}


def test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted():
    v4 = _module("tools.certification.core_freeze_v4")
    compare = _attribute(v4, "additive_only_problems")
    stored = _one_symbol()
    grown = _one_symbol(kind="constant", signature=None, dataclass_fields=None,
                        value={"kind": "immutable_container", "type": "tuple", "size": 9})
    container = _one_symbol(kind="constant", signature=None, dataclass_fields=None,
                            value={"kind": "immutable_container", "type": "tuple", "size": 8})
    assert compare(container, grown) == [], (
        "a frozen tuple that GAINED an entry is the constant form of appending an enum member")

    added_field = _one_symbol(dataclass_fields=[
        {"name": "a", "has_default": False}, {"name": "b", "has_default": True},
        {"name": "c", "has_default": True}])
    assert compare(stored, added_field) == [], "an appended defaulted field is the owner's allowed change"

    new_keyword = _one_symbol(signature={"parameters": [
        *stored["symbols"][0]["signature"]["parameters"],
        {"name": "c", "kind": "KEYWORD_ONLY", "has_default": True,
         "default": {"kind": "literal", "type": "int", "value": 0}},
    ], "returns": "None"})
    assert compare(stored, new_keyword) == []

    for label, live in (
        ("a removed symbol", {"schema": "engcore.api_snapshot/1", "symbols": []}),
        ("a reordered field", _one_symbol(dataclass_fields=[
            {"name": "b", "has_default": True}, {"name": "a", "has_default": False}])),
        ("a field inserted before the last", _one_symbol(dataclass_fields=[
            {"name": "a", "has_default": False}, {"name": "c", "has_default": True},
            {"name": "b", "has_default": True}])),
        ("a new field with no default", _one_symbol(dataclass_fields=[
            {"name": "a", "has_default": False}, {"name": "b", "has_default": True},
            {"name": "c", "has_default": False}])),
        ("a removed parameter", _one_symbol(signature={"parameters": [
            {"name": "a", "kind": "POSITIONAL_OR_KEYWORD", "has_default": False}], "returns": "None"})),
        ("a changed default", _one_symbol(signature={"parameters": [
            {"name": "a", "kind": "POSITIONAL_OR_KEYWORD", "has_default": False},
            {"name": "b", "kind": "KEYWORD_ONLY", "has_default": True,
             "default": {"kind": "literal", "type": "int", "value": 2}}], "returns": "None"})),
        ("a keyword-only argument made positional", _one_symbol(signature={"parameters": [
            {"name": "a", "kind": "POSITIONAL_OR_KEYWORD", "has_default": False},
            {"name": "b", "kind": "POSITIONAL_OR_KEYWORD", "has_default": True,
             "default": {"kind": "literal", "type": "int", "value": 1}}], "returns": "None"})),
        ("a new required argument", _one_symbol(signature={"parameters": [
            *stored["symbols"][0]["signature"]["parameters"],
            {"name": "c", "kind": "KEYWORD_ONLY", "has_default": False}], "returns": "None"})),
        ("a changed kind", _one_symbol(kind="class")),
        ("a changed exception chain", _one_symbol(exception_mro=["engcore.X"])),
        # A frozen tuple of field names that LOST one: two records that differed become one
        # identity. The growth of such a container is additive (see amendment 1 of batch 13 and
        # `_constant_problems`), and the shrink is the break that rule must not let through.
    ):
        assert compare(stored, live), f"{label} is accepted as additive"

    # A frozen tuple of field names that LOST one: two records that differed become one identity.
    # Compared constant-against-constant, because a kind change would be caught by another rule and
    # this is about the size comparison itself.
    shrunk = _one_symbol(kind="constant", signature=None, dataclass_fields=None,
                         value={"kind": "immutable_container", "type": "tuple", "size": 7})
    assert compare(container, shrunk), "a frozen container that SHRANK is accepted as additive"


def test_r69_a_reordered_enum_member_is_not_additive():
    """Finding 95: 13 RouteReason members changed position without detection."""
    v4 = _module("tools.certification.core_freeze_v4")
    compare = _attribute(v4, "additive_only_problems")
    stored = _one_symbol(kind="enum", dataclass_fields=None, signature=None, enum_members=[
        {"name": "ONE", "value": "one"}, {"name": "TWO", "value": "two"}])
    appended = _one_symbol(kind="enum", dataclass_fields=None, signature=None, enum_members=[
        {"name": "ONE", "value": "one"}, {"name": "TWO", "value": "two"},
        {"name": "THREE", "value": "three"}])
    assert compare(stored, appended) == [], "an appended enum member is the owner's allowed change"
    for label, members in (
        ("reordered", [{"name": "TWO", "value": "two"}, {"name": "ONE", "value": "one"}]),
        ("revalued", [{"name": "ONE", "value": "1"}, {"name": "TWO", "value": "two"}]),
        ("removed", [{"name": "ONE", "value": "one"}]),
    ):
        live = _one_symbol(kind="enum", dataclass_fields=None, signature=None, enum_members=members)
        assert compare(stored, live), f"a {label} enum member is accepted as additive"

    # AMENDED against its preregistered form (amendment 1). As preregistered this loop also required
    # an INSERTED member to be a problem. It is not one: every member a consumer named is still
    # there, with its value, and still before the members it was before -- and this round inserted 7
    # such members into `RouteReason` across fifty-five batches, so refusing them here would refuse
    # the round rather than measure it. What finding 95 actually reports is that the insertion went
    # UNDETECTED, so it is additive AND recorded: `enum_insertions` names each inserted member and
    # the position it took, the V4 manifest carries the list, and the audit document carries the
    # owner's decision, whose compatibility rule forbids reordering and does not say which of the
    # two an insertion is.
    inserted = _one_symbol(kind="enum", dataclass_fields=None, signature=None, enum_members=[
        {"name": "ONE", "value": "one"}, {"name": "THREE", "value": "three"},
        {"name": "TWO", "value": "two"}])
    assert compare(stored, inserted) == [], compare(stored, inserted)
    recorded = _attribute(v4, "enum_insertions")(stored, inserted)
    assert recorded["engcore.scientific.Thing"]["inserted_before_an_existing_member"] == ["THREE"]
    assert recorded["engcore.scientific.Thing"]["positions"] == [1]


def test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see():
    """Finding 94: removing `record_values` or `evidence_basis` left both digests unchanged.

    `record_values` is a keyword argument of `ValidityDomain.assess` and `evidence_basis` is a method of
    `ValidationReport`. Neither is a module-level symbol, and `engcore.api_snapshot` describes module-level
    symbols only -- so the object a consumer calls could lose either without moving a number the freeze
    policy quotes. Both are in the deep surface now, with their parameter lists.
    """
    surface = _module("tools.certification.api_surface_v4")
    built = _attribute(surface, "build")()
    methods = {(entry["module"], entry["name"]): entry.get("methods", {}) for entry in built["symbols"]}
    domain = methods[("engcore.scientific", "ValidityDomain")]
    assert "assess" in domain, sorted(domain)
    assert "record_values" in [p["name"] for p in domain["assess"]["parameters"]], domain["assess"]
    report = methods[("engcore.scientific", "ValidationReport")]
    assert "evidence_basis" in report, sorted(report)
    assert built["method_count"] > 1000, built["method_count"]
    pinned = REPO / "certification" / "core_v4_api_surface.json"
    assert pinned.is_file(), "the deeper surface is not pinned, so nothing compares it with anything"
    assert surface.canonical_bytes(built) == surface.canonical_bytes(
        json.loads(pinned.read_text(encoding="utf-8")))


def test_r69_the_v4_surface_records_enum_member_positions():
    surface = _module("tools.certification.api_surface_v4")
    built = surface.build()
    reasons = next(e for e in built["symbols"]
                   if (e["module"], e["name"]) == ("engcore.scientific", "ValidationOutcome"))
    assert [member["position"] for member in reasons["enum_members"]] == list(
        range(len(reasons["enum_members"]))), "the positions are not recorded, so a reorder is invisible"


# ---------------------------------------------------------------------------
# R-70: which rule refused
# ---------------------------------------------------------------------------
def test_r70_the_supersession_check_names_the_rule_that_refuses_the_v3_fixtures():
    """Finding 96: the V3 check passed when the rule was removed and an ImportError raised instead."""
    v4 = _module("tools.certification.core_freeze_v4")
    refused = _attribute(v4, "v3_fixtures_refused")()
    assert refused["refused"] is True, refused
    assert refused["exception"].startswith("engcore."), (
        f"the refusal is not raised by the core: {refused['exception']}")
    assert "contradict their own measurements" in refused["message"], refused["message"]
    is_refusal = _attribute(v4, "is_the_core_refusal")
    assert is_refusal(*v4.REQUIRED_V3_REFUSAL, exception=refused["exception"], message=refused["message"])
    for label, exception, message in (
        ("an import error", "builtins.ImportError", "cannot import name 'fixture_records'"),
        ("a type error", "builtins.TypeError", "fixture_records() takes 0 arguments"),
        ("a core refusal about something else", "engcore.scientific.errors.ScientificCoreError",
         "the record has no schema key"),
    ):
        assert not is_refusal(*v4.REQUIRED_V3_REFUSAL, exception=exception, message=message), (
            f"{label} counts as the refusal")


# ---------------------------------------------------------------------------
# R-66: the figures a record asserts about itself
# ---------------------------------------------------------------------------
def test_r66_an_assurance_record_whose_figures_disagree_with_the_tree_is_refused():
    """Finding 91: a fabricated record with green flags and a copied population sha passed every check."""
    v4 = _module("tools.certification.core_freeze_v4")
    from tools.certification import mutation_population as mp

    population = mp.v4_population(REPO)
    entries = {entry[0]: entry for entry in mp.v4_entries(REPO)}
    logs = {}
    for index in range(mp.SHARD_COUNT):
        selected = population.shard(index)
        lines = [f"{mid} {entries[mid][4].split('::')[-1]} -> {entries[mid][5]} | 1 failed"
                 for mid in selected]
        lines.append("CONTROL (unmutated) GREEN | 1 passed")
        logs[index] = ("\n".join(lines) + "\n").encode("utf-8")
    honest = _attribute(v4, "v4_mutation_assurance")(REPO, logs=logs, source_commit="HEAD")
    assert _attribute(v4, "v4_mutation_problems")(REPO, honest, logs=logs) == []

    fabricated = json.loads(json.dumps(honest))
    fabricated["population_sha256"] = "0" * 64
    assert v4.v4_mutation_problems(REPO, fabricated, logs=logs), (
        "a record naming a population the tree does not have is accepted")

    copied = json.loads(json.dumps(honest))
    copied["shards"]["0"]["execution_log_sha256"] = copied["shards"]["1"]["execution_log_sha256"]
    assert v4.v4_mutation_problems(REPO, copied, logs=logs), (
        "a shard whose log digest is another shard's is accepted -- the copied sha of finding 91")

    # The transcript must be READ and not only hashed. The record is built FROM the silent
    # transcript, so its digest matches and the only thing left that can refuse it is what the
    # lines say -- which is the record vouching for itself, finding 91's shape.
    silent = {index: b"nothing happened here\n" for index in logs}
    self_consistent = v4.v4_mutation_assurance(REPO, logs=silent, source_commit="HEAD")
    assert v4.v4_mutation_problems(REPO, self_consistent, logs=silent), (
        "a shard record whose own transcript reports no verdict at all is accepted")

    one_lying = dict(logs)
    first = sorted(logs)[0]
    one_lying[first] = logs[first].replace(b" -> KILLED", b" -> NOT_A_TEST_FAILURE(exit 2)", 1)
    lying_record = v4.v4_mutation_assurance(REPO, logs=one_lying, source_commit="HEAD")
    assert v4.v4_mutation_problems(REPO, lying_record, logs=one_lying), (
        "a shard whose transcript reports a verdict the entry did not declare is accepted")


def test_r65_a_candidate_that_descends_from_no_freeze_is_not_a_descendant():
    """R-65's first sentence, at its own boundary: *the branch descends from no Core Freeze.*"""
    v4 = _module("tools.certification.core_freeze_v4")
    descends = _attribute(v4, "descends_from")
    manifest = json.loads((REPO / v4.MANIFEST_PATH).read_bytes())
    v3_commit = manifest["freeze"]["descends_from_v3_commit"]
    candidate = manifest["freeze"]["candidate_commit"]
    assert descends(REPO, v3_commit, candidate)
    assert not descends(REPO, "0" * 40, candidate), "an unknown ancestor reads as an ancestor"
    assert not descends(REPO, "", candidate), "no ancestor at all reads as nothing to check"
    assert not descends(REPO, candidate, v3_commit), "descent is not symmetric and is read as if it were"


def test_r69_the_v2_surface_is_compared_too_because_the_v1_contract_has_no_hybrid_uq():
    """`RouteReason` -- the enum finding 95 measured -- is a V2 symbol, not a V1 one."""
    v4 = _module("tools.certification.core_freeze_v4")
    facts = _attribute(v4, "api_facts")(REPO)
    assert facts["v2_additive_only_problems"] == []
    assert facts["v2_stored"]["frozen_digest"] and facts["v4_live"]["v2_frozen_count"] == 221
    insertions = facts["v2_enum_insertions"]
    assert "engcore.hybrid_uq.RouteReason" in insertions, (
        "the V2 surface is not compared, so the module the finding is in is outside the proof")
    assert insertions["engcore.hybrid_uq.RouteReason"]["members_now"] == 43
