"""Failing-first staged-tree counterexamples; copied into the suite after FAST ends."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

SCANNER = Path(__file__).resolve().parents[1] / "audit" / "inventory_scan.py"


@pytest.mark.parametrize("changed", ["artifact.json", "producer.py", "review.json"])
def test_staged_and_working_declaration_inputs_must_agree(tmp_path, changed):
    spec = importlib.util.spec_from_file_location("_staged_scan", SCANNER)
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    (tmp_path/"artifact.json").write_bytes(b'{"result": 1}\n')
    (tmp_path/"producer.py").write_bytes(b"# original producer\n")
    def pin(name):
        return {"path":name, "sha256":hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()}
    record = {**pin("artifact.json"), "class":"DERIVED", "role":"COMPUTE_ARTIFACT",
              "rationale":"Reviewed test output, not physical evidence.",
              "evidence":[pin("producer.py")]}
    manifest = tmp_path/"review.json"
    manifest.write_bytes(json.dumps({"schema":"domain_real_data_provenance_review/1",
                                    "review_base":"3"*40, "records":[record]}).encode())
    git("add", ".")
    assert "artifact.json" in scan.reviewed_declarations(tmp_path, manifest)
    file = tmp_path/changed
    reviewed = file.read_bytes()
    file.write_bytes(b"unreviewed staged bytes")
    git("add", changed)
    file.write_bytes(reviewed)
    assert not scan.reviewed_declarations(tmp_path, manifest)
