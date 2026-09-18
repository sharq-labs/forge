"""Core Freeze V3 as a historical record: what it froze, and that V4 supersedes it without rewriting it.

AMENDED at Core Freeze V4 (I-29, R-65), exactly as `tests/test_core_freeze_v2_manifest.py` was amended when
V3 superseded V2, and for the same reason one round along. Until the 2026-09-16 scientific core re-audit this
module verified the V3 contract against the live tree. That contract can no longer hold on a correct tree: V3
pins as its identity references `hybrid_uq.route_diagnostics/1` records that name no thresholds and carry a
nan chi-square minimum, and R-01/R-20 make every such record refuse on read. Core Freeze V4
(`tests/test_core_freeze_v4_manifest.py`) is the binding contract for descendants. What stays true, and is
asserted here, is the record V3 made of its own freeze -- and that the supersession is MEASURED on this tree,
by the rule that refuses, not by any exception (R-70).
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

from tools.certification import core_freeze_v2, core_freeze_v3  # noqa: E402

MANIFEST = REPO / core_freeze_v3.MANIFEST_PATH

# On a recertification SOURCE commit the repository still holds the previous
# certificate by construction. These checks can only bind once the official
# builder writes the certificate-only child, which runs the full V3 verification
# through the pinned V1 descendant self-check. Deferred there, never weakened.
CERTIFICATE_CHILD_ONLY = {
    "v1.freeze_verifies",
    "certificate.verifies",
    "certificate.covers_required_areas",
}

#: The V3 checks Core Freeze V4 supersedes, each with the reason. Added at V4 (I-29, R-65); nothing
#: outside this set and the one above may fail, which is what makes "superseded" different from
#: "broken". `tree.clean` is not in it: a dirty tree is not a superseded contract.
SUPERSEDED_BY_V4 = {
    "v1.symbols_preserved": "the V1 frozen digest moved additively; V4 proves it against V1's own bytes",
    "api.unchanged_from_v2": "the re-audit added enum members and trailing defaulted fields",
    "api.pinned_snapshot_bytes": "the four snapshots are re-pinned by V4, which records both digests",
    "v3.serialization_and_identity": "V3's identity references are refused by this tree -- the supersession",
    "v3.vocabulary": "the route vocabulary gained 19 RouteReason members, 7 of them inserted",
}


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("candidate: the V3 manifest is built from the candidate commit")
    return json.loads(MANIFEST.read_bytes())


def _assert_contract_holds_pending_certificate(result):
    binding_failures = {check.name for check in result.checks if check.binding and not check.ok}
    unexpected = binding_failures - CERTIFICATE_CHILD_ONLY
    assert not unexpected, "\n" + result.render()


def test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks(manifest):
    """AMENDED at V4. Was: this tree keeps the V3 contract.

    It does not, and this asserts WHICH checks it no longer keeps and that nothing else moved -- the
    difference between a superseded contract and a broken tree. The V3 verifier REPORTS the refusal
    now instead of dying on it: a traceback out of a verifier says nothing about which contract
    holds.
    """
    result = core_freeze_v3.verify(REPO, require_assurance=False)
    failing = {check.name for check in result.checks if check.binding and not check.ok}
    assert failing <= (CERTIFICATE_CHILD_ONLY | set(SUPERSEDED_BY_V4)), "\n" + result.render()
    assert "v3.serialization_and_identity" in failing, (
        "V3's identity references are accepted, so nothing supersedes V3 and V4 has no subject")
    detail = next(c.detail for c in result.checks if c.name == "v3.serialization_and_identity")
    assert "superseded by Core Freeze V4" in detail and "HybridUQError" in detail, detail


def test_core_freeze_v4_is_the_contract_that_binds_on_this_tree(manifest):
    """The other half: a superseded freeze is only superseded BY something that verifies."""
    from tools.certification import core_freeze_v4

    v4_manifest = REPO / core_freeze_v4.MANIFEST_PATH
    assert v4_manifest.is_file(), "V3 is superseded by nothing, which is a tree with no contract"
    recorded = json.loads(v4_manifest.read_bytes())
    assert recorded["v3_manifest_sha256"] == core_freeze_v2.sha256_bytes(MANIFEST.read_bytes()), (
        "the V3 manifest was rewritten rather than recorded")
    assert recorded["supersedes_v3_because"]
    assert recorded["freeze"]["descends_from_v3_commit"] == manifest["freeze"]["candidate_commit"]
    result = core_freeze_v4.verify(REPO, require_assurance=False)
    failing = {check.name for check in result.checks if check.binding and not check.ok}
    assert failing <= CERTIFICATE_CHILD_ONLY, "\nCore Freeze V4:\n" + result.render()


def test_the_v3_refusal_is_the_named_rule_and_not_any_exception(manifest):
    """R-70, finding 96: V3's own supersession check counted an ImportError as the refusal."""
    from tools.certification import core_freeze_v4

    refusal = core_freeze_v4.v3_fixtures_refused()
    assert refusal["refused"] is True
    assert refusal["exception"] == "engcore.hybrid_uq.vocabulary.HybridUQError", refusal
    assert "contradict their own measurements" in refusal["message"]


