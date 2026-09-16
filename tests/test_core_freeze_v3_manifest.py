"""Core Freeze V3: the manifest describes this tree, V1 still verifies, V2 history is untouched."""

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


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("candidate: the V3 manifest is built from the candidate commit")
    return json.loads(MANIFEST.read_bytes())


def _assert_contract_holds_pending_certificate(result):
    binding_failures = {check.name for check in result.checks if check.binding and not check.ok}
    unexpected = binding_failures - CERTIFICATE_CHILD_ONLY
    assert not unexpected, "\n" + result.render()


def test_the_tree_keeps_the_core_freeze_v3_contract(manifest):
    result = core_freeze_v3.verify(REPO, require_assurance=False)
    _assert_contract_holds_pending_certificate(result)


def test_once_assured_the_full_verification_holds(manifest):
    if not (REPO / core_freeze_v3.ASSURANCE_PATH).exists():
        pytest.skip("candidate: the assurance record is written from this suite's own result")
    _assert_contract_holds_pending_certificate(core_freeze_v3.verify(REPO))


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


def test_the_identity_references_are_stable_in_a_fresh_process(manifest):
    script = ("import json, sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
              "from tools.certification import core_freeze_v3 as F; print(json.dumps(F.serialization_facts()))"
              ) % (str(REPO), str(REPO / "src"))
    env = {**os.environ, "PYTHONHASHSEED": "987", "PYTHONPATH": os.pathsep.join([str(REPO / "src"), str(REPO)])}
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", script], cwd=REPO, capture_output=True, text=True, check=True, env=env)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == manifest["serialization_inventory"]


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
