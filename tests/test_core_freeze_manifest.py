"""Part 16: the Core Freeze V1 manifest verifies, and its verifier can fail.

The first test is the one that matters day to day: the checked-out tree IS
Core Freeze V1, or a descendant that kept its contract. Everything after it is
about the verifier rather than the tree -- each takes the real stored manifest,
breaks exactly one fact in a copy, and requires the verifier to fail on the
check that owns that fact. A verifier that passed every one of these copies
would be a verifier that compares nothing.

The tampered copies are held in memory. Nothing here writes to the manifest.
"""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / "certification" / "core_freeze_v1.json"

pytestmark = pytest.mark.skipif(
    not (REPO / ".git").exists(), reason="the freeze verifier reads git state"
)

from tools.certification import core_freeze  # noqa: E402


@pytest.fixture(scope="module")
def live():
    return core_freeze.collect_live(REPO)


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST.exists(), "certification/core_freeze_v1.json is missing"
    return json.loads(MANIFEST.read_bytes())


def failing(result) -> set[str]:
    return set(result.failed())


# =====================================================================
# the tree
# =====================================================================

def test_the_tree_is_core_freeze_v1(live):
    """Deliberately not softened on a dirty tree, like the certificate's test."""
    result = core_freeze.verify(REPO, live=live)
    assert result.ok, "\n" + result.render()


def test_the_tree_is_the_exact_freeze_or_a_contract_keeping_descendant(live, manifest):
    result = core_freeze.verify_manifest(manifest, live, require_clean=False)
    assert result.mode in ("EXACT_FREEZE", "DESCENDANT"), result.mode


def test_the_command_line_verifier_agrees_with_the_function(live):
    """`python -m tools.certification.core_freeze --verify` is the Part 16 command."""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "tools.certification.core_freeze",
         "--verify"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    )
    expected = core_freeze.verify(REPO, live=live).ok
    assert (proc.returncode == 0) == expected, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == ("OK" if expected else "FAILED")


# =====================================================================
# the frozen contract -- each fact, broken once
# =====================================================================

def test_a_changed_frozen_digest_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    broken["api"]["frozen_digest"] = "0" * 64
    assert "contract.api" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_silently_promoting_an_experimental_symbol_fails(live, manifest):
    """Part 5's forbidden move, done CONSISTENTLY so the internal checks pass.

    Dropping a symbol from the experimental list and raising the frozen count to
    match is exactly what a silent promotion looks like in a manifest someone
    edited carefully. The live facts must refuse it.
    """
    broken = copy.deepcopy(manifest)
    broken["api"]["experimental"] = broken["api"]["experimental"][1:]
    broken["api"]["experimental_count"] -= 1
    broken["api"]["frozen_count"] += 1
    broken["api"]["frozen_count_expected"] += 1
    failed = failing(core_freeze.verify_manifest(broken, live, require_clean=False))
    assert "contract.api" in failed
    assert "experimental.visibly_classified" in failed


def test_a_legacy_reader_losing_a_declared_version_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    readers = broken["contract"]["facts"]["serialization"]["legacy_readers"]
    readers["ProvenanceRecord"]["accepted_versions"] = (
        readers["ProvenanceRecord"]["accepted_versions"][1:]
    )
    assert "contract.serialization" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_a_changed_round_trip_inventory_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    broken["contract"]["facts"]["serialization"]["round_trippable_count"] = 62
    assert "contract.serialization" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_a_changed_material_digest_fails(live, manifest):
    """Digest SEMANTICS are frozen, so the reference digests are too."""
    broken = copy.deepcopy(manifest)
    broken["contract"]["facts"]["identity"]["reference"]["parameter"] = "f" * 64
    assert "contract.identity" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_a_changed_failure_order_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    order = broken["contract"]["facts"]["ordering"]["sequential"]["failure_order"]
    order.reverse()
    assert "contract.ordering" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_a_new_exception_family_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    broken["contract"]["facts"]["exceptions"]["roots"]["engcore.new.Root"] = 1
    assert "contract.exceptions" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_an_internally_inconsistent_manifest_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    broken["api"]["experimental_count"] = 10
    assert "manifest.internal_consistency" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


def test_a_changed_pinned_snapshot_file_fails(live, manifest):
    broken = copy.deepcopy(manifest)
    name = sorted(broken["api"]["pinned_files"])[0]
    broken["api"]["pinned_files"][name] = "0" * 64
    assert "bytes.pinned_contract_files" in failing(
        core_freeze.verify_manifest(broken, live, require_clean=False))


# =====================================================================
# exact freeze vs descendant
# =====================================================================

def test_a_descendant_that_keeps_the_contract_still_verifies(live, manifest):
    """The post-freeze policy made executable: `src/` may change, the contract may not.

    Simulated by changing the RECORDED src tree hash, which is what the verifier
    sees when a later commit refactors internals. The byte-level checks must
    become informational, and the contract checks must still bind and pass.
    """
    later = copy.deepcopy(manifest)
    later["trees"]["src"] = "0" * 40
    later["domain"]["digest"] = "0" * 64  # new domain work is allowed after a freeze
    result = core_freeze.verify_manifest(later, live, require_clean=False)
    assert result.mode == "DESCENDANT"
    assert result.ok, "\n" + result.render()
    informational = {c.name for c in result.checks if not c.binding}
    assert {"domain.digest", "bytes.reproduction_sha256"} <= informational


