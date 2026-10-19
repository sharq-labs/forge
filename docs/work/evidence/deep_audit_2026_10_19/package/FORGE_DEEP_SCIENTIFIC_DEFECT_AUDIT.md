# FORGE — Deep Scientific Defect Discovery & Adversarial Audit

> **Addendum 2026-10-19 (supersedes the "no finding is EXECUTED_REPRODUCED" statements below for these items only).**
> The owner authorized four reproductions: R-03, R-04, R-05 and R-06. Each ran once, sequentially, against the real
> FORGE functions at `abed661f`. The tracked-file hash index (`bf233a73…`) was identical before and after every run,
> and no `.pyc` was written in the repository. Every negative control behaved as expected. Records:
> `../repro/R-0x.json` (argv, exit code, wall time, output hashes, source identity) and `R-0x.out`.
>
> | Finding | Reproduction | Executed result | New evidence class |
> |---|---|---|---|
> | FDA-04 | R-04 (2.1 s) | n=4, 3 inputs: Y = x1+x2 gave `completed` lower = upper = 1.0, sd 0. n=32, 17 inputs: Y = x15+x16 gave the same. Control (n=32, 2 inputs): width 1.68. | EXECUTED_REPRODUCED |
> | FDA-14 | R-04 | Stated 0.95; realised mass 0.7125 (n=4) and 0.9203 (n=32) | EXECUTED_REPRODUCED |
> | FDA-05 | R-05 (0.2 s) | One vacuous pair (A/B = 1.3e30 at the region edge) gave `indistinguishable_hit`, credit 1.0, in both the evaluator and the escrow, for **two mutually exclusive truths**. Controls: refusal 0.5; informative pair hit; in-box-disagreeing pair miss; discoverable world −0.5. | EXECUTED_REPRODUCED |
> | FDA-06 | R-06 (0.2 s) | `_capped`: discoverable 1.0→0.0, but spurious stays 1.0 even with an explicit out-of-family flag; paired difference +1.0. Covers the capping function only, not the full `lift_decision`. | EXECUTED_REPRODUCED |
> | FDA-03 | R-03 (0.8 s) | Two conflicting 300 K data gave a `known` INTERPOLATED value: 25.0, or 20.0 after swapping the claim ids. 300 K exactly gave UNKNOWN "not arbitrated". Coverage `conflicted=False`. Control without coincident data: 20.0 regardless of id. | EXECUTED_REPRODUCED |
>
> All other findings keep their static evidence class; R-01, R-02 and R-07+ were not run. The results are recorded in
> this scratch package only. They were not appended to `docs/work/PROGRESS.md`, because no repository write was
> authorized; they are pending owner approval of that write.

**Date:** 2026-10-19. **Status:** read-only static audit. **Nothing was executed against FORGE code.**

The audit did not run any pytest, benchmark, tool, MCP server or `import engcore`. Arithmetic counterexamples come
from stdlib-only scripts run with `python -I -S`, which cannot import engcore. They are independent derivations.
**No finding below is EXECUTED_REPRODUCED.** Nothing is labelled PASS on the strength of a proposed test.

Companion files in this package:
- `FORGE_NEW_FINDINGS_REGISTER.json`: every finding with all 20 fields.
- `FORGE_SCIENTIFIC_RISK_MATRIX.md`
- `FORGE_ADVERSARIAL_REPRODUCTION_PLAN.md`
- `FORGE_BUILD_VS_BUY_DEFECT_OPPORTUNITIES.md`

Annexes in `../`:
- `reviewer_A..E.md`: independent investigations.
- `crossreview_X1..X3.md`: disproval attempts.
- `*.py`: derivation scripts.
- `file_hashes.txt`: hash index of 5,289 tracked files.

## Phase 0 — Repository identity and governance

