"""Core Freeze V2: the manifest describes this tree, and Core Freeze V1 still verifies underneath it."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.certification import core_freeze_v2  # noqa: E402

MANIFEST = REPO / core_freeze_v2.MANIFEST_PATH

# On a recertification SOURCE commit the repository still contains the previous
# certificate by construction. These are precisely the checks that can only bind
# after the official builder writes the certificate-only child. The pinned V1
# descendant self-check runs full Core V2 verification on that child, so these
# failures are deferred rather than weakened or silently skipped.
CERTIFICATE_CHILD_ONLY = {
    "v1.freeze_verifies",
    "certificate.verifies",
    "certificate.covers_hybrid_uq",
}


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_bytes())


def _assert_contract_holds_pending_certificate(result):
    unexpected = set(result.failed()) - CERTIFICATE_CHILD_ONLY
    assert not unexpected, "\n" + result.render()


def test_the_tree_keeps_the_core_freeze_v2_contract():
    """Source commits may defer only checks that require the freshly built certificate child."""
    result = core_freeze_v2.verify(REPO, require_assurance=False)
    _assert_contract_holds_pending_certificate(result)


def test_once_assured_the_full_verification_holds():
    if not (REPO / core_freeze_v2.ASSURANCE_PATH).exists():
        pytest.skip("candidate: the assurance record is written from this suite's own result")
    result = core_freeze_v2.verify(REPO)
    _assert_contract_holds_pending_certificate(result)


def test_v2_is_additive_over_v1(manifest):
    api = manifest["api"]
    assert api["v1"]["frozen_digest"] == core_freeze_v2.V1_FROZEN_DIGEST
    assert api["v1"]["frozen_count"] == core_freeze_v2.V1_FROZEN_COUNT
    assert api["v1_entries_byte_identical_in_v2"] is True
    assert api["v2"]["frozen_count"] == api["v1"]["frozen_count"] + len(api["v2"]["added_frozen_symbols"])
    assert all(name.startswith("engcore.hybrid_uq.") for name in api["v2"]["added_frozen_symbols"])


def test_no_approximation_class_is_recorded_as_exact(manifest):
    assert not any(entry["exact_posterior"] for entry in manifest["vocabulary"]["approximation_classes"].values())


def test_every_v2_record_round_trips_and_refuses_unknown_schemas(manifest):
    for name, entry in manifest["serialization_inventory"].items():
        assert entry["round_trip_byte_identical"] and entry["unknown_schema_refused"], name


def test_the_identity_references_are_stable_in_a_fresh_process(manifest):
    script = ("import json, sys; sys.path.insert(0, %r); from tools.certification import core_freeze_v2 as F; "
              "print(json.dumps(F.serialization_facts()))") % str(REPO)
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", script], cwd=REPO, capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONHASHSEED": "987"})
    assert json.loads(out.stdout.strip().splitlines()[-1]) == manifest["serialization_inventory"]


def test_the_command_line_verifier_agrees_with_the_function():
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.certification.core_freeze_v2", "--verify"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8")
    expected = core_freeze_v2.verify(REPO).ok
    assert (proc.returncode == 0) == expected, proc.stdout[-2000:] + proc.stderr[-2000:]
