# Scientific Findings — Owner Decisions Required (Deep Audit 2026-10-19)

> **No decision below is approved.** Each recommendation is a proposal. Approving one decision implies no other.
> An approval to plan or repair is not an approval to execute tests, reproductions, commits, pushes, merges,
> certification or Genesis measurement. Each of those needs its own explicit approval.

Source: `abed661f` (PR #169 open). Evidence: `../EVIDENCE_MANIFEST.sha256` (`94d75936…`). Plan:
`SCIENTIFIC_FINDINGS_CLOSURE_PLAN.md`.

## A. Evidence and records

| ID | Decision | Options | Recommendation | Unlocks / blocks |
|---|---|---|---|---|
| **ODC-EV1** | Preserve the audit evidence durably in the repository | (a) new `docs/work/evidence/deep_audit_2026_10_19/` with a nested `-text` `.gitattributes`, byte copy, manifest re-verification, separate docs-only PR from a fresh worktree; (b) outside the repository with only a manifest committed; (c) leave in scratch | **(a)** | Durable provenance; avoids repeating B-LEAK's off-repository evidence weakness |
| ODC-EV1b | Form of the derivation and reproduction scripts in the repository | keep `.py` (precedent: `p0_exact_kernel_analysis.py`), with a full TARGETS dependency-guard check before pushing; or store as `.py.txt` | `.py`, plus the guard check | Avoids an unexpected red Formal control |
| **ODC-EV2** | Append the R-03..R-06 commands and results to `docs/work/PROGRESS.md` | approve the append in the same docs PR; or defer | **Approve** (CLAUDE.md requires recording executed commands; this record is currently owed) | Contract compliance |
| ODC-EV3 | PR #169 | leave unchanged (as instructed); or add audit docs to it | **Leave unchanged** | Keeps INT-1 scope clean |

## B. Classification and gate scope

| ID | Decision | Options | Recommendation | Unlocks / blocks |
|---|---|---|---|---|
| **ODC-CL1** | Step-0 classification of the new MAJOR findings | SCIENTIFIC_CORRECTNESS / GOVERNANCE_ONLY (six-question record) / UNCLASSIFIED | **SCIENTIFIC_CORRECTNESS** for FDA-01..06 and FDA-14. Each is a confirmed scientific-semantics defect. None fits a GOVERNANCE_ONLY kind. | Required for the G0 exit under either route; the Genesis Step-0 gate requires unresolved items to be classified |
| **OD-B1** (existing) | G0 exit scope: global or dependency-scoped | global (no SC/UNCLASSIFIED item open anywhere); dependency-scoped (only items the claim depends on) | **Global, fail-closed** (as recommended in the readiness review). Under it, FDA-01..04/14 block the G0 exit even though Genesis-lite does not call their code. | Decides whether Batch A + B must land before G0 exits (see the blocker matrix §2) |
| ODC-CL2 | Severity relabel | keep MAJOR; or relabel FDA-05/FDA-06 to BLOCKER for Genesis-lite | **Treat FDA-05/06 as freeze-blocking for Genesis-lite without relabelling** (the original audit's labels stay; the closure force is stated explicitly) | Prevents downgrading by label |

## C. Per-finding scientific design decisions

| ID | Finding | Decision | Options | Recommendation |
|---|---|---|---|---|
| **ODC-05a** | FDA-05 | Form of the informativeness bound for INDISTINGUISHABLE pairs | (i) hard ratio cap `max/min ≤ 1+w` outside the box; (ii) graded credit decreasing with log-width; (iii) remove bracket credit (credit only when one law passes) | **(i)**, with `w` preregistered and justified in the v0.3 text. Simplest and testable; preserves the honest-spread intent. |
| ODC-05b | FDA-05 | Value of `w` | a multiple of `tol`, or derived from the generator's rival amplitude | Decide from the rule's purpose. **Do not tune it on pilot or formal worlds.** |
| ODC-05c | FDA-05 | Where it lands | v0.3 only, never retroactively applied to v0.2 records | **v0.3 only** |
| **ODC-06a** | FDA-06 | Which contract governs | Genesis §10.5 rule 4 (cap every no-strong-baseline class), or the v0.2 prereg wording (discoverable only) | **§10.5**; amend the wording in v0.3 |
| ODC-06b | FDA-06 | Kinds covered by the cap | discoverable + spurious_correlate; or also confounded (law_pass +1.0; static extension, not executed) | **All three** |
| **ODC-01a** | FDA-01 | Replay treatment of declared external uncertainty | (i) bind it into the authorized-run identity, so replay uses the bound value; (ii) refuse any caller-supplied value at replay that differs from a recorded copy | **(i)**, with a versioned identity field |
| ODC-01b | FDA-01 | Comparison of UQ / validation blocks | exact for kinds and UNKNOWN status, policy tolerance for numbers; or exact throughout | **Exact kinds/status, tolerance for numbers** |
| ODC-01c | FDA-01 | Status of pre-repair stored bundles | readable, with a stated reduced replay scope (no UQ attestation); or refused | **Readable with reduced scope**; never regenerated in place |
| **ODC-02a** | FDA-02 | Clock binding mechanism | (i) preflight + commit check, no schema change; (ii) start instant in `StateProposal` (schema bump) | **(i) first**; (ii) only if a stored record must carry it |
| ODC-02b | FDA-02 | Outcome class of the mismatch | REFUSED (pre-run) / FAILED | **REFUSED**, consistent with the pending OD-30 taxonomy |
| **ODC-03a** | FDA-03 | Coincident-position data with *agreeing* values | refuse always; or allow if equal within stated uncertainty | **Refuse always** (matches the exact-position branch; agreement judgement is arbitration) |
| **ODC-04a** | FDA-04 | Sampler | seeded scrambled `scipy.stats.qmc.LatinHypercube` + correlation diagnostic; or keep the lattice with an input-count refusal | **QMC + diagnostic** |
| ODC-04b | FDA-04 | Relocate UQ computation out of `engcore.mcp` (O-4) | now (with FDA-04); later | **Now**, if the schema bump happens anyway |
| **ODC-14a** | FDA-14 | Small-n rule | refuse a tail below design resolution (for example n < 40 for 95 %); or report achieved mass only | **Both**: refuse below resolution, report achieved mass otherwise |
| ODC-14b | FDA-14 | Label | "empirical central interval estimate; design error unquantified" | Approve wording |
| **ODC-O1a** | O-1 | Significance procedure | (A) keep the bootstrap fraction, with a preregistered null-calibration study and more resamples; (B) exact paired sign-flip / randomisation test for p, bootstrap only for the CI | **(B)**: a validity argument that does not depend on asymptotics; Holm unchanged |
| ODC-O1b | O-1 | Calibration-study execution | authorize later as a separate, bounded, non-formal run | Defer until v0.3 is drafted |
| **ODC-BL1** | B-LEAK / FDA-19 | Extend `isolation_probe` to the Genesis-lite secret inventory (root file, derived seeds, run logs), and keep run logs out of proposer reach until all arms finish | approve as part of P-1 / P-3; or not | **Approve** (certified change → OD-3) |
| OD-20 (existing) | B-LEAK | Isolation deployment and lift | per readiness §2 (five conditions) | Unchanged; independent testing remains mandatory |

## D. Sequencing and execution approvals

| ID | Decision | Recommendation |
|---|---|---|
| **INT-1** (existing) | Merge PR #169 | First. It is the base for every certified repair. |
| ODC-SQ1 | Batch A composition (certified): FDA-01, FDA-02, FDA-03, escrow half of FDA-05, FDA-19 probe scope; optional FDA-07/08/09 | Approve as **one branch, one push**, so one OD-3 (a push cancels a running recertification) |
| ODC-SQ2 | Batch B (uncertified MCP): FDA-04, FDA-14 (+O-4) | Approve independently; it can land before Batch A |
| ODC-SQ3 | v0.3 Genesis-lite amendment content: FDA-05 evaluator half, FDA-06, O-1 route, FDA-18/21/22, P-1..P-5 | Draft after Batch A design is fixed. OD-19 only after the amendment exists (OD-B2). |
| **ODC-EX1** | Execution of failing-first tests at repair time (each is a reproduction against unrepaired code) | Approve per batch when the repair is approved. This converts FDA-01/02 to executed evidence without a separate R-01/R-02 run. |
| ODC-EX2 | R-01 / R-02 standalone reproductions | **Not now** (owner stop preserved). ODC-EX1 supersedes them. |
| OD-3 (existing) | Recertification HEAD | After #169 + Batch A land: Linux 3.11/3.12, venv outer interpreter |
| OD-18 / OD-19 / OD-8 (existing) | Compute budget, identity, external evaluator | After v0.3 exists and B-LEAK is lifted |

## E. What is explicitly NOT being asked

- No benchmark scoring change, freeze, re-scoring of v0.2 pilot results, or formal measurement.
- No change to certification manifests, ledgers, the active epic or historical bundles.
- No replacement of FORGE trust authority (replay, identity, certification, arbitration, escrow, scoring) by any external package.
