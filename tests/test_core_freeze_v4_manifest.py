"""Core Freeze V4: the manifest describes this tree, the compatibility claim is proved, V1-V3 are untouched.

V4 is the 2026-09-16 scientific core re-audit's freeze, and its one dangerous move is the regenerated API
snapshot: a freeze that re-pins the surface and then asserts compatibility has asserted nothing. So the claim
here is not "the digest did not move" -- it did, from `c80e6418` to `f18aa806`, and the count did not -- but
that every difference from the V1 surface AS V1 COMMITTED IT is one of the four additive kinds the owner
allowed, difference by difference, with the comparator's problem list empty and its enum insertions named.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engcore import api_snapshot  # noqa: E402
from tools.certification import api_surface_v4, core_freeze_v2, core_freeze_v3, core_freeze_v4  # noqa: E402

MANIFEST = REPO / core_freeze_v4.MANIFEST_PATH

# On a recertification SOURCE commit the repository still holds the PREVIOUS certificate by
# construction, so these can only bind in the certificate-only child. Deferred there, never weakened
# -- the same list the V3 suite keeps, for the same reason.
CERTIFICATE_CHILD_ONLY = {
    "v1.freeze_verifies",
    "certificate.verifies",
    "certificate.covers_required_areas",
}


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("candidate: the V4 manifest is built from the candidate commit")
    return json.loads(MANIFEST.read_bytes())


def _assert_contract_holds_pending_certificate(result):
    binding_failures = {check.name for check in result.checks if check.binding and not check.ok}
    unexpected = binding_failures - CERTIFICATE_CHILD_ONLY
    assert not unexpected, "\n" + result.render()


def test_the_tree_keeps_the_core_freeze_v4_contract(manifest):
    _assert_contract_holds_pending_certificate(core_freeze_v4.verify(REPO, require_assurance=False))


def test_once_assured_the_full_verification_holds(manifest):
    if not (REPO / core_freeze_v4.ASSURANCE_PATH).exists():
        pytest.skip("candidate: the assurance record is written from the formal round's own transcripts")
    _assert_contract_holds_pending_certificate(core_freeze_v4.verify(REPO))


def test_v4_descends_from_v3_and_rewrites_no_history(manifest):
    """A freeze that does not descend from the previous one is a fork (R-65, finding 89)."""
    v3_manifest = json.loads((REPO / core_freeze_v3.MANIFEST_PATH).read_bytes())
    assert manifest["freeze"]["descends_from_v3_commit"] == v3_manifest["freeze"]["candidate_commit"]
    for path, key in ((core_freeze_v2.V1_MANIFEST_PATH, "v1_manifest_sha256"),
                      (core_freeze_v2.MANIFEST_PATH, "v2_manifest_sha256"),
                      (core_freeze_v3.MANIFEST_PATH, "v3_manifest_sha256")):
        assert manifest[key] == core_freeze_v2.sha256_bytes((REPO / path).read_bytes()), path
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", manifest["freeze"]["descends_from_v3_commit"],
         manifest["freeze"]["candidate_commit"]], cwd=REPO).returncode == 0


def test_the_compatibility_claim_is_proved_against_the_bytes_v1_committed(manifest):
    """R-69, finding 95: the audited check compared the live surface with the live surface."""
    stored = core_freeze_v4.stored_v1_frozen_snapshot(REPO)
    v1_manifest = json.loads((REPO / core_freeze_v2.V1_MANIFEST_PATH).read_bytes())
    assert stored["file_sha256"] == v1_manifest["api"]["pinned_files"][
        core_freeze_v4.V1_FROZEN_SNAPSHOT_FILE]
    assert stored["digest"] == core_freeze_v2.V1_FROZEN_DIGEST
    assert core_freeze_v4.additive_only_problems(stored["snapshot"], api_snapshot.frozen_only()) == []
    assert manifest["api"]["additive_only_problems"] == []
    assert manifest["api"]["v2_additive_only_problems"] == []
    assert manifest["api"]["v1_stored"]["frozen_digest"] == core_freeze_v2.V1_FROZEN_DIGEST
    assert manifest["api"]["v4_live"]["frozen_digest"] == api_snapshot.frozen_digest()
    assert manifest["api"]["v4_live"]["frozen_count"] == core_freeze_v2.V1_FROZEN_COUNT == 194


def test_the_inserted_enum_members_are_named_rather_than_discovered(manifest):
    """Finding 95's own measurement: members changed position and nothing detected it."""
    stored = core_freeze_v4.stored_v2_frozen_snapshot(REPO)
    live = api_snapshot.frozen_only(api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES))
    insertions = core_freeze_v4.enum_insertions(stored["snapshot"], live)
    assert manifest["api"]["v2_enum_insertions"] == insertions
    reasons = insertions["engcore.hybrid_uq.RouteReason"]
    assert reasons["members_before"] == 24 and reasons["members_now"] == 43
    assert reasons["existing_members_keep_their_relative_order"] is True
    assert reasons["inserted_before_an_existing_member"] and reasons["positions"]


