# Executed boundary-red

Original captured log SHA256: fd0a36185fa0dae35ba486891232b68a1e0f34860f4e7126eb34fee01d61b505

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
    "--basetemp=D:/tmp/domain-boundary-red"
  ],
  "cwd": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f",
  "exit_code": 1
}
```

```text
FFFFFF                                                                   [100%]
================================== FAILURES ===================================
_ test_new_file_has_unknown_provenance_even_under_known_prefix[docs/new_measurements.csv] _

path = 'docs/new_measurements.csv'

    @pytest.mark.parametrize("path", [
        "docs/new_measurements.csv",
        "benchmarks/new_measurements.csv",
        "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv",
    ])
    def test_new_file_has_unknown_provenance_even_under_known_prefix(path):
>       assert scanner().classify(path)[1] == "UNKNOWN_PROVENANCE"
E       AssertionError: assert 'DERIVED' == 'UNKNOWN_PROVENANCE'
E         
E         - UNKNOWN_PROVENANCE
E         + DERIVED

benchmarks\domain_real_data\tests\test_inventory_boundary.py:24: AssertionError
_ test_new_file_has_unknown_provenance_even_under_known_prefix[benchmarks/new_measurements.csv] _

path = 'benchmarks/new_measurements.csv'

    @pytest.mark.parametrize("path", [
        "docs/new_measurements.csv",
        "benchmarks/new_measurements.csv",
        "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv",
    ])
    def test_new_file_has_unknown_provenance_even_under_known_prefix(path):
>       assert scanner().classify(path)[1] == "UNKNOWN_PROVENANCE"
E       AssertionError: assert 'DERIVED' == 'UNKNOWN_PROVENANCE'
E         
E         - UNKNOWN_PROVENANCE
E         + DERIVED

benchmarks\domain_real_data\tests\test_inventory_boundary.py:24: AssertionError
_ test_new_file_has_unknown_provenance_even_under_known_prefix[benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv] _

path = 'benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv'

    @pytest.mark.parametrize("path", [
        "docs/new_measurements.csv",
        "benchmarks/new_measurements.csv",
        "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv",
    ])
    def test_new_file_has_unknown_provenance_even_under_known_prefix(path):
>       assert scanner().classify(path)[1] == "UNKNOWN_PROVENANCE"
E       AssertionError: assert 'REAL_MEASURED' == 'UNKNOWN_PROVENANCE'
E         
E         - UNKNOWN_PROVENANCE
E         + REAL_MEASURED

benchmarks\domain_real_data\tests\test_inventory_boundary.py:24: AssertionError
______________ test_historical_scan_replays_exact_original_bytes ______________

    def test_historical_scan_replays_exact_original_bytes():
        scan = scanner()
>       assert scan.render(scan.historical_scan()) == scan.OUT.read_bytes()
                           ^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module '_inventory_boundary' has no attribute 'historical_scan'

benchmarks\domain_real_data\tests\test_inventory_boundary.py:29: AttributeError
_________________ test_missing_historical_object_fails_closed _________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x000002389F7AF5C0>

    def test_missing_historical_object_fails_closed(monkeypatch):
        scan = scanner()
>       monkeypatch.setattr(scan, "HISTORICAL_COMMIT", "0" * 40)
E       AttributeError: <module '_inventory_boundary' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\benchmarks\\domain_real_data\\audit\\inventory_scan.py'> has no attribute 'HISTORICAL_COMMIT'

benchmarks\domain_real_data\tests\test_inventory_boundary.py:34: AttributeError
_____ test_modified_registered_measurement_cannot_keep_historical_credit ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x000002389F8D42B0>

    def test_modified_registered_measurement_cannot_keep_historical_credit(monkeypatch):
        scan = scanner()
        path = "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/549_Dis_2C.csv"
        original = scan._git
    
        def changed(*args):
            if args[:2] == ("diff", "--name-only"):
                return [path]
            return original(*args)
    
        monkeypatch.setattr(scan, "_git", changed)
>       assert scan.classify(path)[1] == "UNKNOWN_PROVENANCE"
E       AssertionError: assert 'REAL_MEASURED' == 'UNKNOWN_PROVENANCE'
E         
E         - UNKNOWN_PROVENANCE
E         + REAL_MEASURED

benchmarks\domain_real_data\tests\test_inventory_boundary.py:50: AssertionError
=========================== short test summary info ===========================
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_new_file_has_unknown_provenance_even_under_known_prefix[docs/new_measurements.csv]
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_new_file_has_unknown_provenance_even_under_known_prefix[benchmarks/new_measurements.csv]
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_new_file_has_unknown_provenance_even_under_known_prefix[benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/new_measurements.csv]
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_historical_scan_replays_exact_original_bytes
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_missing_historical_object_fails_closed
FAILED benchmarks/domain_real_data/tests/test_inventory_boundary.py::test_modified_registered_measurement_cannot_keep_historical_credit
6 failed in 0.10s

```