def test_v3_moves_no_frozen_shape(manifest):
    """The audit fixes changed behaviour and records; the frozen API is exactly Core Freeze V2's."""
    v2_manifest = json.loads((REPO / core_freeze_v2.MANIFEST_PATH).read_bytes())
    assert manifest["api"] == v2_manifest["api"]
    assert manifest["api_identical_to_v2_manifest"] is True
    assert manifest["pinned_v2_snapshot_files"] == v2_manifest["pinned_v2_snapshot_files"]
    assert manifest["api"]["v1"]["frozen_digest"] == core_freeze_v2.V1_FROZEN_DIGEST


def test_v2_history_is_recorded_not_rewritten(manifest):
    blob = (REPO / core_freeze_v2.MANIFEST_PATH).read_bytes()
    assert manifest["v2_manifest_sha256"] == core_freeze_v2.sha256_bytes(blob)
    assert manifest["supersedes_v2_because"]


def test_the_self_contradicting_v2_identity_references_are_refused(manifest):
    """The supersession is measured, not asserted: V2's own fixture records no longer construct."""
    assert core_freeze_v3.v2_fixtures_refused()
    assert manifest["v2_fixtures_refused"]


def test_every_v3_record_round_trips_and_refuses_unknown_schemas(manifest):
    for name, entry in manifest["serialization_inventory"].items():
        assert entry["round_trip_byte_identical"] and entry["unknown_schema_refused"], name


def test_the_identity_references_are_refused_in_a_fresh_process_too(manifest):
    """AMENDED at V4. Was: V3's serialization facts reproduce byte-for-byte in a fresh process.

    They no longer reproduce at all -- building them raises, because the records are the ones this
    round refuses -- and the property worth asserting is the same one in the other direction: the
    refusal is not an artefact of this process's import order or hash seed. A fresh interpreter, with
    a different PYTHONHASHSEED, must refuse with the SAME rule (R-70: which rule fired is the claim).
    """
    script = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
              "from tools.certification import core_freeze_v3 as F; "
              "\ntry:\n    F.serialization_facts()\nexcept BaseException as exc:\n"
              "    print(type(exc).__module__ + '.' + type(exc).__qualname__); print(str(exc)[:200])\n"
              "else:\n    print('ACCEPTED')"
              ) % (str(REPO), str(REPO / "src"))
    env = {**os.environ, "PYTHONHASHSEED": "987",
           "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", script], cwd=REPO,
                         capture_output=True, text=True, check=True, env=env)
    lines = out.stdout.strip().splitlines()
    assert lines[0] == "engcore.hybrid_uq.vocabulary.HybridUQError", out.stdout
    assert "contradict their own measurements" in lines[1], out.stdout


def test_every_deferred_shape_change_is_a_stated_non_claim(manifest):
    deferred = [claim for claim in manifest["non_claims"] if claim.startswith("DEFERRED")]
    assert len(deferred) >= 4


def test_the_certificate_scope_covers_every_area_the_audit_found_a_false_accept_in(manifest):
    from tools.certification import core_certificate

    names = {area.name for area in core_certificate.SCOPE}
    assert set(core_freeze_v3.REQUIRED_CERTIFICATE_AREAS) <= names
    assert manifest["certificate"]["required_areas"] == list(core_freeze_v3.REQUIRED_CERTIFICATE_AREAS)


def test_the_command_line_verifier_agrees_with_the_function(manifest):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.certification.core_freeze_v3", "--verify"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8", env=env)
    expected = core_freeze_v3.verify(REPO).ok
    assert (proc.returncode == 0) == expected, proc.stdout[-2000:] + proc.stderr[-2000:]