| Item | Observed |
| --- | --- |
| Authoritative worktree | `D:/forge-main-337519d1` |
| Branch / HEAD | `fix/p0-scientific-correctness-2026-10-18` / `abed661f0d551f352e7a2c451d0df7fcc22bde5c`. It is not the last-reported `fix/post-merge-remediation-2026-10-18`. INT-1 has committed and pushed the P0 + D1–D3 tree. |
| Upstream | `origin/fix/p0-scientific-correctness-2026-10-18`, which equals HEAD. **sharq-labs/forge#169 is OPEN and not merged.** GitHub `main` is `68502ad1` (PR #168), which is the HEAD's parent. |
| Working tree | Identical to HEAD except two untracked docs: `docs/work/D4_ARCHIVE_COMPATIBILITY_DESIGN_REVIEW.md` and `docs/work/GENESIS_STEP0_A1_READINESS_REVIEW.md`. Tree `7f965f0d…`. |
| Source hash index | SHA-256 `bf233a73…` over 5,289 tracked src/tests/benchmarks/tools files. At audit end, re-hashing the files of every MAJOR finding showed no drift. |
| Concurrent activity | Three other Claude Code sessions, Codex app and exec servers, and about 14 `engcore.mcp.server` processes are running. None of them was touched. No assurance or mutation process was observed against this worktree. |
| Governance docs | All 15 named files are present; none is absent. SHA-256 prefixes (lines): ACTIVE_PLAN `fed2a6eb214580b3` (812); PROGRESS `286607a116232fef` (7491); P0_CLOSURE `a541ccbdc587578e`; FINAL_OWNER_DISPOSITIONS `0988d70aa62d6cc4`; FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION `1cd352c933ce417d`; FROZEN_MODEL_ARCHIVE_READBACK `ad4dc4070df7875d`; D4_REVIEW `bc32e624c771afef`; GENESIS_STEP0_A1 `3f76c73079eab977`; REMEDIATION_2026-10-18 `afb59bdfe0f5a700`; FORGE_GENESIS `37f6e9e47f694bc0`; FORGE_MASTER_PLAN `9a968772cfb4f58a`; COMPLETION_POLICY `46df957e9d170cba`; CORE_FREEZE_POLICY `a2235a8ce2cd5265`; BRANCH_PROTECTION `883c549ff4c1c30e`; CLAUDE.md `7f0a2bd2a1c0d3f5`. |
| Active epic | `engrt.numerical_foundations` (OD-6). Its allowed research scope is set by `ENGINEERING_FOUNDATIONS_PROGRAM.md`. Genesis-lite work is limited to A1 preparation. |
| Certification state | The certificate binds `05522b59`, which is stale. P0, D1–D3 and the source that HEAD carries are all UNCERTIFIED. CI has been dark since 2026-10-15. |

The audit kept to all of these: no source, test, fixture, certificate, ledger or historical-evidence edit; no
commit, push, reset, stash or checkout. All artifacts are outside the repository.

## A. Executive summary

- **No BLOCKER was established.**
- **Six new MAJOR defects** survived independent adversarial disproval:
  - two in the authority and state core: replay that does not reproduce uncertainty (FDA-01), and committed state not bound to the run's clock (FDA-02);
  - one in materials: silent source arbitration in interpolation (FDA-03);
  - one in the MCP product UQ tool: deterministically correlated "independent" inputs that can yield a zero-width interval (FDA-04);
  - two in Genesis-lite scoring and statistics: vacuous INDISTINGUISHABLE pairs earn full credit (FDA-05), and out-of-family spurious worlds are uncapped (FDA-06).
- **Twenty MINOR defects** and **eight observations** were also recorded.
- Two reviewers found the discovery-holdout defect (FDA-16) independently. Cross-review confirmed it only at reduced severity.
- **Six findings were reduced** in severity by cross-review: C-02, E-01, E-03, E-04, D-03 and D-05.
- **Two folded into known items:** D-04 into B-LEAK, and D-09 into readiness row 11.
- **None was fully refuted.** The reviewers' original trigger for A-03 was largely refuted, and a stronger trigger replaced it.
- **Most of the hand-built numerical kernels re-derived as correct.** These include Newton/Armijo, Hager condition estimate, GCI/Richardson, conservative remap, clipping, Thomas, Pearson three-moment, Fincke-Pohst, weighted quantiles, Wilson, and the M1C BE/FV assembly with its exact global gate. This is reported as coverage, not silence.
- **The scientific-authority claims chain is in good order:** `derive_verdict` monotonicity, UNKNOWN channels, contradiction bar, P0 bound-result replay and context binding. The new authority defects sit at its edges: assembly replay, offline verification, and the system-runtime clock.

## B. Previously known issues (deduplicated)