def test_a_shrunk_or_reordered_surface_is_not_additive():
    """The comparator's own guard: a check that cannot fail is what finding 95 is about."""
    stored = api_snapshot.frozen_only()
    fewer = {**stored, "symbols": stored["symbols"][:-1]}
    assert core_freeze_v4.additive_only_problems(stored, fewer)
    reordered = json.loads(json.dumps(stored))
    for entry in reordered["symbols"]:
        if len(entry.get("dataclass_fields") or []) >= 2:
            entry["dataclass_fields"].reverse()
            break
    assert core_freeze_v4.additive_only_problems(stored, reordered)


def test_the_deep_surface_carries_methods_and_member_positions(manifest):
    """R-69, finding 94: two deleted methods moved neither the V1 nor the V2 digest."""
    built = api_surface_v4.build()
    pinned = json.loads((REPO / core_freeze_v4.SURFACE_PATH).read_text(encoding="utf-8"))
    assert api_surface_v4.canonical_bytes(built) == api_surface_v4.canonical_bytes(pinned)
    assert manifest["api"]["deep_surface"]["digest"] == api_surface_v4.digest()
    assert manifest["api"]["deep_surface"]["method_count"] == built["method_count"] > 1000
    for entry in built["symbols"]:
        if entry.get("enum_members"):
            assert [m["position"] for m in entry["enum_members"]] == list(
                range(len(entry["enum_members"]))), entry["name"]
    assert core_freeze_v4.SURFACE_PATH in manifest["pinned_api_files"]


def test_the_v3_supersession_names_the_rule_that_refuses(manifest):
    """R-70, finding 96: the V3 check passed on any exception, including an ImportError."""
    refusal = core_freeze_v4.v3_fixtures_refused()
    assert refusal["refused"] is True
    assert refusal["exception"] == core_freeze_v4.REQUIRED_V3_REFUSAL[0]
    assert core_freeze_v4.REQUIRED_V3_REFUSAL[1] in refusal["message"]
    assert manifest["v3_fixtures_refused"] == refusal
    assert manifest["supersedes_v3_because"]
    assert not core_freeze_v4.is_the_core_refusal(
        *core_freeze_v4.REQUIRED_V3_REFUSAL, exception="builtins.ImportError",
        message="cannot import name 'fixture_records'")


def test_the_manifest_states_its_capability_and_its_non_claims(manifest):
    assert manifest["capability_claim"] == core_freeze_v4.CAPABILITY_CLAIM
    assert manifest["non_claims"] == list(core_freeze_v4.NON_CLAIMS)
    assert manifest["audit"]["problems"] == 75 and manifest["audit"]["improvements"] == 31
    report = REPO / core_freeze_v4.REPORT_PATH
    assert report.is_file(), f"{core_freeze_v4.REPORT_PATH} is what a reader opens first"


def test_the_certificate_scope_covers_every_area_v4_requires(manifest):
    from tools.certification import core_certificate

    names = {area.name for area in core_certificate.SCOPE}
    assert set(core_freeze_v4.REQUIRED_CERTIFICATE_AREAS) <= names
    assert manifest["certificate"]["required_areas"] == list(core_freeze_v4.REQUIRED_CERTIFICATE_AREAS)
    assert core_certificate.harness_pinning_problems(REPO) == []


def test_the_command_line_verifier_agrees_with_the_function(manifest):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.certification.core_freeze_v4",
                           "--verify"], cwd=REPO, capture_output=True, text=True, encoding="utf-8", env=env)
    assert (proc.returncode == 0) == core_freeze_v4.verify(REPO).ok, proc.stdout[-2000:] + proc.stderr[-2000:]
