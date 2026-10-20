# Executed declarations-red

Captured log SHA256: 306e96fe74568064b3e5edc4884be6788e5fdbd797caa0ea0ed18e6721697fa1

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "-m",
    "pytest",
    "benchmarks/domain_real_data/tests/test_provenance_declarations.py",
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp=D:/tmp/domain-declarations-red"
  ],
  "cwd": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f",
  "exit_code": 1
}
```

```text
FFFFF                                                                    [100%]
================================== FAILURES ===================================
___________ test_specific_matching_artifact_and_source_are_accepted ___________

declaration = (<module '_decl_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\ben...74572b5ff98a4d9ced82a6a762dc7bd7a37e6063a834f7748cb51301d286bb4', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...})

    def test_specific_matching_artifact_and_source_are_accepted(declaration):
        scan, root, manifest, _, _, _ = declaration
>       assert scan.reviewed_declarations(root, manifest)["artifact.json"]["class"] == "DERIVED"
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module '_decl_scan' has no attribute 'reviewed_declarations'

benchmarks\domain_real_data\tests\test_provenance_declarations.py:40: AttributeError
______ test_changed_artifact_or_source_invalidates_declaration[artifact] ______

declaration = (<module '_decl_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\ben...74572b5ff98a4d9ced82a6a762dc7bd7a37e6063a834f7748cb51301d286bb4', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...})
which = 'artifact'

    @pytest.mark.parametrize("which", ["artifact", "source"])
    def test_changed_artifact_or_source_invalidates_declaration(declaration, which):
        scan, root, manifest, target, evidence, _ = declaration
        (target if which == "artifact" else evidence).write_bytes(b"changed")
>       assert not scan.reviewed_declarations(root, manifest)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module '_decl_scan' has no attribute 'reviewed_declarations'

benchmarks\domain_real_data\tests\test_provenance_declarations.py:47: AttributeError
_______ test_changed_artifact_or_source_invalidates_declaration[source] _______

declaration = (<module '_decl_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\ben...74572b5ff98a4d9ced82a6a762dc7bd7a37e6063a834f7748cb51301d286bb4', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...})
which = 'source'

    @pytest.mark.parametrize("which", ["artifact", "source"])
    def test_changed_artifact_or_source_invalidates_declaration(declaration, which):
        scan, root, manifest, target, evidence, _ = declaration
        (target if which == "artifact" else evidence).write_bytes(b"changed")
>       assert not scan.reviewed_declarations(root, manifest)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module '_decl_scan' has no attribute 'reviewed_declarations'

benchmarks\domain_real_data\tests\test_provenance_declarations.py:47: AttributeError
_____________________ test_duplicate_declaration_refused ______________________

declaration = (<module '_decl_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\ben...74572b5ff98a4d9ced82a6a762dc7bd7a37e6063a834f7748cb51301d286bb4', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...})

    def test_duplicate_declaration_refused(declaration):
        scan, root, manifest, _, _, record = declaration
        doc = json.loads(manifest.read_bytes())
        doc["records"].append(record)
        manifest.write_text(json.dumps(doc))
        with pytest.raises(ValueError, match="duplicate"):
>           scan.reviewed_declarations(root, manifest)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module '_decl_scan' has no attribute 'reviewed_declarations'

benchmarks\domain_real_data\tests\test_provenance_declarations.py:56: AttributeError
_________ test_physical_or_reference_class_requires_registry_evidence _________

declaration = (<module '_decl_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\ben...74572b5ff98a4d9ced82a6a762dc7bd7a37e6063a834f7748cb51301d286bb4', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...})

    def test_physical_or_reference_class_requires_registry_evidence(declaration):
        scan, root, manifest, _, _, _ = declaration
        doc = json.loads(manifest.read_bytes())
        doc["records"][0]["class"] = "REAL_MEASURED"
        manifest.write_text(json.dumps(doc))
        with pytest.raises(ValueError, match="dataset_record"):
>           scan.reviewed_declarations(root, manifest)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^
E           AttributeError: module '_decl_scan' has no attribute 'reviewed_declarations'

benchmarks\domain_real_data\tests\test_provenance_declarations.py:65: AttributeError
=========================== short test summary info ===========================
FAILED benchmarks/domain_real_data/tests/test_provenance_declarations.py::test_specific_matching_artifact_and_source_are_accepted
FAILED benchmarks/domain_real_data/tests/test_provenance_declarations.py::test_changed_artifact_or_source_invalidates_declaration[artifact]
FAILED benchmarks/domain_real_data/tests/test_provenance_declarations.py::test_changed_artifact_or_source_invalidates_declaration[source]
FAILED benchmarks/domain_real_data/tests/test_provenance_declarations.py::test_duplicate_declaration_refused
FAILED benchmarks/domain_real_data/tests/test_provenance_declarations.py::test_physical_or_reference_class_requires_registry_evidence
5 failed in 0.10s

```
