# Executed fixed

Original captured log SHA256: ed63f04ebfe0f1e91c80b30134d4b17adf37e13fc3892d639676b2e43de39b6e

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "-m",
    "pytest",
    "benchmarks/domain_real_data/tests",
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp=D:/tmp/domain-boundary-fixed"
  ],
  "cwd": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f",
  "exit_code": 1
}
```

```text
.......F..F.........                                                     [100%]
================================== FAILURES ===================================
________________ test_synthetic_data_is_never_called_measured _________________

    def test_synthetic_data_is_never_called_measured():
        scan = _load("_drd_live_scan", ROUND / "audit" / "inventory_scan.py").scan()
        measured = [p for g in scan["groups"] if g["class"] == "REAL_MEASURED" for p in g["files"]]
        for path in measured:
            assert not re.search(r"cases_|/truth|oracle|synthetic|experiments/", path), path
>       assert scan["unknown_provenance_files"] == 0
E       assert 433 == 0

benchmarks\domain_real_data\tests\test_domain_real_data.py:123: AssertionError
_______ test_current_repository_inventory_has_no_unreviewed_provenance ________

    def test_current_repository_inventory_has_no_unreviewed_provenance():
        scan = _load("_drd_current_scan", ROUND / "audit" / "inventory_scan.py").scan()
        unknown = [g for g in scan["groups"] if g["class"] == "UNKNOWN_PROVENANCE"]
>       assert not unknown, unknown
E       AssertionError: [{'rule_prefix': '', 'class': 'UNKNOWN_PROVENANCE', 'role': 'UNREVIEWED_CHANGE', 'rationale': 'new or changed bytes need explicit provenance review', ...}]
E       assert not [{'rule_prefix': '', 'class': 'UNKNOWN_PROVENANCE', 'role': 'UNREVIEWED_CHANGE', 'rationale': 'new or changed bytes need explicit provenance review', ...}]

benchmarks\domain_real_data\tests\test_domain_real_data.py:143: AssertionError
=========================== short test summary info ===========================
FAILED benchmarks/domain_real_data/tests/test_domain_real_data.py::test_synthetic_data_is_never_called_measured
FAILED benchmarks/domain_real_data/tests/test_domain_real_data.py::test_current_repository_inventory_has_no_unreviewed_provenance
2 failed, 18 passed in 1.83s

```
