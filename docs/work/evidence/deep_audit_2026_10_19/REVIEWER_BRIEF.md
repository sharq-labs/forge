# FORGE deep defect audit — common reviewer brief (2026-10-19)

## Target (authoritative, verified by the lead)
- Worktree: `D:/forge-main-337519d1` (Windows path; Git Bash path `/d/forge-main-337519d1`)
- Branch `fix/p0-scientific-correctness-2026-10-18`, HEAD `abed661f0d551f352e7a2c451d0df7fcc22bde5c`
  (pushed; PR sharq-labs/forge#169 OPEN, not merged). Parent `68502ad1` = GitHub `main` (PR #168).
- Working tree == HEAD except two untracked docs (`docs/work/D4_ARCHIVE_COMPATIBILITY_DESIGN_REVIEW.md`,
  `docs/work/GENESIS_STEP0_A1_READINESS_REVIEW.md`). Tree hash `7f965f0da21ca17f1b7dff7b79962b04d86c9a50`.
- Other agent sessions are running on this machine. Do not touch their processes or files.

## Hard rules (read-only audit)
- NO edits, creations or deletions anywhere inside `D:/forge-main-337519d1` or any other checkout. No
  `__pycache__` either: never run Python against repo code, never `import engcore`, never run pytest, tools,
  benchmarks or the MCP server.
- Git: read-only only (`git log`, `git show`, `git blame`, `git diff`, `git grep`). Never checkout, switch,
  stash, reset, commit, fetch, push.
- No installs, no network fetches of code.
- Allowed execution: stdlib-only independent arithmetic/derivation scripts that you write in the scratch dir
  `C:/Users/DEV_KA~1/AppData/Local/Temp/claude/C--Users-dev-kaeem-Downloads-Compressed-phyx/930d769c-c13d-4ea2-92ed-e1fbd607fb46/scratchpad/audit/`
  and run with `"C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe" -I -S <script>`
  (`-S` guarantees no site-packages, hence no engcore). Such output is an *independent derivation*, never
  `EXECUTED_REPRODUCED` (that class requires running FORGE code, which needs owner authorization).
- Bare `python` in Bash is the Windows Store stub; use the venv path above.
- Use the Read/Grep/Glob tools for source. Cite exact `file:line` that you actually read.

## Evidence classes (use exactly)
EXECUTED_REPRODUCED (not available to you) · SOURCE_PROVEN (a complete code path you traced line by line
proves the behaviour) · STATIC_SUSPICION · CONTRACT_AMBIGUITY · DOCUMENTATION_ONLY · PERFORMANCE_HYPOTHESIS

## Severity
BLOCKER (established defect directly causing false scientific support, corrupted evidence, wrong admitted
numerical results, broken benchmark isolation) · MAJOR · MINOR · OBSERVATION. Keep confidence separate from
impact: a consequential hypothesis without a traced path is not a confirmed BLOCKER.

## Already-known findings — DO NOT re-report these as new
A new finding needs a distinct root cause, exploit condition, consequence or invariant. If you find a NEW
consequence/variant of a known item, report it as `variant_of: <known id>` and say exactly what is new.

Sources: `docs/work/REMEDIATION_2026-10-18.md` (master table A1..X-1), `docs/work/POST_MERGE_REMEDIATION_VERIFICATION.md`,
`docs/work/P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md`, `docs/work/FINAL_OWNER_DISPOSITIONS_2026_10_18.md`,
`docs/work/FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION.md`, `docs/work/FROZEN_MODEL_ARCHIVE_READBACK_INVESTIGATION_2026_10_18.md`,
`docs/work/D4_ARCHIVE_COMPATIBILITY_DESIGN_REVIEW.md`, `docs/work/GENESIS_STEP0_A1_READINESS_REVIEW.md`,
`docs/work/ACTIVE_PLAN.md` (OD table ~lines 620-670), `docs/work/G0_A1_FINAL_CLOSURE.md`,
`docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md`, `docs/work/BR15_AUTHORITY_CLOSURE.md`, `docs/work/HOSTILE_REMEDIATION_ROUND1.md`.
Grep these for your candidate before calling it new.

Compact list:
- D4: frozen `thermal.conduction1d.linear_diffusion@0.1.0` cannot read back its own /2 payload (null exclusions;
  module-scoped exemption via frame walk); registry all-or-nothing; stale docstrings; missing exemption pin-guard;
  L1 `ModelUse.of` TypeError on NOT_DECLARED, no NOT_DECLARED channel in ModelUse; OD-D4-6 latent null-convention bugs L1-L3.
- Replay: matching refusals replayed as VERIFIED (FIXED in P0 via bound-result requirement).
- Conservation: N^2 arithmetic floor admitted 1e-7 J leak at 256/512 cells (FIXED: exact Fraction global policy);
  D1-2 in-solver energy check is algebraically the row residual; D1-3 datum scaling (fixed); D1-5 float `==` region ends.
- M1C invalid realization aborted domain index (FIXED). OD-31 census 19->20 (applied).
- OD-22 window subdivision 7 vs 8; OD-23 electrothermal relaxation contract; OD-24 self-loop edges; OD-26 forward-tear
  guard unreachable + A2b `runtime_equivalent` trusts a frozen/tampered plan; OD-27 MultiphysicsAuthority scenario
  (fixed + B3a snapshot per instance not per request); OD-28 Multiscale scenario/timeline/env binding; OD-29 FastSystem
  inner run ids/digests never resolved (ghost digest passes); OD-30 initial_fast_state identity (fixed), FAILED vs REFUSED;
  B3d `initial_slow` digest omits domain keys / dict order; B3c held checkpoint cleared before admission.
- B2c battery-cooling flagship inner runs use build-time scenario digest; B2d provider refs side channel, pybamm refs
  with empty record digest.
- OD-32: Newton initial-point DIVERGED; `residual_norm` mixes relative/absolute/inf norms; linear providers lack
  residual-is-not-error note; C3-1 "oriented" interface residual equals unsigned residual (cannot detect orientation);
  C3-2 interface plane chart assumption undocumented. C1-1..5 Newton exception narrowing (fixed), C2-3 singular spsolve (fixed).
- OD-33 / D3-2: M1B dual transfer splits amount by length across a c*A jump; D3-3 refine/coarsen round trip is not identity.
- OD-34 / F2-4: O(N^2) issued-record verification. F1/F2/F3 performance hypotheses (dense SVD per solve etc.).
- E4-2/3/4 IQN staged drop, finalize masking, fail-closed retire (fixed); MINOR-2 finalize gap before main try.
- B-LEAK: same-account proposer read `/proc/<ppid>/cmdline --root-file` and recovered master root (5/6 true laws, run VALID);
  network reachable; detached child persisted; wrote into benchmark package; escrow in-process (`InProcessTransport`);
  `SubprocessTransport` same account; isolation (`blindfold/isolation.py`) not wired into harness; parent-memory refusal only
  Linux YAMA. No in-repo attack arm for cmdline/network/persistence/code-write.
- Genesis/benchmark: O-1 Holm fed with bootstrap resample fraction as "p"; O-2 coverage without interval; O-3 multiplicity
  ledger with no correction; O-4 UQ computed in MCP layer; O-5 two bootstrap index conventions; gate constant 3.5 "≈99% F",
  ddof=0, |r|>0.5 cut-off; P-1 `always_law` floor arm dominates; no frozen environment manifest; no formal-tier driver;
  held-out instances from FORGE's own generator; PySR/BoTorch/PySINDy NOT_AVAILABLE; v0.2 cannot be formal identity (OD-20/OD-B2).
- Governance: certificate binds 05522b59 (stale); CI dark (billing); no branch protection; harness identity moved by D2;
  Windows symlink skip; OD-16 API surface Python-version bound; OD-21 `is_usable` excludes validity; BR-15 residuals
  (static loader completeness, runtime-injected objects); OD-17 benchmark rounds pin live src digest.

## What to deliver
Write your report to `.../scratchpad/audit/reviewer_<LETTER>.md` (the scratch dir above), then return a concise
summary (<= 900 words) listing each finding's ID, title, severity, evidence class and one-line consequence.

For each candidate finding include all fields:
1 ID (`<LETTER>-NN`) · 2 Category · 3 Exact file:line · 4 Governing contract (doc/test/docstring) · 5 Invariant violated
(quote the CLAUDE.md authority rule where one applies) · 6 Root cause · 7 Minimal triggering conditions · 8 Expected vs
observed · 9 Independent mathematical/logical reasoning · 10 Evidence class · 11 Affected models/providers/claims ·
12 False-support risk (none/low/medium/high + why) · 13 Replay/provenance impact · 14 Compatibility impact ·
15 Certification impact (is the file in `certification/current_core_v2.json`? grep it) · 16 Genesis impact (blocks
Step-0 / Genesis-lite Step-1 / Minimal Mind Step-2 / Independent Blindfold Graduation / none) · 17 Minimal
reproduction plan (exact bounded command, cost estimate, expected result, isolation needs — NOT executed) ·
18 Smallest scientifically correct repair (proposal only) · 19 Owner approval required (yes/no + which) ·
20 Self-challenge: the strongest argument that this is NOT a defect, and why it does or does not survive.
Also: `new_or_known` (NEW / variant_of:<id>).

Separately list: (a) hypotheses you could not confirm, (b) areas you inspected and found sound (with the reasoning),
so the lead can tell coverage from silence.

Quality bar: depth over breadth. Zero new findings in an area is an acceptable, honest result. Do not manufacture
issue counts. Every SOURCE_PROVEN claim must survive your own attempt to break it. Trace real call paths end to end;
check whether an upstream guard already refuses the input before claiming a downstream gap is reachable.
