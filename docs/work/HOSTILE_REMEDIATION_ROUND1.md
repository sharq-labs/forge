# Hostile remediation round 1 — blocked preflight (2026-10-13)

No finding is closed. No production code or certificate was changed.

Starting `origin/main`: `5d73e8f5118aa845f1957decc5aae986e72476a9`, verified
after `git fetch origin`. It matches the requested starting SHA.
Branch: `fix/hostile-review-p0-p1`. Worktree: `D:/forge-hostile-remediation`.
The original checkout's dirty documents were preserved. No push, PR or merge.

## Blocking environment evidence

Authoritative assurance cannot run in the available execution environment:
`tools.certification.local_assurance._require_linux()` raises
`LocalAssuranceError: authoritative local assurance must run on Linux/WSL ...
native Windows/macOS is refused`. Both `wsl --list --quiet` and
`wsl -d Ubuntu -- bash -lc ...` failed to return and were interrupted.
The Windows launcher lists Python 3.10 and 3.14 only. Supported Python 3.11/3.12
acceptance, Linux authority tests and recertification are unavailable here.

Unmodified Python 3.14 probes and the regression command also stalled in
`platform._wmi_query`, reached through Pint/flexcache. A faulthandler traceback
identified that call. Diagnostic probes set `platform._wmi = None` in memory,
using Python's existing fallback. This changes environment probing, not Forge
science, and is explicitly **not acceptance or certification evidence**.

The user requires stopping if recertification cannot prove the resulting tree.
The verifier rejects even the clean starting tree and the authoritative runner
cannot execute. Implementation stopped at preflight; do not treat this report
as a completed remediation or as permission to recertify without measured gates.

## Finding ledger

| Finding | Before | Root cause / exact symbol | Architectural fix | Adversarial proof this session | Status |
|---|---|---|---|---|---|
| F1 LLM authority | CRITICAL | `claims/adapters/nl.py::compile_natural_language` grounds inputs/context but not decision criteria | NOT IMPLEMENTED | Text requests 305 K ± 0.5 K; proposal retains 309.75 K, compiles `ready` without findings, `assess_claim` returns `supported` | OPEN, reproduced diagnostically |
| F2 certification scope | HIGH | `tools/certification/core_certificate.py::SCOPE` omits verdict/authority ownership | NOT IMPLEMENTED | Enumerated scope excludes `credibility/evidence.py`, `claims/verdict.py`, `authority/ledger.py`, `blindfold/__init__.py` | OPEN; committed-drift fixture NOT RUN |
| F3 stale certificate | HIGH | `core_certificate.py::verify_certificate`; certificate targets an earlier tree | NOT IMPLEMENTED | Clean-main verification rejects target SHA and changed files in five areas | OPEN, owner assurance blocked |
| F4 validation semantics | HIGH | `scientific/results/validation.py::VALIDATION_LEVELS` includes `BENCHMARK_VALIDATED`; `credibility/evidence.py::evidence_basis` maps it to `VALIDATED` | NOT IMPLEMENTED | Membership probe returns True; inspected downstream mapping | OPEN; no migration attempted |
| F5 conservation | HIGH | `execution/multiphysics/runtime.py::run` overwrites `last_conservation`; `_audit_conservation` outcome not enforced | NOT IMPLEMENTED | Injected audit FAIL then PASS into a two-window runtime; final output retains only PASS | OPEN; actual declared-balance fixture still required |
| F6 physical admissibility | HIGH | `systems/products/drone_coupled.py::build_runtime` lacks ideal-power admissibility check | NOT IMPLEMENTED | Illustrative fixture with power coefficient 0.002 returns computed coupled screening; independently calculated FM = 14.554560428103372 | OPEN, reproduced diagnostically |
| F7 selective gate | HIGH | `tools/forge_check.py::changed_test_files` requires root `tests/`; `test_impact.py::ImpactGraph.importers` cannot resolve deleted relative imports | NOT IMPLEMENTED | Provider-local changed test selects nothing. Actual HVAC deletion selects 47 modules, none HVAC-specific; unresolved empty and narrowing refusal empty. Bytes restored exactly | OPEN, reproduced diagnostically |
| F8 CI enforcement | HIGH | `.github/workflows/tests.yml` declares dispatch only | NOT IMPLEMENTED | Static workflow inspection; no host setting changed or queried | OPEN, code-side enforcement NOT FIXED; HOST SETTING STILL REQUIRED |
| scanner `.forge/venvs` | BLOCKER | `tools/certification/mutation_workspace.py::snapshot` traverses environment trees | NOT IMPLEMENTED | Synthetic `.forge/venvs/env/lib/foreign.py` appears in snapshot | OPEN; full baseline-run integration NOT RUN |
| authority genesis mutation | MED/P1 | `authority/ledger.py::AuthorityLedger._apply_checked` signature guard has insufficient demonstrated coverage | NOT IMPLEMENTED | In-memory deletion of genesis signature guard: same exact 15 failing IDs and same 21 passing tests as baseline in two authority modules; failures involve unavailable `os.geteuid`, `fcntl`, and default cp1252 source decoding | OPEN; partial coverage gap evidence, Linux population NOT RUN |
| empty-UQ authority | MED/P1 | `uq/budget/aggregation.py::aggregate_uncertainty` returns zero for empty components | NOT IMPLEMENTED | Empty tuple returns standard uncertainty 0.0 and variance 0.0. Production users include `uq/combined/combine.py` and `uq/budget/report.py` | OPEN; terminal authority-consumer trace incomplete |

