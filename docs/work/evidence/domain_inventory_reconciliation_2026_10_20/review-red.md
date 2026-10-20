# Executed review-red

Captured log SHA256: 4490535a0c36fc0879eb727adf91aca1141e8350b65e25c78214ffde8529c6c3

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "-m",
    "pytest",
    "benchmarks/domain_real_data/tests/test_inventory_boundary.py",
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp=D:/tmp/domain-review-red"
  ],
  "exit_code": 1,
  "cwd": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f"
}
```

```text
.....F..F                                                                [100%]
================================== FAILURES ===================================
____________ test_unicode_staged_addition_is_enumerated_as_unknown ____________

git_inventory = (<module '_inventory_boundary' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c.../domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv', <function git_inventory.<locals>.git at 0x00000281D4CA7690>)

    def test_unicode_staged_addition_is_enumerated_as_unknown(git_inventory):
        scan, root, _, git = git_inventory
        path = "docs/\u0642\u064a\u0627\u0633.csv"
        (root / "docs").mkdir()
        (root / path).write_bytes(b"not reviewed\n")
        git("add", ".")
        report = scan.scan()
>       assert any(path in g.get("files", []) and g["class"] == "UNKNOWN_PROVENANCE"
                   for g in report["groups"])
E       assert False
E        +  where False = any(<generator object test_unicode_staged_addition_is_enumerated_as_unknown.<locals>.<genexpr> at 0x00000281D4CA22F0>)

benchmarks\domain_real_data\tests\test_inventory_boundary.py:72: AssertionError
---------------------------- Captured stderr setup ----------------------------
warning: in the working copy of 'benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv', LF will be replaced by CRLF the next time Git touches it
---------------------------- Captured stderr call -----------------------------
warning: in the working copy of 'benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv', LF will be replaced by CRLF the next time Git touches it\nwarning: in the working copy of 'docs/\u0642\u064a\u0627\u0633.csv', LF will be replaced by CRLF the next time Git touches it
__________ test_assume_unchanged_does_not_hide_modified_measurement ___________

git_inventory = (<module '_inventory_boundary' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c.../domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv', <function git_inventory.<locals>.git at 0x00000281D4C7F5E0>)

    def test_assume_unchanged_does_not_hide_modified_measurement(git_inventory):
        scan, root, path, git = git_inventory
        git("update-index", "--assume-unchanged", path)
        (root / path).write_bytes(b"changed behind index flag\n")
>       assert scan.classify(path)[1] == "UNKNOWN_PROVENANCE"
E       AssertionError: assert 'REAL_MEASURED' == 'UNKNOWN_PROVENANCE'
E         
E         - UNKNOWN_PROVENANCE
E         + REAL_MEASURED

benchmarks\domain_real_data\tests\test_inventory_boundary.py:89: AssertionError
---------------------------- Captured stderr setup ----------------------------
warning: in the working copy of 'benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/sample.csv', LF will be replaced by CRLF the next time Git touches it
=========================== short test summary info ===========================
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_unicode_staged_addition_is_enumerated_as_unknown
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_assume_unchanged_does_not_hide_modified_measurement
2 failed, 7 passed in 1.28s

```
