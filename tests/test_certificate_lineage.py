"""A certificate child is bound to its exact parent, and to the run that produced it.

Finding A of the certification trust-closure round. ``core_certificate --verify``
proves certified BYTES; it never proved the certificate was about the commit it
sits on. Every case here builds a synthetic repository, runs the real
source -> evidence -> assurance -> builder cycle, commits a certificate child,
and then breaks exactly one lineage fact.

Nothing here touches the checkout.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate
from tools.certification.certificate_lineage import (
    PARENT_BOUND_FIELDS,
    PROVENANCE_REQUIRED_JOBS,
    fetch_and_verify_provenance,
    provenance_problems,
    verify_certificate_child,
)
from tools.certification.hardening_assurance import WORKFLOW_PATH
from tools.certification.recertification_scope import CERTIFICATE_PATH


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)
    root = tmp_path / "repo"
    first = fx.make_repo(root)
    return root, first


@pytest.fixture
def certified(repo, tmp_path):
    """A source commit, its certificate, and the child that commits it."""
    root, first = repo
    fx.write(root, "src/engcore/scientific/record.py", "VALUE = 3\n")
    source = fx.commit(root, "core change")
    certificate = fx.certify(root, tmp_path / "evidence")
    child = fx.commit_child(root, certificate)
    return root, first, source, child, certificate


def failed(root):
    return set(verify_certificate_child(root, policy=fx.POLICY).failed())


def _recommit(root, certificate, **kwargs):
    fx.git(root, "reset", "-q", "--hard", "HEAD^")
    return fx.commit_child(root, certificate, **kwargs)


# ---- the exact parent ------------------------------------------------------------
def test_a_child_of_its_exact_parent_verifies(certified):
    root, _first, source, _child, certificate = certified
    result = verify_certificate_child(root, policy=fx.POLICY)
    assert result.ok, "\n" + result.render()
    for dotted in PARENT_BOUND_FIELDS:
        assert f"parent_binding.{dotted}" in {c.name for c in result.checks}
    assert certificate["repository"]["commit"] == source


# ---- 1-3: each commit field, stale on its own ---------------------------------------
@pytest.mark.parametrize("dotted", [
    "repository.commit",
    "assurance.source_commit",
    "assurance.environment.source_commit",
])
def test_a_stale_commit_field_fails_on_its_own(certified, dotted):
    root, first, _source, _child, certificate = certified
    stale = json.loads(json.dumps(certificate))
    *path, last = dotted.split(".")
    node = stale
    for key in path:
        node = node[key]
    node[last] = first
    _recommit(root, stale)
    # Exactly this check: bytes, scope and evidence all still agree, so only the
    # binding to the parent can be what refuses it.
    assert failed(root) == {f"parent_binding.{dotted}"}


@pytest.mark.parametrize("dotted", PARENT_BOUND_FIELDS)
def test_an_absent_commit_field_fails_rather_than_passes(certified, dotted):
    root, _first, _source, _child, certificate = certified
    stripped = json.loads(json.dumps(certificate))
    *path, last = dotted.split(".")
    node = stripped
    for key in path:
        node = node[key]
    del node[last]
    _recommit(root, stripped)
    assert f"parent_binding.{dotted}" in failed(root)


# ---- 4: a whole certificate from an older source, identical certified bytes ---------
def test_a_certificate_copied_from_an_older_source_with_identical_bytes_fails(repo, tmp_path):
    root, _first = repo
    older = fx.git(root, "rev-parse", "HEAD")
    old_certificate = fx.certify(root, tmp_path / "old-evidence")
    fx.write(root, "README.md", "a later commit that changes nothing certified\n")
    newer = fx.commit(root, "later, uncertified")
    fx.commit_child(root, old_certificate)

    # The bytes still agree -- which is exactly why byte verification was not enough.
    content = core_certificate.verify_certificate(root, old_certificate, require_commit=False)
    assert content.ok, content.render()
    assert old_certificate["repository"]["commit"] == older != newer

    result = verify_certificate_child(root, policy=fx.POLICY)
    assert not result.ok
    assert {f"parent_binding.{d}" for d in PARENT_BOUND_FIELDS} <= set(result.failed())


# ---- 5: more than one parent ------------------------------------------------------
def test_a_child_with_two_parents_fails(certified):
    root, _first, source, _child, certificate = certified
    fx.git(root, "reset", "-q", "--hard", source)
    fx.git(root, "checkout", "-q", "-b", "side")
    fx.write(root, "README.md", "side\n")
    fx.commit(root, "side")
    fx.git(root, "checkout", "-q", "-")
    fx.git(root, "merge", "-q", "--no-ff", "--no-commit", "side")
    fx.git(root, "checkout", "-q", source, "--", "README.md")
    core_certificate.write_certificate(root / CERTIFICATE_PATH, certificate)
    fx.git(root, "add", "-A")
    fx.git(root, "commit", "-q", "-m", "certification: recertify hardened core")
    assert len(fx.git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    assert "child.shape" in failed(root)


# ---- 6: a child that changes another file -------------------------------------------
def test_a_child_that_changes_another_file_fails(certified):
    root, _first, _source, _child, certificate = certified
    fx.git(root, "reset", "-q", "--hard", "HEAD^")
    fx.write(root, "README.md", "smuggled alongside the certificate\n")
    fx.git(root, "add", "README.md")
    fx.commit_child(root, certificate)
    assert "child.shape" in failed(root)


def test_a_child_that_changes_a_certified_file_fails_on_shape_and_bytes(certified):
    root, _first, _source, _child, certificate = certified
    fx.git(root, "reset", "-q", "--hard", "HEAD^")
    fx.write(root, "src/engcore/scientific/record.py", "VALUE = 99\n")
    fx.git(root, "add", "-A")
    fx.commit_child(root, certificate)
    assert {"child.shape", "certificate.content_and_scope"} <= failed(root)


def test_the_subject_alone_does_not_make_a_child(certified):
    root, _first, _source, _child, certificate = certified
    _recommit(root, certificate, subject="update certificate")
    assert "child.shape" in failed(root)


# ---- what else a child must be ----------------------------------------------------------
def test_an_uncommitted_edit_to_the_certificate_fails(certified):
    root, *_ = certified
    path = root / CERTIFICATE_PATH
    path.write_bytes(path.read_bytes().replace(b'"diagnostic": false', b'"diagnostic": false '))
    assert {"certificate.working_copy_is_committed_bytes", "child.checkout_is_head"} <= failed(root)


def test_a_diagnostic_certificate_fails(certified):
    root, _first, _source, _child, certificate = certified
    diagnostic = json.loads(json.dumps(certificate))
    diagnostic["diagnostic"] = True
    _recommit(root, diagnostic)
    assert "certificate.built_from_clean_tree" in failed(root)


def test_an_assurance_v2_record_is_refused_on_a_child(certified):
    root, _first, _source, _child, certificate = certified
    legacy = json.loads(json.dumps(certificate))
    legacy["assurance"]["schema"] = "forge.core_hardening_assurance/2"
    _recommit(root, legacy)
    assert "assurance.revalidated_against_tree" in failed(root)


def test_a_certificate_written_under_an_older_scope_fails(certified, monkeypatch):
    """Byte-valid over the scope it names, and silent about the control plane."""
    root, _first, _source, _child, certificate = certified
    fx.git(root, "reset", "-q", "--hard", "HEAD^")
    narrower = tuple(a for a in fx.SCOPE if a.name != "certification_control")
    monkeypatch.setattr(core_certificate, "SCOPE", narrower)
    old = core_certificate.build_certificate(root, certification_id="SYNTHETIC")
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)
    old["assurance"] = certificate["assurance"]
    fx.commit_child(root, old)

    assert core_certificate.verify_certificate(
        root, old, require_commit=False, require_current_scope=False
    ).ok, "the old-scope certificate should still agree byte-for-byte"
    assert failed(root) >= {"certificate.content_and_scope"}


def test_a_hand_edited_mutation_claim_fails_revalidation(certified):
    """``passed: true`` with a mutation missing from every shard is not a certificate."""
    root, _first, _source, _child, certificate = certified
    forged = json.loads(json.dumps(certificate))
    shard = forged["assurance"]["formal_guard_mutations"]["shards"]["3"]
    shard["selected_ids"] = shard["selected_ids"][:-1]
    shard["selected_count"] -= 1
    shard["killed_count"] -= 1
    _recommit(root, forged)
    assert "assurance.revalidated_against_tree" in failed(root)


def test_a_forged_control_plane_digest_fails_revalidation(certified):
    root, _first, _source, _child, certificate = certified
    forged = json.loads(json.dumps(certificate))
    forged["assurance"]["control_plane"]["digest"] = "0" * 64
    _recommit(root, forged)
    assert "assurance.revalidated_against_tree" in failed(root)


def test_a_merge_preview_with_different_certified_bytes_fails(certified):
    root, _first, _source, child, _certificate = certified
    fx.git(root, "checkout", "-q", "-b", "preview")
    fx.write(root, "tools/certification/verifier.py", "def verify():\n    return False\n")
    preview = fx.commit(root, "base moved the verifier")
    fx.git(root, "checkout", "-q", child)
    result = verify_certificate_child(root, policy=fx.POLICY, merge_preview=preview)
    assert "merge_preview.certified_bytes" in result.failed()
    assert verify_certificate_child(root, policy=fx.POLICY, merge_preview=child).ok


# ---- provenance: the certify run for the parent produced these bytes -------------------
def _run(source, **overrides):
    run = {"id": fx.RUN["run_id"], "run_attempt": 1, "path": WORKFLOW_PATH,
           "event": "pull_request", "head_sha": source,
           "repository": {"full_name": fx.RUN["repository"]}}
    run.update(overrides)
    return run


def _jobs(source, **states):
    return [{"name": name, "status": "completed", "conclusion": states.get(name, "success"),
             "head_sha": source} for name in PROVENANCE_REQUIRED_JOBS]


def _provenance(root, source, *, run=None, jobs=None, artifact=b"same"):
    committed = (root / CERTIFICATE_PATH).read_bytes()
    return provenance_problems(
        certificate_bytes=committed, source_commit=source, repository=fx.RUN["repository"],
        run=run if run is not None else _run(source),
        jobs=jobs if jobs is not None else _jobs(source),
        artifact_certificate=committed if artifact == b"same" else artifact,
    )


def test_provenance_accepts_the_run_that_uploaded_these_bytes(certified):
    root, _first, source, *_ = certified
    assert _provenance(root, source) == []


@pytest.mark.parametrize("override, fragment", [
    ({"head_sha": "0" * 40}, "measured"),
    ({"path": ".github/workflows/tests.yml"}, "ran workflow"),
    ({"event": "push"}, "triggered by"),
    ({"repository": {"full_name": "someone/else"}}, "belongs to"),
    ({"id": 1}, "GitHub returned run"),
    ({"run_attempt": 0}, "attempt"),
])
def test_provenance_refuses_a_run_that_is_not_the_parents_certify_run(certified, override, fragment):
    root, _first, source, *_ = certified
    problems = _provenance(root, source, run=_run(source, **override))
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize("job", ["fast311", "formal_mutations_2", "trust_mutations", "certify"])
def test_provenance_refuses_a_run_where_a_required_job_did_not_succeed(certified, job):
    root, _first, source, *_ = certified
    for state in ("failure", "skipped", "cancelled"):
        problems = _provenance(root, source, jobs=_jobs(source, **{job: state}))
        assert any(repr(job) in p for p in problems), problems


def test_provenance_refuses_a_run_missing_a_gate(certified):
    root, _first, source, *_ = certified
    jobs = [j for j in _jobs(source) if j["name"] != "scientific312"]
    assert any("'scientific312'" in p for p in _provenance(root, source, jobs=jobs))


def test_provenance_refuses_bytes_the_certify_job_did_not_upload(certified):
    root, _first, source, *_ = certified
    assert any("byte-identical" in p for p in _provenance(root, source, artifact=b"{}"))
    assert any("not found" in p for p in _provenance(root, source, artifact=None))


def test_fetching_provenance_waits_for_certify_and_reads_the_artifact(certified):
    root, _first, source, *_ = certified
    committed = (root / CERTIFICATE_PATH).read_bytes()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("current_core_v2.json", committed)
        handle.writestr("core-hardening-assurance.json", b"{}")
    calls, sleeps = [], []
    pending = _jobs(source)
    pending[-1] = {**pending[-1], "status": "in_progress", "conclusion": None}

    def gh(args):
        calls.append(args[0])
        path = args[0]
        if path.endswith(f"runs/{fx.RUN['run_id']}"):
            return json.dumps(_run(source)).encode()
        if "/jobs" in path:
            jobs = pending if len(sleeps) == 0 else _jobs(source)
            return json.dumps({"total_count": len(jobs), "jobs": jobs}).encode()
        if "/artifacts?" in path:
            return json.dumps({"artifacts": [{"id": 9, "name": f"hardened-core-assurance-{source}", "expired": False}]}).encode()
        if path.endswith("/artifacts/9/zip"):
            return archive.getvalue()
        raise AssertionError(path)

    problems = fetch_and_verify_provenance(
        root, repository=fx.RUN["repository"], timeout=60, interval=0, gh=gh, sleep=sleeps.append,
    )
    assert problems == [], problems
    assert sleeps, "provenance must wait for an in-progress certify job rather than judge it"