| Known item | Classification | Basis |
| --- | --- | --- |
| D4 frozen-model archive readback | OPEN_CONFIRMED + OWNER_DECISION_REQUIRED | Executed probe log; OD-D4-1..6 |
| D4 latent L1 (`ModelUse.of` TypeError, no NOT_DECLARED channel) | OPEN_STATIC_SUSPICION | D4 review §3 |
| Replay of matching refusals → VERIFIED | RESOLVED_WITH_EXECUTED_EVIDENCE (on #169 only, uncertified) | 175 claims tests |
| Conservation N² arithmetic floor | RESOLVED_WITH_EXECUTED_EVIDENCE (#169, uncertified) | 48 actual-solver cases |
| M1C invalid realization aborts domain index | RESOLVED_WITH_EXECUTED_EVIDENCE (#169) | Claims and M1ABC packs |
| OD-22 window subdivisions 7 vs 8 | OWNER_DECISION_REQUIRED | Executed Fraction replay 7/4 |
| OD-23 electrothermal relaxation | OWNER_DECISION_REQUIRED | Red L3 test |
| OD-24 self-loop edges | OWNER_DECISION_REQUIRED | Red BR1 test |
| OD-26 forward-tear unreachable / A2b coupling-plan tampering | OPEN_CONFIRMED (fixtures) / OPEN_STATIC_SUSPICION (A2b) | Five executed failures |
| OD-27 / B3a scenario binding | RESOLVED_WITH_EXECUTED_EVIDENCE; the per-instance snapshot residual is OPEN_STATIC | 83-case pack |
| OD-28 multiscale scenario binding | RESOLVED_WITH_EXECUTED_EVIDENCE | PR #167, 83-case pack |
| OD-29 FastSystem inner provenance | OPEN_STATIC_SUSPICION + OWNER_DECISION_REQUIRED | Census; attack not executed |
| OD-30 fast-state identity / FAILED vs REFUSED / B3d slow-state | Fast-state half RESOLVED_WITH_EXECUTED_EVIDENCE; the rest OWNER_DECISION_REQUIRED | 83-case pack |
| OD-31 census 19→20 | RESOLVED_WITH_EXECUTED_EVIDENCE | Discovery: 3 passed |
| OD-32 nonlinear semantics, residual meaning, C3-1 orientation | OWNER_DECISION_REQUIRED | — |
| OD-33 M1D / D3-2 dual transfer | Primitive RESOLVED_WITH_EXECUTED_EVIDENCE; integration OWNER_DECISION_REQUIRED | M1B tests |
| D3-3 refine/coarsen round-trip diffusion | OPEN_STATIC_SUSPICION | Census |
| OD-34 O(N²) issued-record verification | OWNER_DECISION_REQUIRED (performance hypothesis) | — |
| B2c battery-cooling scenario identity | OPEN_STATIC_SUSPICION | Census |
| B2d provider reference authenticity | OPEN_STATIC_SUSPICION | Census |
| Mesh/transfer conservation (C3-4 mechanics) | No defect (census); see FDA-17 for a new point-location gap | — |
| B-LEAK Blindfold answer leakage | OPEN_CONFIRMED (measured 2026-10-14; raw evidence outside repo) | G0_A1_FINAL_CLOSURE |
| Genesis O-1 bootstrap-"p" fed to Holm | OPEN_STATIC_SUSPICION | Readiness §8.7. D judged it approximately calibrated at formal sizes, but did not simulate it. |
| O-2 coverage without interval / O-3 multiplicity ledger / O-4 UQ in MCP / O-5 two bootstrap conventions | OPEN_STATIC_SUSPICION | Readiness §8.7 |
| Missing vs empty exclusions | OPEN (D4 family; fail-closed) | — |
| Certificate and compatibility limitations (stale cert, CI dark, Windows symlink skip, OD-16, OD-21, BR-15 residuals) | OPEN_CONFIRMED (governance) | — |

None of the known items above is re-reported as new. Where a new finding extends one, the register marks it
`variant_of`.

## C. Newly identified defects (ranked by consequence × evidence)

| ID | Area | New/Known | Finding | Evidence | Severity | Scientific impact | Reproduction | Recommended action |
|---|---|---|---|---|---|---|---|---|
| FDA-01 | Replay / certification | NEW | `assembly/replay.py:531-638` never compares uncertainty or validation blocks, units or field outputs. `external_uncertainty` is supplied by the caller at replay and not bound to the plan, so REPLAYED_MATCH can certify UQ that was never reproduced. | SOURCE_PROVEN (A, X1, lead) | MAJOR | Certification UQ/validation gates rest on stored values | R-01 | Bind the external UQ into the plan identity; compare the UQ blocks; OD-3 |
| FDA-02 | System runtime state | NEW | A coupled run's window is not tied to the committed state clock (`authorities.py:407`, `records.py:171`, `state.py:204`). Two [0,10] s runs commit x=20 at t=10. | SOURCE_PROVEN (latent) | MAJOR | A wrong state is committed with valid receipts | R-02 | Preflight `plan.start == state.time`; OD-3 |
| FDA-03 | Materials | NEW | Interpolation silently arbitrates two sources at one position (`properties.py:353-366`), and coverage hides the conflict. | SOURCE_PROVEN (latent) | MAJOR | An arbitrated coefficient is admitted as known | R-03 | Refuse coincident positions; OD-3 |
| FDA-04 | MCP UQ tool | NEW | Lattice-LHS columns are exactly anti-correlated (n=4 with ≥3 inputs; n=32 with ≥17), giving a zero-width "completed" interval. | SOURCE_PROVEN + lead derivation | MAJOR | Missing uncertainty becomes zero | R-04 | SciPy QMC LHS or refusal |
| FDA-05 | Genesis-lite scoring | NEW | The INDISTINGUISHABLE bracket has no width bound. A vacuous pair hits 77% of the time (independent simulation). | SOURCE_PROVEN + simulation | MAJOR | UNKNOWN (0.5) becomes 1.0 | R-05 | Width bound in evaluator and escrow; v0.3 |
| FDA-06 | Genesis-lite lift rule | variant of D4 | Out-of-family `spurious_correlate` worlds are uncapped (`analysis.py:192-196`). | SOURCE_PROVEN; CONTRACT_AMBIGUITY | MAJOR | A grammar-reach lift can pass | R-06 | Cap that kind too; v0.3 |
| FDA-07 | Claims offline verify | NEW | The execution view is not re-derived, so an inconsistent record is not reported as TAMPERED. | SOURCE_PROVEN | MINOR | Offline only | R-07 | Re-derive |
| FDA-08 | Claims replay | NEW | `replay_bundle` drops `criteria_authority`, so grounded records can never be VERIFIED. | SOURCE_PROVEN | MINOR (fails closed) | Availability | R-08 | Pass it through |
| FDA-09 | Replay contract | NEW | VERIFIED is documented as "publishable support" yet is returned for INSUFFICIENT; `ReplayResult` has no verdict. | CONTRACT_AMBIGUITY | MINOR | Consumer misreading | R-09 | Carry the verdict |
| FDA-10 | Coupled conservation | NEW | The balance uses the transfer's own RECEIVED, not the consumed value. | CONTRACT_AMBIGUITY | MINOR | Label overstated | R-10 | Qualify the docs |
| FDA-11 | Run records | NEW | Parameter bindings are not recorded or replayed. | SOURCE_PROVEN (latent) | MINOR | Provenance | R-11 | Record them |
| FDA-12 | DC validation | variant of D1-3 | The residual scale grows with common-mode potential. | SOURCE_PROVEN + exact derivation | MINOR | NUMERICALLY_CONVERGED on a corrupted solve | R-12 | Branch scaling |
| FDA-13 | FTCS | NEW | An unstable run passes the amplitude check; applicability is not recorded. | SOURCE_PROVEN + emulation | MINOR | No production caller | R-13 | Decayed-mode check |
| FDA-14 | MCP UQ tool | NEW | A stated 0.95 interval covers 0.95 − 0.95/n (0.920 at n=32). | SOURCE_PROVEN + derivation | MINOR | Narrow intervals | R-04 | `method="hazen"` |
| FDA-15 | hybrid_uq multistart | NEW | Halton starts are collinear in the high dimensions. | SOURCE_PROVEN geometry | MINOR | Degenerate search | R-15 | Scheme /2 |
| FDA-16 | Discovery holdout | partly known | Absolute 0.05 RMSE gate; noise "survives". | SOURCE_PROVEN + simulation | MINOR | Mitigated downstream | R-16 | Relative gate |
| FDA-17 | Mapping | NEW | Non-convex quad over-coverage in point location. | SOURCE_PROVEN geometry | MINOR | Extrapolation undercounted | R-17 | Convexity refusal |
| FDA-18 | Genesis-lite design | NEW | Answer exclusivity within a campaign. | Channel SOURCE_PROVEN | MINOR (MAJOR with FDA-05) | Tell for stateful arms | R-18 | Randomise the mix |
| FDA-19 | Isolation demo | variant of B-LEAK | The leak scan omits Genesis-lite secrets. | SOURCE_PROVEN | MINOR | Weak lift verifier | R-19 | Extend the probe |
| FDA-20 | Pilot metric | NEW | "Presentation invariance" compares different worlds. | SOURCE_PROVEN | MINOR | Descriptive | static | Relabel or pair |
| FDA-21 | Baseline arms | variant | `np.std` ignores fitted degrees of freedom. | SOURCE_PROVEN | MINOR | Baseline calibration | static | v0.3 |
| FDA-22 | Generator priors | variant | Per-kind form-prior tell. | SOURCE_PROVEN | MINOR | Enables FDA-05 | static | v0.3 |
| FDA-23 | Golden replay | variant of R-48 | Affine tolerance conversion. | SOURCE_PROVEN | MINOR (latent) | None today | static | Spread conversion |
| FDA-24 | PDE contracts | NEW | Partial-component Dirichlet treated as non-singular. | Guard SOURCE_PROVEN | MINOR | Rigid-mode offset | R-24 | Component check |
| FDA-25 | Coupling error ledger | NEW | Implicit window-hold error is omitted. | SOURCE_PROVEN | MINOR | Mislabel only | static | Add source |
| FDA-26 | PyBaMM flagship | NEW consequence | The origin-zero rule blocks Flagship A regeneration. | SOURCE_PROVEN static | MINOR (fail-safe) | Reproducibility | R-26 | Document or adapter |

Observations OBS-01..08 are listed in the register.

## D. Unconfirmed hypotheses (kept separate)

- **Timing side channel in escrow `observe`.** NO_SOLUTION skips law evaluation. Unmeasured, and not among the OD-20 requirements (D).
- **O-1 at formal sample sizes.** Expected to be approximately calibrated; not simulated (D).
- **Combined magnitude of FDA-05 + FDA-18 + FDA-22.** Unmeasured.
- **System runtime (C):**
  - H-1: an authority with a fixed runtime may reuse participant state.
  - H-2: an event found on an unconverged iterate.
  - H-3: a retryable failure masking a hard refusal under concurrency.
  - H-4: a datum-scaled coupling residual.
- **Assembly replay vacuous match.** `system_runtime.compare_runs` would match two all-failed runs, but nothing in `src` calls it (A).
- **Attested-PASS bypass.** `credibility_vector.py:1035-1038` admits an individually attested PASS check, which might let an attested residual check back NUMERICALLY_CONVERGED despite FDA-12 (X2; static).
- **Numerics (B, E):**
  - Pearson three-moment tail accuracy at α/2 = 0.005.
  - Warped-hexahedron point location.
  - Unbalanced ICC m₀.
  - `adapt_resolution` stopping at first pass.
- **FDA-15 missed mode.** Whether a second mode is actually missed in practice is unproven.

## E. Scientific authority risks (pathways to an incorrect scientific claim)

1. **Replay certifying unreproduced uncertainty (FDA-01).** This is the most direct path. A COMPUTATIONAL_REPLAY_VERIFIED gate is meant to attest that the run is reproducible. Its UQ and validation gates then read the stored record.
2. **Committed state from a mis-timed run (FDA-02).** All downstream nodes and receipts are consistent with a wrong state. Replay faithfully reproduces the wrong commit.
3. **Material coefficient chosen by `claim_id` order (FDA-03).** Its status is "known", and it carries a digest list that omits the conflicting datum.
4. **Zero-width or understated product UQ (FDA-04, FDA-14).** Delivered to an MCP client as `completed`.
5. **Smaller authority hazards:**
   - Reproduced but insufficient results labelled VERIFIED (FDA-09) invite consumers to read reproducibility as support.
   - Offline verification accepting an internally inconsistent execution view (FDA-07).

Paths that held under attack:
- Removing evidence never increases the level (monotone `derive_verdict`).
- UNKNOWN, COMBINED and misattributed uncertainty channels are never used as support.
- Caller values never replace sealed reports.
- Policy only adds requirements.
- The P0 bound-result replay cannot be satisfied by stored flags.
- Verification does not satisfy validation.

## F. Blindfold blockers (formal measurement)

| Blocker | Status | Blocks |
| --- | --- | --- |
| **B-LEAK (known)** | Open; measured | All formal measurement, Step-1 formal tier, Step-2, Graduation |
| **FDA-05** vacuous pair credit (new) | Open | Step-1 scoring freeze, Step-2 validity, Graduation |
| **FDA-06** uncapped out-of-family spurious worlds (new) | Open | Must fix before the Step-1 freeze (OD-19); Step-2, Graduation |
| FDA-18 campaign exclusivity (new; MAJOR while FDA-05 is open) | Open | Step-2 / Graduation design |
| FDA-19 isolation demo cannot detect the Genesis-lite leak class | Open | B-LEAK lift verification (P-1 spec), Graduation |
| FDA-21, FDA-22, known gate constants (3.5 "F", ddof=0, \|r\|>0.5), O-1 | Open | Baseline strength / §10.5 before OD-19 |
| FDA-20 | Descriptive only | None |
| Known governance: G0 not exited, no formal driver, no environment manifest, own-generator held-out | Open | Step-0 / Step-1 |

Genesis **Step-0** remains blocked by the known G0 items, not by the new findings. The new findings add three
pre-freeze scoring and statistics corrections (FDA-05, FDA-06, FDA-18), and they all fall inside the v0.3
amendment, which was already needed for B-LEAK. **No isolation boundary is claimed to work.**

## G. Numerical counterexamples (exact derivations; not FORGE executions)

1. **FDA-04, lattice anti-correlation.**
   - Column c uses index (i·s_c + c) mod n, with s_c the smallest odd number ≥ 2c+1 that is coprime to n.
   - At n=4: s = 1, 3, 5. Column 1 is (1,0,3,2) and column 2 is (2,3,0,1), so column 2 = 3 − column 1 elementwise and r = −1.
   - Hence for uniform inputs of equal width, X1+X2 is constant and its sd is 0.
   - At n=32 with ≥17 inputs, columns 15 and 16 have r = −1. With 2 inputs, r = +0.2903. (Lead: `../lead_e02_check.py`.)
2. **FDA-14.** For an output monotone in one input, the sorted values sit at quantiles (k+0.5)/n. The type-7 estimator at p=0.025 has position h = p(n−1). The realised lower quantile is (h+0.5)/n, so the covered mass is 1 − 2(0.025(n−1)+0.5)/n = 0.95 − 0.95/n. That gives 0.7125 at n=4 and 0.9203 at n=32 (lead-verified).
3. **FDA-02.** For dx/dt = 1 and x(0) = 0, two committed runs of the plan [0,10] s, each starting from the committed state, give x = 10 then x = 20 at t = 10. The true x(10) = 10. `state.next` accepts t_new = 10 ≥ t_old = 10.
4. **FDA-03.** Data a(300 K) = 10 and b(300 K) = 20 from different sources, plus c(400 K) = 30, with the state at 350 K. Sorted by claim_id, b follows a. The stable sort by position gives `below[-1]` = b, and the result is 20 + 0.5·(30−20) = 25. Exchanging the ids gives 10 + 0.5·20 = 20. At exactly 300 K the code refuses ("sources are not arbitrated").
5. **FDA-12.** In an a–m–c divider with a 1 mV drop, corrupting the midpoint by 0.1 mV (a 20% current error) makes the relative residual scale with |A||x|. X2 found with exact Fractions that the gate first passes at about 25 kV common mode, while KCL still FAILs.
6. **FDA-13.** FTCS with r = 0.55 > 0.5 at n = 20: the highest mode grows as |1 − 4r sin²(kπ/2n)|^t. The check max|u| ≤ 1 stays true for about 29 steps while the error reaches about 19× the decayed fundamental (X2 emulation).
7. **FDA-15.** Halton radical inverse in prime bases b_j for indices k < b_j satisfies u_j(k) = k/b_j. When N = 2p+2 < b_a < b_b, every start lies on u_b = (b_a/b_b)·u_a. At p=10, all 22 starts lie on one ray in the last two dimensions.
8. **FDA-05.** Take A = L(1+Ks) and B = L/(1+Ks), with s = Σ(x/high)^M and K = 1e-4. In the box, |A−B|/|B| ≈ 2Ks ≈ 8e-4, below σ_min = 0.005. Outside the box s → ∞, so A/B → ∞ and the pair brackets every finite truth. X3's re-implemented generator scored 1,156 of 1,500 worlds (0.771) as hits.
9. **FDA-17.** For the quad (0,0),(2,0),(2,2),(1.5,0.5), with reflex vertex 3: the point (1,0.6) lies in triangle (0,1,2) but outside the polygon.

## H. Cross-domain risks (generic architecture losing semantics)

- **Time is not a first-class part of state transitions (FDA-02).** The generic system runtime binds values, owners, units, scenario and plan, but not the start instant. Every domain committer inherits the gap.
- **Replay equality is defined over scalar magnitudes (FDA-01, FDA-23).** Domain semantics such as units, affine scales, uncertainty and field-valued outputs are outside the comparison.
- **"Conservation" is a transfer-mapping property, not physical interface conservation (FDA-10).** The generic name invites a physical reading.
- **Source arbitration is enforced in one branch but not the other (FDA-03).** A generic materials invariant fails on a derived path.
- **The datum- and scale-dependent tolerance pattern recurs across domains:** D1-3 (thermal, fixed), FDA-12 (electrical) and FDA-16 (discovery). It suggests a cross-domain invariant test: tolerance gates should be invariant under affine datum shift and unit rescaling.

## I. Build vs Buy findings

See `FORGE_BUILD_VS_BUY_DEFECT_OPPORTUNITIES.md`. In short:
- **External packages would remove verified risks** in FDA-04 and FDA-14 (SciPy QMC LHS and Hazen quantiles) and in FDA-15 (scrambled Halton via `scipy.stats.qmc`, as a new scheme).
- **Library oracles would audit the statistics:** FDA-21 and the known gate constants against `scipy.stats`, and O-1 against `scipy.stats.bootstrap` or a permutation test.
- **FDA-17** could use Shapely as a test oracle; the repair is a convexity precondition.
- **Everything else re-derived correctly by hand:** KEEP with test-only oracles.
- **Must stay proprietary FORGE logic:** replay, identity and certification semantics (FDA-01, 02, 07–09, 11), source arbitration (FDA-03), and escrow/evaluator scoring (FDA-05, 06, 18). No library carries FORGE's authority contracts. The evaluator must remain stdlib-only.

## J. Proposed remediation roadmap

Each step needs separate owner approval. None is implemented.

1. **Authorize bounded reproductions** R-01..R-06 (about 2–10 min each; scratch-only, `PYTHONDONTWRITEBYTECODE`; see the reproduction plan). This converts SOURCE_PROVEN to EXECUTED_REPRODUCED or refutes the findings.
2. **Authority core (certified; one OD-3 batch together with the P0 certification):**
   - FDA-01: bind and compare uncertainty and validation in replay.
   - FDA-02: tie the plan start to the state clock.
   - FDA-03: refuse coincident sources.
   - FDA-07 and FDA-08: pass-through and re-derivation.
   - FDA-09: verdict carried in `ReplayResult`.
   - Batch them, because a push cancels recertification (see memory notes).
3. **v0.3 Genesis-lite amendment, bundled with P-1..P-5:** FDA-05 width bound (with the certified escrow side), FDA-06 cap, FDA-18 mix randomisation, FDA-21 and FDA-22, an FDA-19 probe extension, the O-1 calibration study, and the gate constants. Only after that, OD-19.
4. **MCP UQ tool:** FDA-04 and FDA-14. Uncertified, so it can land independently. Also resolve O-4 (move the computation out of MCP).
5. **Minor numerics:** FDA-12, FDA-13, FDA-15 (with the freeze review), FDA-16, FDA-17, FDA-24 and FDA-25.

## Phase 11 — Scientific improvement opportunities (not defects)

| Improvement | Scientific benefit | Complexity | Verification cost | Dependency/licence | Before Blindfold? | Existing FORGE component |
| --- | --- | --- | --- | --- | --- | --- |
| Metamorphic tolerance tests (datum shift, unit rescale, common mode) across every gate | Would have caught D1-3, FDA-12 and FDA-16 | Low | Low (pure tests) | None | Optional | `tests/test_p0_conservation_policy.py` pattern |
| Replay challenge with perturbed declared inputs (external UQ, parameters, units) | Exposes FDA-01/FDA-11-class gaps | Medium | Medium | None | No | `assembly/replay.py`, claims replay |
| State-clock invariant tests across committers | FDA-02 class | Low | Low | None | No | system_runtime tests |
| Adversarial scoring arms (vacuous pair, refusal farming, stateful-exclusivity arm) | Benchmark validity (FDA-05, FDA-18) | Medium | Pilot-scope only | None | **Yes** | `tests/genesis_lite/attack_arms.py`, `arms.py` |
| Null-calibration study of the lift statistic (O-1) | Validity of the Holm FWER claim | Low | Small CPU | SciPy (test-only) | **Yes** | `analysis.py` |
| Independent numerical oracles (mpmath / Decimal for exact kernels; SciPy QMC; Shapely) | Stronger verification | Low–Medium | Low | Already installed, except Shapely | Optional | P0 Decimal kernel check |
| Isolation probe covering the Genesis-lite secret inventory | B-LEAK lift credibility | Medium | Requires a deployment | None | **Yes** | `isolation_probe.py` |
| Identifiability / profile likelihood via pyPESTO as a cross-check | Calibration rigour | High | Medium | BSD-3; new dependency | No | `inference/calibration.py` |
| Equal-budget external baselines (PySR, BoTorch) | Removes a straw-man risk | High | Pilot-scope | Apache/MIT; Julia/PyTorch weight | Yes (§10.5) | Provider runners exist |

No numerical improvement percentages are claimed.

## Final decision

1. **Genuinely new defects:** FDA-01..05, 07..18, 20 and 24..26 are new root causes. FDA-06, 12, 19, 21, 22 and 23 are new variants of known items. In total there are 6 MAJOR and 20 MINOR defects, plus 8 observations.
2. **Confirmed vs suspected:** none is EXECUTED_REPRODUCED.
   - **Confirmed:** FDA-01..08 and FDA-10..20 are SOURCE_PROVEN and survived an independent disproval attempt. Some of them carry a STATIC_SUSPICION component in their reach. FDA-10 also carries a CONTRACT_AMBIGUITY component.
   - **Not cross-reviewed:** FDA-09 (CONTRACT_AMBIGUITY) and FDA-21..26 have a single reviewer plus the lead's reading.
   - **Suspicions only:** the hypotheses in §D.
3. **Can lead to false scientific conclusions:** FDA-01, FDA-02, FDA-03 and FDA-04 directly. FDA-05 and FDA-06 can produce a false benchmark lift. FDA-09, FDA-12 and FDA-14 can mislead conditionally.
4. **Block the intended Blindfold benchmark:** FDA-05 and FDA-06 (pre-freeze), FDA-18 (while FDA-05 is open) and FDA-19 (lift verification). All of these are in addition to the known B-LEAK.
5. **Affect only unrelated capabilities:** FDA-03, 10–13, 15, 17, 23–26 and FDA-04/FDA-14 (MCP product). FDA-01, 02, 07–09 affect the authority core but not Genesis-lite.
6. **Best solved with existing packages:** FDA-04, FDA-14 and FDA-15 (SciPy QMC and NumPy quantile methods). Library test oracles suit FDA-17, FDA-21 and O-1.
7. **Must remain proprietary:** replay, identity, certification and state-clock semantics; source arbitration; escrow and evaluator scoring rules.
8. **Ten highest-value next steps:**
   1. Authorize R-01 (FDA-01).
   2. Authorize R-02 (FDA-02).
   3. Authorize R-05 (FDA-05) on the stdlib evaluator.
   4. Design the FDA-05 width bound and FDA-06 cap in v0.3.
   5. Bind and compare uncertainty in replay.
   6. Clock-tie preflight.
   7. Coincident-source refusal.
   8. MCP sampler and quantile replacement.
   9. Extend the isolation probe to the Genesis-lite secret inventory.
   10. O-1 null-calibration study plus gate-constant audit (BVB-0).
9. **Owner approvals required:**
   - Execution of each reproduction.
   - OD-3 for certified files (replay, certification, authorities, state, records, properties, validation, schemes, escrow, symbolic_regression, mapping, runtime, claims).
   - Core Freeze review for FDA-15.
   - OD-19 / BVB-1 for v0.3 content.
   - OD-20 for isolation.
   - A product-behaviour decision for the MCP tool.
   - Merge of #169 (INT-1) before OD-3.
10. **Shortest evidence-backed path:**
    1. Merge #169.
    2. Run the authorized R-01/R-02/R-05 reproductions.
    3. One certified repair batch (FDA-01/02/03/07/08/09) plus the P0 tree.
    4. Linux 3.11/3.12 FAST tier, then the OD-3 recertification (G0 Route 1, together with the open OD dispositions and D4).
    5. In parallel, draft v0.3: P-1..P-5 plus FDA-05/06/18/19/21/22 and O-1. Then the pilot-scope overhead measurement, OD-20 with independent attack arms, and OD-19.
    6. Formal ≥ 20-seed baselines.

    For the Real Engineering Demo, FDA-02 and FDA-01 must be closed first, because the flagship system-runtime and replay paths are exactly where they live.

**Stop.** No repairs, contract changes, source edits, broad tests or merges were performed.
