# Windows infrastructure fixtures — bounded repair, 2026-10-28

## Scope and source

Owner requested the remaining Windows-compatible repairs without interfering
with the other session's discovery/analysis work. This continuation changes
only `tests/test_local_assurance.py` and `tests/test_mutation_startup.py`, plus
this execution record and an append-only PROGRESS entry. No production guard,
scientific code, certification artifact, global setting or dependency changed.
The previous timing-fixture repair remains in the shared working tree.

Base HEAD `dd567d53d2444950f57ffaeb9903c74d7c38f04d`, local main; dirty, concurrently
edited checkout. Native Windows, existing CPython 3.11.15 `.venv`. This is a
bounded fixture result, not certification of HEAD or of the concurrent changes.
Logs and exact relevant file hashes are in the ignored local directory
`.forge/mvp-2026-10-28/` under `windows-fixtures-*` names. Export them as needed
for delivery; ignored logs are not preserved by a Git commit.

## Reproduced defects and corrections

1. Two interpreter-identity tests created extensionless `python` fixtures.
   Windows does not set the executable stat bits from chmod as POSIX does.
   Naming these fixtures `python.exe` satisfies the existing precondition;
   chmod and all identity/replacement assertions remain. These files are
   synthetic bytes, not interpreters whose execution has been demonstrated.
2. The source-orchestration fixture wrote `.gitignore` through newline-translating
   text I/O. With current Git autocrlf=true, raw working bytes differed from the
   index before the first gate. Write explicit LF bytes, retaining the strict
   clean-tree check and its final assertions. No Git configuration changed.
3. The forbidden-call trap for `killpg` assumed the attribute already exists.
   `monkeypatch.setattr(..., raising=False)` installs the same failing trap on
   Windows too; it does not permit group kills or modify production behavior.
4. After (2), orchestration reached `OwnedRoot` and exposed another invalid
   positive-fixture precondition: inherited TEMP was
   `C:\Users\DEV_KA~1\AppData\Local\Temp`, which resolves to a different spelling.
   The guard refuses such aliases. An opt-in fixture supplies resolved pytest
   temporary storage for the two positive orchestration families, including
   failure-injection variants. Ownership checks remain intact; repository-local
   scratch refusal and retention tests are unchanged.

No assertions removed, tolerances widened, skips added, or historical evidence
rewritten. The source-gate orchestration tests mock `_run`; their printed gate
names do NOT mean a campaign or full assurance ran.

## Executed commands and results

From repository root, executable `.venv/Scripts/python.exe`:

```text
-m pytest
 tests/test_mutation_startup.py::test_environment_snapshot_is_independent_of_parent_and_each_child
 tests/test_mutation_startup.py::test_interpreter_replacement_is_refused_with_same_size
 tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout
 tests/test_local_assurance.py::test_child_exit_during_forced_kill_preserves_stream_error
 -q --tb=short
```

- Before corrections: **9 failed in 2.14 s**, `windows-fixtures-red.log`.
- After corrections 1–3: **6 failed, 3 passed in 8.97 s**,
  `windows-fixtures-green.log`. Despite that filename, this intermediate run
  is RED: the remaining six failures exposed the TEMP alias issue.

Final verification after correction 4:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_local_assurance.py tests/test_mutation_startup.py -q --tb=short
git diff --check -- tests/test_local_assurance.py tests/test_mutation_startup.py tests/test_test_timing.py
```

**56 passed, 1 failed, 4 existing skips in 27.99 s**; pytest exit 1.
Log: `windows-fixtures-suite.log`. Diff check exit 0.
The sole remaining failure in these modules is
`tests/test_mutation_startup.py::test_venv_interpreter_symlink_spelling_is_preserved`:
real symlink creation raises WinError 1314 before startup capture. No skip or
mock replaced this filesystem control. Existing skips remain existing skips.

Independent read-only scientific-review skill result: **PASS**, no actionable
test weakening found. Reviewer did not run tests; its PASS does not close the
remaining failure or any mandatory gate.

## Boundary reached for this infrastructure track

The residual infrastructure failures inspected in the earlier FAST traces
include Linux `/proc` ownership checks, `fcntl` locks, POSIX signal masks and
signals, POSIX permission/readonly cleanup behavior, and literal backslash
filenames. Those cannot be established on this native Windows environment by
changing fixtures without changing what is being tested. The production local
assurance entry point explicitly requires Linux. Porting its security model is
outside this bounded repair, not an implied prerequisite for the MVP.

Symlink tests specifically require a privilege/capability missing on this host;
they are not inherently impossible on every Windows setup. We did not enable
Developer Mode, elevate, or change system security settings. Run the unchanged
controls on the intended Linux/WSL assurance environment instead.

Dirty-source certificate/freeze and current-provenance gates require completion
of the concurrently edited source, provenance review and the prescribed freeze
workflow. They are not Windows bugs, and historical pins must not be refreshed
just to silence them. Discovery, data-role and v3 scoring work remain owned by
the other session; this continuation neither modifies nor certifies them.

Next infrastructure step: use a supported Linux runtime after the source is
ready, run the unchanged mandatory FAST/SCIENTIFIC commands from docs/TESTING.md,
and triage fresh failures. Full assurance still requires the separate budget
decision; isolated blindfold and final evaluation also retain their own gates.
Do not infer that every residual failure will disappear on Linux.

Full FAST rerun, SCIENTIFIC, Linux isolation, campaign, full assurance and final
evaluation in this continuation: **NOT RUN**. No project commit/push/merge.
Unit-test-owned temporary Git fixture commits are not changes to project history.
