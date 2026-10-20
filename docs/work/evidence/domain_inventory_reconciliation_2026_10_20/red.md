# Executed red

Original captured log SHA256: 0fa66cd2070f3fa8a791ceaa56398130d65860ced0b255cfaadd03301c91ad25

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "-m",
    "pytest",
    "benchmarks/domain_real_data/tests/test_domain_real_data.py",
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp=D:/tmp/domain-reconcile-red"
  ],
  "cwd": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f",
  "exit_code": 1,
  "seconds": 0.8685879000695422,
  "base": "3213bb35b2e222c5eddd86012aa8e179cee6c4a6",
  "merged_branch": "a80b4df5e4cb6e0cdfc4e4e87f9f09d13a7823db",
  "env": {
    "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f",
    "TMPDIR": "D:/tmp"
  }
}
```

```text
.........F...                                                            [100%]
================================== FAILURES ===================================
_______________________ test_repository_scan_is_current _______________________

    def test_repository_scan_is_current():
        scan = _load("_drd_scan", ROUND / "audit" / "inventory_scan.py")
>       assert scan.render(scan.scan()) == scan.OUT.read_bytes()
E       assert b'{\n "schema...n  }\n ]\n}\n' == b'{\n "schema...n  }\n ]\n}\n'
E         
E         At index 600 diff: b'5' != b'1'
E         Use -v to get more diff

benchmarks\domain_real_data\tests\test_domain_real_data.py:137: AssertionError
=========================== short test summary info ===========================
FAILED benchmarks/domain_real_data/tests/test_domain_real_data.py::test_repository_scan_is_current
1 failed, 12 passed in 0.45s

```
