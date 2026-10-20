# index-red-recorded

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "-m",
    "pytest",
    "C:/Users/dev_kaeem/AppData/Roaming/Claude/side-session-notes/local_dac3224f-3028-46a9-ab85-20d361143aa4/domain-reconcile-2026-10-20/test_staged_declarations.py",
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp=D:/tmp/domain-index-red-recorded/bt"
  ],
  "cwd": "C:/Users/dev_kaeem/.codex/worktrees/review-unmerged-work/wonderful-gould-1c576f",
  "environment": {
    "TMPDIR": "D:/tmp/domain-index-red-recorded",
    "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/review-unmerged-work/wonderful-gould-1c576f"
  },
  "exit_code": 1,
  "elapsed_seconds": 1.6640740999719128,
  "completed_utc": "2026-10-20T18:48:54.972177+00:00",
  "output_sha256": "579e2c1c768d34207c9d9f4f0030a598d14fcf4ec139419b806c24f9cbadb277"
}
```

```text
FFF                                                                      [100%]
================================== FAILURES ===================================
____ test_staged_and_working_declaration_inputs_must_agree[artifact.json] _____

tmp_path = WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar0')
changed = 'artifact.json'

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
>       assert not scan.reviewed_declarations(tmp_path, manifest)
E       AssertionError: assert not {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}}
E        +  where {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}} = <function reviewed_declarations at 0x00000178AADAD170>(WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar0'), WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar0/review.json'))
E        +    where <function reviewed_declarations at 0x00000178AADAD170> = <module '_staged_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\benchmarks\\domain_real_data\\audit\\inventory_scan.py'>.reviewed_declarations

..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py:38: AssertionError
_____ test_staged_and_working_declaration_inputs_must_agree[producer.py] ______

tmp_path = WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar1')
changed = 'producer.py'

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
>       assert not scan.reviewed_declarations(tmp_path, manifest)
E       AssertionError: assert not {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}}
E        +  where {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}} = <function reviewed_declarations at 0x00000178AADAEF00>(WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar1'), WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar1/review.json'))
E        +    where <function reviewed_declarations at 0x00000178AADAEF00> = <module '_staged_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\benchmarks\\domain_real_data\\audit\\inventory_scan.py'>.reviewed_declarations

..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py:38: AssertionError
_____ test_staged_and_working_declaration_inputs_must_agree[review.json] ______

tmp_path = WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar2')
changed = 'review.json'

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
>       assert not scan.reviewed_declarations(tmp_path, manifest)
E       AssertionError: assert not {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}}
E        +  where {'artifact.json': {'path': 'artifact.json', 'sha256': '1d7f9f961498e9da2a030376afc1b67a138e088765d2d663f94477e455b34db5', 'class': 'DERIVED', 'role': 'COMPUTE_ARTIFACT', ...}} = <function reviewed_declarations at 0x00000178AAE10A90>(WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar2'), WindowsPath('D:/tmp/domain-index-red-recorded/bt/test_staged_and_working_declar2/review.json'))
E        +    where <function reviewed_declarations at 0x00000178AAE10A90> = <module '_staged_scan' from 'C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\benchmarks\\domain_real_data\\audit\\inventory_scan.py'>.reviewed_declarations

..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py:38: AssertionError
=========================== short test summary info ===========================
FAILED ..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py::test_staged_and_working_declaration_inputs_must_agree[artifact.json]
FAILED ..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py::test_staged_and_working_declaration_inputs_must_agree[producer.py]
FAILED ..\..\..\..\AppData\Roaming\Claude\side-session-notes\local_dac3224f-3028-46a9-ab85-20d361143aa4\domain-reconcile-2026-10-20\test_staged_declarations.py::test_staged_and_working_declaration_inputs_must_agree[review.json]
3 failed in 1.19s

```
