# Scientific Findings Closure Plan — Deep Audit 2026-10-19

> **PLANNING DOCUMENT · SCRATCH ONLY · NOTHING IMPLEMENTED · NOTHING APPROVED**
>
> - No reproduction, test, mutation, benchmark or Genesis measurement was run to prepare this plan. The owner's
>   stop instruction on further reproductions is preserved.
> - The only commands executed were read-only `git` queries, `sha256sum`, and one stdlib-only integrity script over
>   scratch files (`../verify_package.py`, run with `python -I -S`). The script reads no repository code.
> - No repository file, certificate, ledger, PR #169 or benchmark identity was touched.

Companion documents:
- `SCIENTIFIC_FINDINGS_OWNER_DECISIONS.md`
- `GENESIS_BLINDFOLD_BLOCKER_MATRIX.md`

## 1. Evidence verification and preservation (Step 1)

### 1.1 Source identity

| Item | Value |
| --- | --- |
| Worktree | `D:/forge-main-337519d1` |
| Branch | `fix/p0-scientific-correctness-2026-10-18` |
| HEAD | `abed661f0d551f352e7a2c451d0df7fcc22bde5c`. It equals `origin/…` (`git ls-remote`). PR #169 is OPEN and was not touched. |
| Tree | `7f965f0da21ca17f1b7dff7b79962b04d86c9a50` |
| GitHub `main` | `68502ad1457ffb3fe160b87729e1d586c6413875` |
| Working tree | Identical to HEAD, plus two untracked docs: the D4 review and the Genesis Step-0 review. |
| Concurrent writer (observed at plan completion) | Six **new untracked** files appeared in the worktree during this planning task: `docs/work/BVB_40_ALGORITHM_INVENTORY.md`, `BVB_LICENSE_AND_DEPENDENCY_AUDIT.md`, `BVB_NUMERICAL_EQUIVALENCE_PLAN.md`, `BVB_OWNER_DECISIONS.md`, `BVB_PRE_BLINDFOLD_ROADMAP.md`, `BVB_SCIENTIFIC_COMPARISON_MATRIX.md`. This session did not create them, and they were neither read nor touched. Another agent is writing into this worktree. Any evidence-preservation PR must exclude them unless their owner decides otherwise. |
| Tracked-file hash index | `bf233a73a046225a225aea4f9101e64f0402d37509a095a6b5e22714c8dad08f` over 5,289 src/tests/benchmarks/tools files. It is identical at audit start, before and after each of R-03..R-06, and now. |

### 1.2 Integrity check (executed on scratch files only)

`../verify_package.py` results:
- All 13 required reports are present and non-empty.
- Each of the four run records (`R-0x.json`) matches its script, stdout and stderr SHA-256. Each has exit code 0, HEAD before = after = `abed661f`, tracked hash before = after, and 0 new `.pyc` in the repository. Every stdout ends with `VERDICT …: REPRODUCED` and `CONTROL_OK: True`.
- Register: 26 unique findings (6 MAJOR, 20 MINOR), 8 observations, 0 labelled BLOCKER. `EXECUTED_REPRODUCED = 5`: FDA-03, FDA-04, FDA-05, FDA-06 and FDA-14. **Note:** 5 findings were reproduced by **4** runs, because R-04 covered both FDA-04 and FDA-14.

Full manifest: `../EVIDENCE_MANIFEST.sha256`. It covers 49 files, and its own SHA-256 is
`94d75936f930baebcea7e6f4db27444cb613e00fcbc5dd0dad25fd21ac0c147e`.

| File | SHA-256 |
| --- | --- |
| package/FORGE_DEEP_SCIENTIFIC_DEFECT_AUDIT.md | `91ddff5f9765ac51…` |
| package/FORGE_NEW_FINDINGS_REGISTER.json | `69f660a59422e04b…` |
| package/FORGE_SCIENTIFIC_RISK_MATRIX.md | `6bd78c66e5a9f6c0…` |
| package/FORGE_ADVERSARIAL_REPRODUCTION_PLAN.md | `bfe441d7972aca8f…` |
| package/FORGE_BUILD_VS_BUY_DEFECT_OPPORTUNITIES.md | `bd4c00c36bfd766d…` |
| repro/r03_material_arbitration.py · R-03.out · R-03.json | `d5de692dbeb4f1bc…` · `b271275bf287f73e…` · `01f085bc945833d0…` |
| repro/r04_mcp_uq.py · R-04.out · R-04.json | `6097afe9d77f1232…` · `184a33f4765b97ce…` · `433d8703a50eb0f3…` |
| repro/r05_vacuous_pair.py · R-05.out · R-05.json | `f7e1da48b150f48c…` · `e555856efad14cc9…` · `f448f2a8d29b9815…` |
| repro/r06_spurious_cap.py · R-06.out · R-06.json | `d2c3fe1d4d5ca3b2…` · `ba7b5a95c205bae5…` · `c97f2f91691f4330…` |
| repro/run.sh · bootstrap/sitecustomize.py | `94c763b2f34c119d…` · `7dc1438d65600499…` |
| reviewer_A..E.md | `e8deac01…` `7779e6b4…` `6f0ebe70…` `5cf6364d…` `c018e4dd…` |
| crossreview_X1..X3.md | `be17a5f6…` `41ddfd6e…` `b98aa7b4…` |