def test_on_the_exact_freeze_the_domain_digest_binds(live, manifest):
    broken = copy.deepcopy(manifest)
    broken["domain"]["digest"] = "0" * 64
    result = core_freeze.verify_manifest(broken, live, require_clean=False)
    if result.mode != "EXACT_FREEZE":
        pytest.skip("this tree is a descendant; the domain digest is informational")
    assert "domain.digest" in failing(result)


def test_a_descendant_that_breaks_the_contract_fails(live, manifest):
    later = copy.deepcopy(manifest)
    later["trees"]["src"] = "0" * 40
    later["api"]["frozen_digest"] = "0" * 64
    result = core_freeze.verify_manifest(later, live, require_clean=False)
    assert result.mode == "DESCENDANT"
    assert "contract.api" in failing(result)


# =====================================================================
# the assurance record
# =====================================================================

def test_an_assurance_record_for_a_different_manifest_fails(live, manifest):
    result = core_freeze.verify_manifest(manifest, live, require_clean=False)
    core_freeze.verify_assurance(
        {"schema": core_freeze.ASSURANCE_SCHEMA, "manifest_sha256": "0" * 64,
         "tag": manifest["freeze"]["tag"], "candidate_commit": live.head,
         "evidence": {}, "results": {}},
        MANIFEST.read_bytes(), manifest, live, result, changed_paths=[],
    )
    assert "assurance.manifest_sha256" in failing(result)


def test_code_changed_after_the_assured_candidate_fails(live, manifest):
    """The property that makes the tagged src/ provably the assured src/."""
    exact = copy.deepcopy(manifest)
    exact["trees"] = dict(live.trees)  # force EXACT mode for this check
    result = core_freeze.verify_manifest(exact, live, require_clean=False)
    core_freeze.verify_assurance(
        {"schema": core_freeze.ASSURANCE_SCHEMA,
         "manifest_sha256": core_freeze.sha256_bytes(MANIFEST.read_bytes()),
         "tag": manifest["freeze"]["tag"], "candidate_commit": live.head,
         "evidence": {}, "results": {}},
        MANIFEST.read_bytes(), exact, live, result,
        changed_paths=["src/engcore/scientific/units/quantity.py"],
    )
    assert "assurance.post_candidate_changes_are_evidence_only" in failing(result)


def test_no_post_candidate_path_is_code_or_a_test():
    for path in core_freeze.POST_CANDIDATE_PATHS:
        assert not path.startswith(("src/", "tests/", "tools/")), path
        assert not path.endswith(".py"), path


# =====================================================================
# what the manifest says about itself
# =====================================================================

def test_the_manifest_records_the_blocked_candidate(manifest):
    blocked = manifest["freeze"]["blocked_candidates"]
    assert [b["commit"] for b in blocked] == [core_freeze.FINAL_FREEZE_BASELINE]
    assert blocked[0]["verdict"] == "FREEZE_BLOCKED"


def test_the_manifest_freezes_exactly_194_and_excludes_exactly_the_eleven(manifest):
    assert manifest["api"]["frozen_count"] == 194
    assert sorted(map(tuple, manifest["api"]["experimental"])) == sorted([
        ("engcore.inference", "FieldObservationError"),
        ("engcore.inference", "FieldObservationKind"),
        ("engcore.inference", "FieldObservationOperator"),
        ("engcore.studies", "TCR_MODEL_REF"),
        ("engcore.studies", "TcrTruth"),
        ("engcore.studies", "build_tcr_parameter_set"),
        ("engcore.studies", "ols_reference_estimate"),
        ("engcore.studies", "synthesize_tcr_observations"),
        ("engcore.studies", "tcr_forward_evaluator"),
        ("engcore.studies", "tcr_forward_table"),
        ("engcore.studies", "tcr_prediction"),
    ])


def test_the_manifest_states_its_non_claims(manifest):
    text = " ".join(manifest["non_claims"])
    for required in ("EXPERIMENTAL != FROZEN", "error prose", "EI/RI/FM/SP",
                     "seven exception roots", "unsupported checkout alias"):
        assert required in text, required


def test_the_manifest_carries_the_change_policy(manifest):
    policy = manifest["change_policy"]
    assert set(policy) == {
        "allowed_without_breaking_freeze",
        "requires_core_compatibility_review",
        "requires_new_core_freeze_version",
    }
    assert "silently promoting" in manifest["experimental_policy"]["forbidden"]


def test_every_reference_exists(manifest):
    missing = [
        ref["path"] for ref in manifest["references"].values()
        if not (REPO / ref["path"]).exists()
        and ref["path"] not in (core_freeze.ASSURANCE_PATH, core_freeze.REPORT_PATH)
    ]
    assert not missing, missing