Closest existing tests needing adversarial extensions: `tests/claims/test_nl_adapter.py`,
`tests/claims/test_sria_context_authority.py`, `tests/foundations/test_drone_coupled_hover.py`,
`tests/test_stateful_multiphysics_runtime.py`, `tests/foundations/test_authority_integrity.py`,
`tests/foundations/test_authority_durable_campaign.py`, `tests/uq/budget/test_aggregation.py`.
Certification, impact-selector and mutation-workspace suites also require committed-drift,
deleted-import, collected-test-root and ownership-scope regressions before implementation.

Phase 0 is incomplete: F2 committed semantic drift, F4 independent experimental comparison,
F5 actual declared-balance failure, full genesis mutation population, and the complete UQ
authority-consumer trace remain to be executed. Static inspection is distinguished above
from runtime reproduction.

## Commands and results

Diagnostic Python executable:
`C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe`.
Probe sources and complete outputs are retained in `hostile-round1-evidence/`.

- `git fetch origin`; `git rev-parse origin/main`: PASS, expected SHA above.
- `git worktree add -b fix/hostile-review-p0-p1 D:/forge-hostile-remediation origin/main`:
  PASS, clean starting worktree.
- `py -0p`: only Windows Python 3.10 and 3.14 reported.
- `py -3.14 tools/forge_check.py --regression`: BLOCKED in environment query;
  interrupted. Direct Python execution of the same command also blocked.
- Diagnostic in-process `pytest.main(build_targets([], regression=True) +
  ['-q', '--basetemp=D:/forge-hostile-diagnostic-pytest', '-p', 'no:cacheprovider'])`,
  with `platform._wmi=None`: **256 passed in 11.85 s**, exit 0.
  This is a diagnostic run of the fixed-pack targets, not the documented supported gate.
- `$env:PYTHONPATH='.;src;tests;tests/claims;tests/foundations'; & <python>
  D:/forge-hostile-phase0-probes.py`: exit 0; results in ledger above.
- Genesis baseline: in-process `pytest.main(['tests/foundations/test_authority_integrity.py',
  'tests/foundations/test_authority_durable_campaign.py', '-q', '-p', 'no:cacheprovider',
  '--basetemp=D:/forge-hostile-genesis-baseline-temp'])`, WMI fallback:
  **15 failed, 21 passed in 2.02 s**, exit 1.
- Genesis mutant: `& <python> D:/forge-hostile-phase0-mutations.py`, with
  `PYTHONPATH=D:/forge-hostile-diagnostic-deps;.;src;tests;tests/foundations`:
  pytest **15 failed, 21 passed in 2.11 s**, pytest exit 1. Harness exit 0 records
  observations and is not a passing mutation gate. Exact failure IDs compared
  with `Compare-Object`: no differences. Full identities and tracebacks retained.
- Initial genesis attempt: **35 failed, 1 passed**, missing `cryptography`.
  Installed cryptography 50.0.2/cffi 2.1.1/pycparser 3.11 into an external
  diagnostic-only directory, then reran. User/global Python environment unchanged.
- `core_certificate.verify_certificate(Path.cwd(), load_certificate(...))`:
  FAIL; changed areas `certification_control`, `execution_trust`, `harness`,
  `inference_admission`, `runtime_dependencies`; target mismatch.
- `python -c 'from tools.certification.local_assurance import _require_linux;
  _require_linux()'`: FAIL, native Windows explicitly refused, exit 1.

Failed probe approaches: importing `compile_natural_language` from top-level claims
instead of canonical adapter; launching external script without repository root on
PYTHONPATH. Corrected before interpreting results. No temporary source mutation
remains. HVAC SHA-256 before/after:
`54a69815bc43a5a7cb66040c298322adfecf7944edb1a4462fb463dfa70fef8a`.

## Required closeout fields

- Ending SHA / commits: documentation-only local checkpoint; see Git HEAD and PROGRESS.
- Changed files: this report, evidence transcripts/scripts, ACTIVE_PLAN and PROGRESS.
- Production files changed: **none**.
- Scientific numerical outputs changed: **NO**. Frozen experiment outputs changed: **NO**.
- Certificate old target: `39d43456cab918ed0748efe7f5b0ff5781474ffa`.
- Certificate new target: **none**; stored certificate untouched.
- Python 3.11 / 3.12 FAST: **NOT RUN — environment unavailable**.
- Python 3.12 SCIENTIFIC / FULL: **NOT RUN — environment unavailable**.
- Supported regression gate: **BLOCKED**; diagnostic target run recorded separately.
- Complete selective mutation campaign: **NOT RUN**.
- Benchmark digest failure attribution: **NOT RUN**; no pins updated.
- Hardened recertification: **NOT RUN — authoritative Linux runner unavailable**.
- Remaining CRITICAL: **1**. Remaining listed HIGH: **7**. No listed finding closed.
- Intentionally deferred: PETSc convergence, ngspice/preCICE process wrappers,
  broad style/exception cleanup, exact floating rounding and contraction estimator.
- No Mind work. No new features. No external communications or GitHub mutations.

Resume in a functioning Linux/WSL environment with supported Python versions.
Recheck HEAD, complete phase-0 reproductions, then implement F1–F8 and the associated
scanner/genesis/UQ repairs in the user's prescribed order. Do not mint a certificate
until all measured gates and independent scientific reviews bind the final source head.

HOSTILE_P0_P1_REMEDIATION_BLOCKED
