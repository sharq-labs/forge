# Deep Scientific Defect Audit — evidence, 2026-10-19

**UNCERTIFIED. Developer audit evidence, not a validation or certification result.** Every finding is static
(SOURCE_PROVEN, STATIC_SUSPICION, CONTRACT_AMBIGUITY, …) unless the register marks it `EXECUTED_REPRODUCED`.

## Source the audit examined

| Item | Value |
| --- | --- |
| Worktree | `D:/forge-main-337519d1` |
| Branch / commit | `fix/p0-scientific-correctness-2026-10-18` @ `abed661f0d551f352e7a2c451d0df7fcc22bde5c` (PR sharq-labs/forge#169, open at audit time) |
| Tree | `7f965f0da21ca17f1b7dff7b79962b04d86c9a50` |
| Tracked-file hash index | `bf233a73a046225a225aea4f9101e64f0402d37509a095a6b5e22714c8dad08f` (`file_hashes.txt`, 5,289 src/tests/benchmarks/tools files). Unchanged before and after every executed run. |
| GitHub `main` at audit time | `68502ad1457ffb3fe160b87729e1d586c6413875` |

This evidence directory is committed on top of `main` `68502ad1`. **The audited source is `abed661f`, not the commit
that carries these files.** Line numbers in the reports refer to `abed661f`.

## What was executed

- **Read-only audit (no FORGE code run).** Five independent reviewers (A–E) and three adversarial cross-reviewers (X1–X3). Independent arithmetic used stdlib-only scripts run with `python -I -S`, so engcore could not be imported. Those outputs are derivations, not reproductions.
- **Owner-authorized reproductions R-03, R-04, R-05, R-06.** Each was run once, sequentially, against the real FORGE functions at `abed661f`.
  - Environment: phyx `.venv`, Windows, CPython 3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3.
  - Bootstrap: `repro/bootstrap/sitecustomize.py`, containing only `platform._wmi = None`.
  - Flags: `-B`, `PYTHONDONTWRITEBYTECODE=1`, BLAS threads 1.
  - Exact argv, exit code, wall time, output hashes and before/after source identity are in `repro/R-0x.json`.
  - All four reproduced their finding, and all negative controls behaved as expected. Together they cover 5 findings: FDA-03, FDA-04, FDA-05, FDA-06 and FDA-14.
  - **Windows 3.14 is not the supported certification platform.**
- **Not run:** R-01, R-02 and R-07..R-26 (the owner stopped further reproductions), any pytest, benchmark, mutation, assurance or Genesis measurement.

## Layout

The scratch layout is preserved exactly, so the original manifest verifies without any path rewriting.

| Path | Content |
| --- | --- |
| `package/` | The five audit artifacts: report, findings register (JSON), risk matrix, reproduction plan, build-vs-buy |
| `reviewer_A.md` … `reviewer_E.md` | Independent reviewer reports (all 20 fields per finding) |
| `crossreview_X1.md` … `crossreview_X3.md` | Adversarial disproval reports |
| `REVIEWER_BRIEF.md` | Common rules and known-findings list given to every reviewer |
| `*.py`, `x3_prereg_dump.txt` | Stdlib-only derivation scripts (never import engcore), and `verify_package.py` |
| `repro/` | R-03..R-06 scripts, `run.sh`, bootstrap, stdout/stderr, run records, `update_register.py` |
| `closure/` | Closure plan, owner decisions, Genesis/Blindfold blocker matrix (planning only; nothing approved by their existence) |
| `source_identity.txt`, `file_hashes.txt` | Source identity of the audited tree |
| `EVIDENCE_MANIFEST.sha256` | SHA-256 of the 49 audit files (manifest digest `94d75936f930baebcea7e6f4db27444cb613e00fcbc5dd0dad25fd21ac0c147e`) |
| `closure/CLOSURE_DOCS.sha256` | SHA-256 of the closure documents |
| `.gitattributes` | `* -text`: git never rewrites these bytes |

These files are **not** a runnable test suite. The repro scripts import engcore and must not be run without owner
authorization. They are historical records bound to `abed661f`.

## Verify

From this directory:

```bash
sha256sum -c EVIDENCE_MANIFEST.sha256
sha256sum -c closure/CLOSURE_DOCS.sha256
```

Never edit files here. A correction is a new, dated evidence directory that references this one.