The full 64-hex values are in the manifest.

### 1.3 Proposed durable destination (requires owner approval; nothing written)

**Recommended: an in-repository, new and dated directory, landed through its own docs-only PR.** It must not go
into PR #169.

```text
docs/work/evidence/deep_audit_2026_10_19/
  README.md                  # source commit abed661f, tree 7f965f0d, hash-index bf233a73, scope, NOT-certified label
  EVIDENCE_MANIFEST.sha256   # recomputed after copy; must equal the scratch manifest line for line
  .gitattributes             # "* -text" so git never rewrites line endings (byte pins)
  package/   repro/   reviewers/   crossreviews/   derivations/   closure/
docs/work/DEEP_SCIENTIFIC_DEFECT_AUDIT_2026_10_19.md   # short pointer + findings table, links into the directory
```

Provenance and no-overwrite rules:
1. **New directory name.** The date-stamped path is new. The procedure first checks `test ! -e` on the path and refuses to write if it exists, so no historical evidence directory can be touched.
2. **Byte copy, not text write.** Copy the files as bytes (`cp`), never by re-serialising them. This repository's SHA-256 pins break on CRLF injection (memory note). The nested `.gitattributes` with `-text` prevents git from normalising line endings.
3. **Verify.** After copying, recompute every SHA-256 and compare it with `EVIDENCE_MANIFEST.sha256` (manifest digest `94d75936…`). Any mismatch aborts the commit.
4. **Bind the README to the source.** The README states `abed661f` and the tree and hash-index values. It states that R-03..R-06 ran on Windows CPython 3.14.2 in the phyx venv, which is not the supported certification platform. It labels everything UNCERTIFIED and "static unless marked EXECUTED_REPRODUCED".
5. **Isolated worktree.** Work in a fresh worktree branched from `origin/main` (or from the #169 tip once it merges), never in the shared checkout (memory note). Use one docs-only commit and a separate PR. That PR touches no certified file and should classify as an ordinary docs change. Check that classification before pushing.
6. **Record in `docs/work/PROGRESS.md`.** CLAUDE.md requires every executed command, with its result, to be appended there. R-03..R-06 were executed, so this record is **owed** and is pending only on write approval. Append; never rewrite earlier entries.
7. **Guard check before pushing.** The `.py` scripts under `docs/work/evidence/` follow existing precedent (`p0_exact_kernel_analysis.py`). Even so, run the full TARGETS dependency-guard check before pushing (memory: string-form scans), or store the scripts with a `.py.txt` suffix. The owner should choose (see the decision file).

Alternative (not recommended): keep the evidence outside the repository (for example `D:/forge-evidence/…`) and
commit only the manifest. The B-LEAK raw evidence sits outside the repository today, and this review already
flagged that as a provenance weakness.

## 2. Register confirmation (Step 2)

| Count | Reported | Verified |
| --- | --- | --- |
| MAJOR | 6 | 6 (FDA-01..06) |
| MINOR | 20 | 20 (FDA-07..26) |
| OBSERVATION | 8 | 8 (OBS-01..08) |
| Executed reproductions | 5 | 5 findings EXECUTED_REPRODUCED, by 4 runs (R-03..R-06) |
| Newly classified BLOCKER | 0 | 0 |

**On the absence of BLOCKER labels.** The audit's BLOCKER definition was "established defect directly causing
false support … or broken benchmark isolation". The audit assigned none, mainly because reach was latent, or because
false support needed a second ingredient. **That does not lower the closure priority.** Three of the confirmed
MAJOR findings violate a CLAUDE.md authority invariant outright, and each of these is now executed evidence:
- FDA-05: UNKNOWN can improve an answer (0.5 → 1.0).
- FDA-04: missing uncertainty becomes zero.
- FDA-03: sources are arbitrated.

The closure plan treats all three, together with FDA-06, as **must-fix before any dependent claim**. For
Genesis-lite, FDA-05 and FDA-06 are treated with the **same force as a formal-measurement blocker**: the benchmark
scoring cannot be frozen with them in place. The plan does not relabel them.

Known blockers stay separate from the new findings:

| Known formal-measurement / gate blockers (pre-existing) | Newly discovered (this audit) |
| --- | --- |
| B-LEAK same-account answer leakage (measured) | FDA-05, FDA-06 (scoring/lift rule; executed) |
| G0 not exited: stale certificate `05522b59`, P0 tree not merged (#169 open), OD-22..34 dispositions, D4 UNCLASSIFIED | FDA-18, FDA-19, FDA-21, FDA-22 (v0.3 benchmark-design items) |
| No formal driver or fresh root (P-4), no environment manifest (P-5), own-generator held-out, OD-8/18/19/20 open | FDA-01, FDA-02, FDA-03, FDA-04, FDA-14 (authority/product correctness; not on the Genesis-lite path) |
| O-1 bootstrap-"p" calibration unresolved (static) | — (O-1 is known; this plan only deepens its analysis) |

## 3. Prioritised closure assessments (Step 3)

Abbreviations:
- **SP** = SOURCE_PROVEN.
- **ER** = EXECUTED_REPRODUCED, on Windows CPython 3.14.2 at `abed661f`.
- **Cert** = file in `certification/current_core_v2.json`.
- **Prereg** = file pinned by the Genesis-lite preregistration, so a change is a new benchmark identity.

### 3.1 FDA-05 — INDISTINGUISHABLE pair credit has no width bound (Genesis-lite scoring)

| Aspect | Assessment |
| --- | --- |
| Root cause | Both scoring implementations accept a pair when the truth lies in `[min(A,B)(1−tol), max(A,B)(1+tol)]` at ≥ 90 % of evaluation points. Nothing bounds how far apart A and B may be outside the box. A pair diverging without limit brackets every finite truth. |
| Evidence: confirmed | **ER (R-05).** One pair built only from an in-box fit and the public box edge (A/B = 1.3×10³⁰ at the region edge) scored `indistinguishable_hit`, credit +1.0, for **two mutually exclusive truths**. The evaluator and the escrow agree. All four negative controls behaved as expected. SP: grammar admissibility (finite constants; negative exponents allowed; node and depth limits met). |
| Evidence: unconfirmed | Population hit rate (X3 independent simulation: 0.771) and expected credit (+0.54 to +0.89 against +0.50 for refusal) on the real generator. Whether a full `lift_decision` could be flipped, which needs a kind-separating tell (FDA-18, FDA-22, B-LEAK). |
| Affected paths | `benchmarks/genesis_lite/evaluator/score.py:90-117` (`_pair_hit`) [Prereg]; `src/engcore/blindfold/escrow.py:570-610` (`_assess_pair`) [Cert, verdict_authority; also Prereg substrate]; credit table `score.py` `CREDIT` and `engcore.blindfold.roles.DEFAULT_CREDIT` (rule unchanged). |
| Scientific consequence | Violates "UNKNOWN never improves an answer". The honest refusal (+0.5) is dominated by a statement that carries no extrapolation knowledge. The INDISTINGUISHABLE kind stops measuring the recognition of non-identifiability. |
| Affected capabilities / claims | Genesis-lite v0.2 scoring; any Blindfold assessment of INDISTINGUISHABLE claims; every future lift claim (Step-2) and Graduation. The production claims runtime is not affected. |
| False PASS reachable? | **A false per-universe hit is reachable (ER).** A false benchmark *lift* PASS is **not demonstrated**. Blanket use costs −0.5 on discoverable worlds and fails per-kind non-inferiority. It would need a tell that separates the kinds. |
| Minimum correct repair | Add a **preregistered outside-box informativeness bound** to both implementations: at evaluation points outside the box, require `max(A,B)/min(A,B) ≤ 1 + w`, with `w` declared, for example as a multiple of `tol`. Alternatively, make the credit decrease with the bracket's log-width. Keep the existing conditions. Change both implementations together (they must agree, or the run is `EVALUATOR_DISAGREEMENT`). Bump `EVALUATOR_SCHEMA` and the escrow assessment version. |
| Required contracts and tests | (a) Preregistration v0.3 rule text, with the `w` rationale. (b) The escrow `_assess_pair` docstring. (c) Tests: the R-05 vacuous pair must be a **miss** in both implementations, for both truths. The informative pair (law, rival) must still **hit**. The in-box-disagreeing pair must still miss. The evaluator/escrow agreement test must cover the new condition. (d) An attack arm, "vacuous pair", in `tests/genesis_lite/attack_arms.py`, expected to be refused. |
| Compatibility / identity | New benchmark identity (v0.3). v0.2 pilot results stay historical and are **never re-scored silently**. The credit digest is unchanged if only the rule changes, but the evaluator code identity moves. |
| Certification | `escrow.py` is certified → OD-3. `score.py` is outside certificate scope but prereg-pinned. |
| Owner decisions | ODC-05a: the form of the bound (ratio cap or graded credit) and the value of `w`. ODC-05b: whether bracket crediting stays at all. ODC-05c: landing in v0.3 only (recommended). |

### 3.2 FDA-06 — out-of-family worlds capped only for `discoverable`

| Aspect | Assessment |
| --- | --- |
| Root cause | `analysis.out_of_family` reads the flag only from the discoverable universe and keys it per world set. `_capped` applies the cap only when `k == "discoverable"`. `spurious_correlate` (and, statically, `confounded`) can earn +1.0 through `law_pass` without being capped. |
| Evidence: confirmed | **ER (R-06).** With both truths flagged out of family, discoverable 1.0 → 0.0 but spurious stays 1.0, and the paired primary difference is +1.0. The control behaved as expected. SP: `harness.py:330` already emits `truth_in_searched_family` for **every** universe, so the information exists and is ignored. |
| Evidence: unconfirmed | The run covered `world_credits`, `out_of_family` and `_capped`, not the full `lift_decision`. **Static extension:** `confounded` also awards `law_pass` = +1.0 and is equally uncapped. This was not executed and is flagged for the repair's tests. The size of the gain on the real grid (D's ~+0.6 per world set) is unmeasured. |
| Affected paths | `benchmarks/genesis_lite/analysis.py:131-145, 192-196` [Prereg]. |
| Scientific consequence | Violates Genesis §10.5 rule 4: no lift from a class without a strong applicable baseline. A candidate whose only advantage is grammar reach is credited as reasoning. |
| Affected capabilities / claims | The Genesis-lite lift decision (Step-2), Graduation. Nothing in production. |
| False PASS reachable? | **A false credit contribution is reachable (ER).** A false lift PASS is plausible but not demonstrated, because all other lift conditions must also hold. |
| Minimum correct repair | Make `out_of_family` return per (world set, kind). In `_capped`, cap **every kind whose credit can come from a law** (discoverable, spurious_correlate, confounded) when that universe's truth is out of family. Refuse records lacking the flag for those kinds. |
| Required contracts and tests | Reconcile the prereg wording (`amends/changes/3`, "discoverable") with §10.5 in v0.3. Tests: R-06 as a permanent negative control; an in-family spurious world is not capped; a confounded out-of-family world is capped; a record missing the spurious or confounded flag is refused. |
| Compatibility / identity | v0.3 identity. The RunRecord already carries the field, so there is no schema change, only analysis semantics. |
| Certification | Not certified; prereg-pinned. |
| Owner decisions | ODC-06a: §10.5 governs over the v0.2 wording. ODC-06b: include `confounded`. |

### 3.3 FDA-01 — assembly replay does not reproduce uncertainty, validation or units

| Aspect | Assessment |
| --- | --- |
| Root cause | `compare_runs` compares identities plus scalar final magnitudes only. It skips the `_uncertainty`, `_edge_uncertainty` and `_coupling_error` blocks, field outputs, units, and the replay's recomputed system validation, uncertainty and verification. `external_uncertainty` is an argument of both execution and replay, and is not bound into the GraphPlan identity. |
| Evidence: confirmed | SP, confirmed by the lead and X1. X1 largely refuted the reviewer's original trigger (a code change inside a UQ implementation is caught by the pack implementation fingerprints). The caller-uncertainty trigger survives with no code change. |
| Evidence: unconfirmed | **Not executed (R-01 declined).** That certification's COMPUTATIONAL_REPLAY_VERIFIED gate then passes on stored, unreproduced UQ was traced statically, not observed. |
| Affected paths | `src/engcore/assembly/replay.py:531-546, 549-638, 650, 675` [Cert]; `assembly/multiphysics.py:877-889, 944-1044` [Cert]; `assembly/certification.py:456-566` [Cert]. |
| Scientific consequence | A replay attestation states more than it checked. Evidence produced under one declared input-uncertainty context certifies a run whose UQ was never reproduced. This touches "evidence bound to its context" and "missing uncertainty never improves". |
| Affected capabilities / claims | Assembly multiphysics runs with declared external UQ or system UQ/validation; assembly certification. Not the claims-runtime replay (`claims/replay/bundle.py`, a separate path), and not Genesis-lite. |
| False VERIFIED reachable? | **A false replay-verified attestation is reachable by source (SP, not executed).** No path from it to a claims SUPPORTED verdict was traced. |
| Minimum correct repair | (1) Bind the declared `external_uncertainty` into the authorized run identity, and make replay use the bound value: either refuse a caller-supplied value that differs, or drop the parameter. (2) Under the replay policy, compare the UQ, coupling-error and recomputed system UQ/validation/verification blocks: kinds and UNKNOWN status exactly, numbers within tolerance. (3) Compare output units exactly. (4) Correct the docstring. |
| Required contracts and tests | Replay-policy contract text: what "REPLAYED_MATCH" attests. Tests: replay with `external_uncertainty=None` against a quantified original is **not** a match; a changed edge uncertainty is detected; a K→degC relabel with equal magnitude is detected; an identical replay still matches. The first test, run first on unrepaired code, is the executed reproduction (it needs explicit approval at repair time). |
| Compatibility / identity | Binding UQ into the plan moves authorized-run digests. Prefer a versioned identity field, so existing stored bundles remain readable as `/old` with a stated reduced replay scope rather than being refused or rewritten. Historical bundles are never regenerated in place. |
| Certification | Three certified files → OD-3. |
| Owner decisions | ODC-01a: bind or refuse. ODC-01b: tolerance policy for UQ blocks. ODC-01c: status of pre-repair bundles. |

### 3.4 FDA-02 — committed state not tied to the run's clock

| Aspect | Assessment |
| --- | --- |
| Root cause | The authority pins the plan fingerprint, so every run integrates the plan window from its own start. It reads initial values from `call.state` and commits `StateProposal(run.ended_at)`. Nothing compares the plan start with the committed state's time: `StateProposal` has no start instant, and `SystemState.next` refuses only backwards time. |
| Evidence: confirmed | SP, confirmed by the lead and X1. No authority reads the state time (grep). Two ordered committers on one owner are admissible (`plan.py:262-270`). |
| Evidence: unconfirmed | **Not executed (R-02 declined).** The derived consequence (two [0,10] s runs commit x = 20 at t = 10 when the true value is 10) is arithmetic, not observed. |
| Affected paths | `src/engcore/system_runtime/authorities.py:206-221, 339-340, 407`; `records.py:171-187`; `state.py:204`; `executor.py:356-365`. All are Cert. |
| Scientific consequence | Wrong admitted state with a valid-looking receipt chain. Replays faithfully reproduce the wrong commit. |
| Affected capabilities / claims | The system runtime with MultiphysicsAuthority/MultiscaleAuthority committers. Today `flagships/forge_flagships/battery_cooling.py:639` is the only production committer, so the defect is **latent**. The drone product chain uses `MultiphysicsRuntime` directly (`systems/products/drone_coupled.py:41`), not the system runtime. |
| False result reachable? | A wrong committed numerical state is reachable by source. Its reach is latent. |
| Minimum correct repair | **Preflight and commit check only, no schema change.** Refuse, as REFUSED and not FAILED (aligned with the OD-30 taxonomy), when the plan start ≠ the state's time, compared exactly in Fraction seconds. Apply this in both authorities. Optional and stronger: a start instant in `StateProposal`, checked at commit; that is a schema bump. |
| Required contracts and tests | State-transition contract: a proposal advances from the committed state's time. Tests: a second commit of the same plan is refused; a [100,200] plan from t = 0 is refused; a matched start passes; the cell-cooling flagship path is still admitted. |
| Compatibility / identity | The preflight variant moves no digests. The schema variant bumps `PROPOSAL_SCHEMA`. |
| Certification | Certified → OD-3. |
| Owner decisions | ODC-02a: preflight only, or a schema field. ODC-02b: refusal class. |

### 3.5 FDA-03 — material interpolation arbitrates conflicting sources

| Aspect | Assessment |
| --- | --- |
| Root cause | The interpolation bracket uses `below[-1]` / `above[0]` after a stable position sort over data pre-sorted by `claim_id`. Coincident positions are never detected, so the claim-id spelling picks the source. The exact-position branch refuses the same conflict. The coverage `conflicted` property requires `rule is None`, so it cannot see this case. |
| Evidence: confirmed | **ER (R-03).** The same two conflicting 300 K data gave `known` INTERPOLATED 25.0, or 20.0 after swapping ids. 300 K exactly gave UNKNOWN "sources are not arbitrated". Coverage at 350 K reported `conflicted=False`. Control: with no coincident data the result does not depend on the id. |
| Evidence: unconfirmed | Production reach. No `src` producer of an `InterpolationRule` was found outside tests (X2), so the defect is latent. |
| Affected paths | `src/engcore/materials/properties.py:272, 329-366` [Cert]; `materials/coverage.py:13-14, 71-74`; consumers `spatial/fields.py:197-216`, `pde/cases.py:42`. |
| Scientific consequence | Violates "sources are not arbitrated" (BR-15 AUTHORITY_CRITICAL) and the coverage contract that conflicts are listed. An arbitrated coefficient is admitted as a known material property. |
| Affected capabilities / claims | Material-property-driven PDE/field coefficients, when an interpolation rule exists. Not M1C (SOURCED only). Not Genesis-lite. |
| False SUPPORTED reachable? | A false `known` property is reachable (ER). Its propagation to a claim verdict was not traced, and is latent. |
| Minimum correct repair | In interpolation, refuse when any bracketing position carries more than one admitted datum. Return UNKNOWN with the existing reason, naming every coincident datum, which is consistent with the exact-match branch. Make `conflicted` true for this case. |
| Required contracts and tests | R-03 as a permanent negative control (both id orders → UNKNOWN; coverage conflicted). The exact-position refusal is unchanged. Non-coincident interpolation is unchanged. |
| Compatibility / identity | Results change only for sets with coincident positions, which become more UNKNOWN. There is no schema change. |
| Certification | Certified → OD-3. |
| Owner decisions | ODC-03a: refuse even when the coincident values agree (recommended, consistent with the exact branch). |

### 3.6 FDA-04 — deterministic "independent" inputs are exactly anti-correlated (MCP UQ tool)

| Aspect | Assessment |
| --- | --- |
| Root cause | Column c uses quantile index `(i·s_c + c) mod n`, with odd strides coprime to n. Some column pairs are exact reverses of each other. Nothing relates the input count to `sample_count`. |
| Evidence: confirmed | **ER (R-04).** n=4 with 3 inputs, and n=32 with 17 inputs: Y = Xa + Xb gave `status=completed`, lower = upper, sd 0. Control (n=32, 2 inputs): width 1.68. |
| Evidence: unconfirmed | Effects on real engineering outputs through `answer_engineering_uncertainty`, which run the solver; this was not executed. |
| Affected paths | `src/engcore/mcp/probabilistic_uq.py:29-85` (not certified); caller `mcp/server.py:885-918` (`answer_engineering_uncertainty`). |
| Scientific consequence | Violates "missing uncertainty never becomes zero". The recorded `conditional_on` "independent" is false for the realised design. |
| Affected capabilities / claims | The MCP engineering-uncertainty product tool and its clients. No claim verdict consumes it. |
| False SUPPORTED reachable? | No verdict path. A **false completed zero-width interval is reachable (ER)**. |
| Minimum correct repair | Replace the lattice with a seeded, scrambled `scipy.stats.qmc.LatinHypercube` (deterministic given the recorded seed). Add a refusal diagnostic for any column-pair rank correlation above a declared bound. Bump the result schema and method label. Separately, move the computation out of `engcore.mcp` (known O-4). |
| Required contracts and tests | R-04 cases as negative controls; a property test over n ∈ [4,256] and k ≤ the maximum allowed showing no pair with \|r\| above the bound; reproducibility (same seed, same samples). |
| Compatibility / identity | Every output value changes; `engineering_probabilistic_uq/1` → `/2`. |
| Certification | None (MCP is uncertified). This is a product-behaviour decision. |
| Owner decisions | ODC-04a: QMC replacement plus diagnostic. ODC-04b: relocation from MCP (O-4) now or later. |

### 3.7 FDA-14 — the stated central mass is not the realised mass

| Aspect | Assessment |
| --- | --- |
| Root cause | Inputs sit at stratum midpoints `(i+0.5)/n`, but the interval is read with NumPy's default type-7 quantile. Its plotting positions differ, so the realised mass is 0.95 − 0.95/n. |
| Evidence: confirmed | **ER (R-04).** 0.7125 at n=4 and 0.9203 at n=32, equal to the closed form. |
| Evidence: unconfirmed | Behaviour for non-monotone outputs, where the empirical quantile also carries unquantified design error. |
| Affected paths | `mcp/probabilistic_uq.py:47, 138-141`. |
| Scientific consequence | Intervals are narrower than the `credible_mass` they state. The sampling error of the quantile estimate is unreported, so a missing uncertainty is presented as absent. |
| Affected capabilities / claims | As for FDA-04. |
| False SUPPORTED reachable? | No verdict path. Over-narrow intervals are reachable (ER). |
| Minimum correct repair | `method="hazen"`, matching the midpoint design. Report the achieved mass. Refuse a central mass whose tails are below the design resolution (for example 2.5 % tails with n < 40) rather than interpolate. Label the interval an estimate with unquantified design error. |
| Required contracts and tests | Contract clarification of what `credible_mass` means for a deterministic design. Tests: monotone Y = X0 realised mass equals the stated mass to design resolution; small n is refused. |
| Compatibility / identity | Interval values change; ship together with the FDA-04 schema bump. |
| Certification | None. |
| Owner decisions | ODC-14a: minimum n rule. ODC-14b: wording of the estimate label. |

### 3.8 O-1 (known) — bootstrap "achieved significance" fed to Holm

| Aspect | Assessment |
| --- | --- |
| Root cause | `analysis.bootstrap_mean_ci` (`:148-157`) returns as "p" the fraction of 2,000 resampled means ≤ 0. The resampling uses `random.Random(0)`. That fraction goes into a Holm step-down over the 5-member family (`:297-301`). |
| Evidence: confirmed | SP: the code is exactly that. |
| Evidence: unconfirmed (static derivation only; nothing executed) | (a) The bootstrap distribution is centred at the observed mean, so the fraction ≈ Φ(−x̄/(s/√n)) with the plug-in (1/n) variance. That is a one-sided z-test p-value: approximately valid at formal sizes (600 world sets per presentation, 2,400 pooled), and **anti-conservative at small n or with heavy skew**. (b) **Monte-Carlo resolution:** at p ≈ 0.01, the smallest Holm threshold (0.05/5), the resampling standard error is √(0.01·0.99/2000) ≈ 0.0022, about 22 % relative. With the seed fixed, the decision near the threshold is deterministic but arbitrary relative to the ideal bootstrap. (c) Holm is valid under arbitrary dependence, so the shared seed across family members does not invalidate it. Each p must still be super-uniform under the null. (d) Ties at 0 are counted as ≤ 0, which is conservative. |
| Affected paths | `benchmarks/genesis_lite/analysis.py:148-157, 297-301` [Prereg]. |
| Scientific consequence | The family-wise error claim of the lift rule rests on unverified calibration. |
| Affected capabilities / claims | Step-2 lift decisions and Graduation. |
| False benchmark PASS reachable? | Not demonstrated. The risk concentrates in decisions near the threshold. |
| Minimum correct repair | Either (A) keep the bootstrap but **preregister** a calibration study (under a known null, at the formal grid size and pilot-derived variance, confirming rejection rate ≤ α within Monte-Carlo error) and raise the resample count so threshold decisions are stable; or (B) replace the "p" with an **exact paired sign-flip (randomisation) test** on world-set differences, valid under a symmetric null, or a t-test, keeping the bootstrap CI as the effect-size bound. |
| Required contracts and tests | Preregistration v0.3 statistics text. A test-only oracle against `scipy.stats.permutation_test`, `scipy.stats.bootstrap` and statsmodels `multipletests(method="holm")` (test dependencies only, never in the evaluator). |
| Compatibility / identity | v0.3 identity. |
| Certification | Not certified. |
| Owner decisions | ODC-O1a: route A or B. ODC-O1b: authorize the calibration study when appropriate; it executes code, so it needs separate approval. |

### 3.9 B-LEAK (known) — proposer can recover hidden answers (formal-measurement blocker)

| Aspect | Assessment |
| --- | --- |
| Root cause | The proposer is a same-account child of the operator (`harness.py:61-66`). The escrow and master seed live in the operator process (`InProcessTransport`, `harness.py:230-231`). The command line exposes `--root-file`. There is no network or persistence isolation, and the benchmark package is writable. |
| Evidence: confirmed | Measured 2026-10-14: 5 of 6 true laws recovered with the run still VALID; outbound TCP; a detached child; writes into the package. The raw evidence is **outside the repository**. SP: transports are labelled `SECURITY_BOUNDARY_NOT_PROVEN`. |
| New findings that extend it | FDA-19: the isolation demo's leak scan covers escrow storage only, not the Genesis-lite root file, derived seeds or run logs. OBS-04: the pilot run log reveals kinds while worlds are reused (duplicate). FDA-18: in-campaign answer exclusivity (a design tell). |
| Affected paths | `benchmarks/genesis_lite/harness.py`, `proposer_host.py`; `src/engcore/blindfold/escrow.py`, `escrow_server.py`, `isolation.py`, `isolation_probe.py`. |
| Consequence | Hidden answers are not hidden, so no formal measurement is valid. |
| Affected capabilities / claims | Genesis-lite formal tier, Step-2, Graduation. **Not** the Real Engineering Demo and not production claims. |
| False benchmark PASS reachable? | **Yes, measured** (VALID runs with leaked laws). |
| Minimum correct repair | Readiness §2's five conditions: an isolation deployment (no process/command-line visibility, no operator files, no network, no persistence, read-only benchmark code); wired into the harness (P-1, with P-2 only alongside it); in-repository attack arms for each measured attack (P-3); an independent rerun of the escrow probe with a preserved transcript; owner acceptance (OD-20). **Add:** extend `isolation_probe` to scan the Genesis-lite secret inventory (FDA-19), and keep run logs outside the proposer's reach until all arms have finished (OBS-04). |
| Required contracts and tests | Attack arms for command-line/root-file, network, persistence, code-write and run-log read, each required to be refused. |
| Compatibility / identity | Changes prereg-pinned harness files → v0.3. |
| Certification | `blindfold/*` is certified → OD-3 for the probe extension. |
| Owner decisions | OD-20 (deployment), OD-B2/OD-19 (v0.3), ODC-BL1 (probe-scope extension). |

## 4. Build vs Buy per finding (Step 5)

FORGE trust authority stays proprietary in every case. No external package is proposed for replay, identity,
certification, state, arbitration, escrow or scoring semantics.

| Finding | Local correctness repair | Mature external library | Independent baseline | Contract clarification | Validation / negative controls |
|---|---|---|---|---|---|
| FDA-05 | **Primary**: width bound in evaluator and escrow | — (FORGE rule; the evaluator stays stdlib-only) | Adversarial "vacuous pair" attack arm | **Required** (prereg v0.3 rule text) | R-05 as a permanent control |
| FDA-06 | **Primary**: per-kind cap | — | — | **Required** (§10.5 vs prereg wording) | R-06 plus a confounded control |
| FDA-01 | **Primary**: bind and compare UQ | — | — | **Required** (what REPLAYED_MATCH attests) | Perturbed-declared-input replay challenge |
| FDA-02 | **Primary**: clock check | — | — | Required (transition contract) | State-clock invariant tests |
| FDA-03 | **Primary**: coincident refusal | — | — | Coverage-contract alignment | R-03 control |
| FDA-04 | Diagnostic and refusal | **Primary**: `scipy.stats.qmc.LatinHypercube` (already a dependency) | — | Schema / label | R-04 plus a correlation property test |
| FDA-14 | Minimum-n refusal, achieved mass | **Primary**: NumPy `method="hazen"` | — | **Required** (`credible_mass` meaning) | Monotone-mass test |
| O-1 | Resample count / test choice | Test-only oracles: SciPy permutation/bootstrap, statsmodels Holm | — | Prereg statistics text | **Primary**: null-calibration study |
| B-LEAK | Harness wiring, probe scope | OS isolation primitives (containers / namespaces / accounts); not a scientific library | — | OD-20 deployment statement | **Primary**: attack arms plus an independent probe rerun |

## 5. Shortest safe scientific closure path

Every step needs explicit owner approval. Steps are ordered by dependency, not effort.

1. **Preserve the evidence.** Approve the docs-only PR in §1.3 (ODC-EV1) and the owed PROGRESS.md record (ODC-EV2). This is independent of #169.
2. **Decide.** Settle ODC-01..06, ODC-14, ODC-O1, ODC-CL1 and the OD-B1 reading. See the owner-decision file.
3. **Land INT-1.** Merge #169, the P0 + D1–D3 base. Every later certified repair builds on it.
4. **Repair Batch A (certified authority; one branch; failing tests first).** FDA-01, FDA-02, FDA-03, and the escrow half of FDA-05 (plus the FDA-19 probe scope). Running the failing-first tests is itself execution, so it needs approval at repair time. That run converts FDA-01 and FDA-02 to executed evidence. Optional MINOR riders: FDA-07/08/09.
5. **Repair Batch B (uncertified MCP).** FDA-04 and FDA-14. These can land independently and early.
6. **v0.3 Genesis-lite amendment (prereg-pinned, docs and benchmarks).** FDA-05 evaluator half, FDA-06, the O-1 route, FDA-18/21/22, P-1..P-5. Bind it to the post-Batch-A escrow.
7. **One OD-3 recertification** on Linux 3.11/3.12, covering #169 + Batch A. Push once; a push cancels a running recertification. Together with the open OD-22..34 dispositions and D4, this is G0 Route 1.
8. **B-LEAK lift** under OD-20: deployment, attack arms, independent probe rerun, owner acceptance.
9. **OD-18 / OD-19 / OD-8, then freeze v0.3** and run ≥ 20-seed formal baselines (Step-1 gate).

The Real Engineering Demo (Step 2B) does not wait on Genesis-lite, but by contract it runs only after Step-2 PASS.
Its own dependencies are in the blocker matrix.

**Stop. Awaiting explicit owner approval.** Nothing is implemented, committed, pushed, merged or certified, and
PR #169 is unchanged.
