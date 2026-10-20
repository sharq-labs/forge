"""Inventory declarations are specific to both artifact bytes and their sources."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


def digest(body):
    return hashlib.sha256(body).hexdigest()


@pytest.fixture
def declaration(tmp_path):
    path = Path(__file__).resolve().parents[1] / "audit" / "inventory_scan.py"
    spec = importlib.util.spec_from_file_location("_decl_scan", path)
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    target = tmp_path / "artifact.json"
    evidence = tmp_path / "producer.py"
    target.write_bytes(b'{"origin": "generated"}\n')
    evidence.write_bytes(b"# audited producer\n")
    record = {
        "path": "artifact.json", "sha256": digest(target.read_bytes()),
        "class": "DERIVED", "role": "COMPUTE_ARTIFACT",
        "rationale": "Reviewed output of the pinned producer; no validation claim.",
        "evidence": [{"path": "producer.py", "sha256": digest(evidence.read_bytes())}],
    }
    manifest = tmp_path / "review.json"
    manifest.write_bytes(json.dumps({
        "schema": "domain_real_data_provenance_review/1",
        "review_base": "3" * 40, "records": [record],
    }).encode())
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "core.autocrlf", "false"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    return scan, tmp_path, manifest, target, evidence, record


def test_specific_matching_artifact_and_source_are_accepted(declaration):
    scan, root, manifest, _, _, _ = declaration
    assert scan.reviewed_declarations(root, manifest)["artifact.json"]["class"] == "DERIVED"


@pytest.mark.parametrize("which", ["artifact", "source"])
def test_changed_artifact_or_source_invalidates_declaration(declaration, which):
    scan, root, manifest, target, evidence, _ = declaration
    (target if which == "artifact" else evidence).write_bytes(b"changed")
    assert not scan.reviewed_declarations(root, manifest)


def test_duplicate_declaration_refused(declaration):
    scan, root, manifest, _, _, record = declaration
    doc = json.loads(manifest.read_bytes())
    doc["records"].append(record)
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="duplicate"):
        scan.reviewed_declarations(root, manifest)


def test_physical_or_reference_class_requires_registry_evidence(declaration):
    scan, root, manifest, _, _, _ = declaration
    doc = json.loads(manifest.read_bytes())
    doc["records"][0]["class"] = "REAL_MEASURED"
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="dataset_record"):
        scan.reviewed_declarations(root, manifest)


def test_archived_source_is_bound_to_full_commit_not_current_working_bytes(declaration):
    scan, root, manifest, _, evidence, _ = declaration
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "producer.py"], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
        "user.email=fixture@example.invalid", "commit", "-qm", "source",
    ], check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    doc = json.loads(manifest.read_bytes())
    doc["records"][0]["evidence"][0]["commit"] = commit
    manifest.write_text(json.dumps(doc))
    subprocess.run(["git", "-C", str(root), "add", "review.json"], check=True)
    evidence.write_bytes(b"later source revision")
    assert "artifact.json" in scan.reviewed_declarations(root, manifest)
    doc["records"][0]["evidence"][0]["commit"] = "HEAD"
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="immutable"):
        scan.reviewed_declarations(root, manifest)
