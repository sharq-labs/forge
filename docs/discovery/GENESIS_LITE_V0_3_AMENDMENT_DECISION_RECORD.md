---
ai_schema_version: 1
doc_id: FORGE-GENESIS-LITE-V0-3-AMENDMENT-DECISIONS
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: 8ec97064c35144405e3eba53a4282e90f8593b1c
evidence_level: EXECUTED_BOUNDED
last_reviewed: 2026-10-19
supersedes: none
---

# Genesis-lite v0.3 amendment: what the owner must decide

> **Nothing here is approved.** This record lists the decisions that would let Genesis A1 (Genesis-lite Step-1)
> close through a v0.3 identity. It covers the Genesis-lite half of the deep-audit 2026-10-19 closures.
>
> The code is a DRAFT: not frozen, not FREEZE_READY, not the active identity, and not pushed. v0.2 stays the active
> identity.
>
> An approval of one item below implies no other. An approval to freeze is not an approval to run a pilot, a formal
> tier, a recertification or a merge; each needs its own approval.

Base: `origin/main` `8ec97064` (PR #172 merged). Branch `feat/genesis-lite-v03-amendment-draft`, local only.

Blocker sources:
- [blocker matrix](../work/evidence/deep_audit_2026_10_19/closure/GENESIS_BLINDFOLD_BLOCKER_MATRIX.md)
- [owner decisions](../work/evidence/deep_audit_2026_10_19/closure/SCIENTIFIC_FINDINGS_OWNER_DECISIONS.md)
- [closure plan](../work/evidence/deep_audit_2026_10_19/closure/SCIENTIFIC_FINDINGS_CLOSURE_PLAN.md), §3.1, §3.2 and §3.8

Commands and results: `docs/work/PROGRESS.md`, entry "2026-10-19 — Genesis-lite v0.3 amendment package (DRAFT)".

## 1. Status, one axis at a time

| Item | Implementation | Execution | Scientific validation | Certification | Owner |
|---|---|---|---|---|---|
| FDA-05 evaluator half (`v0_3/evaluator.py`) | IMPLEMENTED (draft) | targeted tests PASS | NOT_VALIDATED | prereg-pinned only | PENDING (ODC-05a/b/c/d) |
| FDA-05 escrow half (`engcore.blindfold.escrow._assess_pair`) | NOT_STARTED; specified in §5 | NOT_RUN | NOT_VALIDATED | certified → OD-3 | PENDING (ODC-SQ1, OD-3) |
| FDA-06 cap (`v0_3/analysis.py`) | IMPLEMENTED (draft); extended to `indistinguishable` after review | targeted tests PASS | NOT_VALIDATED | not certified | PENDING (ODC-06a/b) |
| O-1 route B (`v0_3/analysis.py`) | IMPLEMENTED (draft) | targeted tests PASS | NOT_VALIDATED; no calibration study run | not certified | PENDING (ODC-O1a/b) |
| P-4 formal driver (`v0_3/formal.py`) | PARTIAL: orchestration, root rules, ordering, committed-identity check and log; harness binding and one-attempt registry NOT_STARTED | targeted tests PASS with a stub runner; never ran a world | n/a | not certified | PENDING (OD-19, OD-20) |
| P-5 environment manifest (`v0_3/environment.py`) | IMPLEMENTED; import-time modules only | built on this Windows 3.14.2 machine only | n/a | not certified | PENDING (OD-18) |
| FDA-19 probe scope | NOT_STARTED; specified in §5 | NOT_RUN | — | certified → OD-3 | PENDING (ODC-BL1) |
| `preregistration/genesis_lite_v0_3.json` | DRAFT, rebuilt from code (digest in its `.sha256`) | rebuild test PASS | — | — | PENDING (OD-19) |

What did not change:
- v0 (`f99fcfbd…`), v0.1 (`94efff08…`) and v0.2 (`878e6812…`) and their pilot results are byte for byte unchanged. A test checks this.
- `pilot.prereg_matches_code()` still returns v0.2.
- No v0.2-pinned file and no certified file was edited.

The new test file falls under the `assurance_suites` recertification trigger (`tests/**`), as every test change
does.

## 2. The package

| File | What it proposes |
|---|---|
| `benchmarks/genesis_lite/v0_3/evaluator.py` | **Pair rule (d').** The BRACKET route also requires `max(\|A\|,\|B\|)/min(\|A\|,\|B\|) <= 1 + w` at every outside-box evaluation point. A non-finite value, a zero or a sign change fails closed. The pass route is unchanged. **`w` has no default:** `PAIR_BOUND = "OWNER_DECISION_REQUIRED"`, scoring refuses without an explicit `PairBound`, and `evaluate_campaign` refuses any bound other than the preregistered one. Standard library only. The credit table is unchanged; the schema moves to `/3`. |
| `benchmarks/genesis_lite/v0_3/analysis.py` | **FDA-06.** The cap covers every kind whose positive credit can come from a law or a law pair: discoverable, spurious_correlate, confounded and indistinguishable. It applies per universe, and a VALID record missing the flag is refused. **O-1.** A one-sided paired sign-flip p: exact integer enumeration when cheap, else Monte-Carlo `(b+1)/(M+1)` with M = 19,999 from a fixed SHAKE-256 stream. The bootstrap gives the lower bound only; Holm is unchanged. **D-09.** Records must carry `tier = formal` and the preregistered root commitment. While v0.3 is a DRAFT, `lift_decision` claims nothing. |
| `benchmarks/genesis_lite/v0_3/formal.py` | **P-4.** The driver accepts only the committed v0.3 bytes that the code rebuilds. It refuses: a non-FROZEN document; any `OWNER_DECISION_REQUIRED`; a root that does not match the commitment; a retired root (every pilot or formal commitment of another committed preregistration, including the v0.2 pilot root, which its summary revealed); a changed environment. It runs world-set-major (OBS-04) with tier-tagged masters, and reads the root from stdin, never argv. A record from another identity is marked INVALID, never relabelled. The log is hash-chained and refuses an existing file. |
| `benchmarks/genesis_lite/v0_3/environment.py` | **P-5.** Run in a fresh `-I` interpreter, it records the interpreter and every third-party distribution behind the modules a formal run imports. Unclaimed modules are listed, never dropped. It provides a digest and a difference report. |
| `benchmarks/genesis_lite/v0_3/preregistration.py`, `preregistration/genesis_lite_v0_3.json` | The DRAFT identity, built from code. It amends v0.2 by digest and pins the reused v0.2 files (the build refuses if one changed). It lists every open decision. |
| `tests/genesis_lite/test_genesis_lite_v0_3_amendment.py` | 66 tests. Each defect is pinned twice: on frozen v0.2, where the defect stays, and on v0.3, where it must be gone. |

## 3. Evidence (executed in this session, Windows `.venv` CPython 3.14.2, numpy 2.5.2)

### Failing-first

The stage-1 stubs exposed the v0.3 API but kept the unrepaired v0.2 behaviour. On the FDA-05/06/O-1 subset of the
first test version: **35 failed, 12 passed.** The failures were the defects themselves:

- **FDA-05:** the vacuous pair scored `('indistinguishable_hit', 1.0)` for both mutually exclusive truths. An escrow
  that still credits it produced `VALID`, not `EVALUATOR_DISAGREEMENT`.
- **FDA-06:** `KeyError` and "did not raise" on spurious_correlate and confounded. No per-kind flag was read.
- **O-1:** under the sign-symmetric null, the v0.2 bootstrap fraction (2,000 resamples, `Random(0)`) rejects more often than alpha.

The O-1 rates come from enumerating every sign pattern of a fixed magnitude vector (the p-function is v0.2's bootstrap):

| Magnitudes | v0.2, α = 0.01 | v0.2, α = 0.05 | v0.3, α = 0.01 | v0.3, α = 0.05 |
|---|---|---|---|---|
| Six differences | 1/32 | 5/64 | 0 | 1/32 |
| Eight, skewed, with zeros | 1/32 | 7/64 | 0 | 1/64 |

This shows the fraction is not a p-value at small n. It says nothing about the formal sizes (600 / 2,400 world sets),
where the audit expects approximate calibration (UNVERIFIED).

### After the repair and the review fixes

- 66/66 v0.3 tests pass.
- `tests/genesis_lite`: 160 passed.
- Sign-flip timing: 0.04 s for 600 world-set differences, 0.11 s for 2,400 (Monte-Carlo path).
- FAST tier: see PROGRESS. The comparison was made against pristine `origin/main` on the pre-review code; the review
  fixes touch only `v0_3/**` and its test file.

### Not executed

- any generator, pilot or formal-grid world, or any real arm under v0.3;
- the escrow half and the isolation probe;
- a null-calibration study;
- Linux, 3.11 or 3.12;
- the SCIENTIFIC tier.

## 4. Independent review (2026-10-19, static, read-only reviewer agent; no code executed)

The reviewer found no BLOCKER. It confirmed three things:
- the pair-rule equivalence;
- the sign-flip DP and the Monte-Carlo bit handling;
- the cap mechanics.

Dispositions of its findings:

| # | Finding | Disposition |
|---|---|---|
| 1 MAJOR | The FDA-06 cap missed `indistinguishable`. FDA-05 removes a monomial baseline's bracket route on rival truths (outside the family), while a richer grammar keeps the pass route. | **Fixed.** Capped kinds are now derived from a positive `law_pass` **or** `indistinguishable_hit`. Tests added. |
| 2 MAJOR | The pass route credits a passing law with an arbitrary in-box-agreeing partner: +1.0, where the law alone earns 0.0. | **Not changed. It is a scientific design question: new ODC-05d.** It is a v0.2 property, and the draft neither adds nor removes it. |
| 3 MAJOR | `w` was taken from the caller. With `w = 1e31` the vacuous pair is credited again. | **Fixed.** `evaluate_campaign` requires `expected_pair_bound` from the preregistration and refuses anything else. Tested. |
| 4 MAJOR | The driver accepted any dict labelled FROZEN. | **Fixed.** `committed_identity_problems` requires the committed bytes, a matching digest file and a code rebuild. Tested. |
| 5 MAJOR | D-09 binding and "one attempt" were label checks: a second `--out` with the same root was possible, and the log chain had no external anchor. | **Partly addressed.** The overstatement is corrected in code docs and here. A used-root registry, a published head hash and a post-reveal master/key recomputation are **not drafted**; they are a freeze prerequisite (§6). |
| 6 MAJOR | PROGRESS had no entry for the cited evidence. | **Fixed.** PROGRESS entry written with commands and results. |
| 7 MINOR | O-1 figures were inconsistent between the record and the tests. | **Fixed.** Recomputed exactly (§3). An earlier draft of this record had swapped 5/64 and 7/64. |
| 8 MINOR | The retired-root list was narrow. | **Widened** to every pilot or formal commitment of another committed preregistration. A root revealed anywhere else remains the operator's responsibility (fresh root at freeze). |
| 9 MINOR | "Honest pair untouched (tested)" overstated the test. | **Reworded.** It is an argument from the rule plus a synthetic honest pair; it was not tested on `universe._rival` worlds. |
| 10 NOTE | Monte-Carlo validity with one fixed public stream | **Stated.** The guarantee holds over random streams; for the fixed stream the size is approximately α. The exact path is exact. |
| 11 NOTE | The freeze path failed on a status note containing the ODR literal, and on serialising a `PairBound`. | **Fixed.** Both are handled. |
| 12 NOTE | The manifest records import-time modules only, and the driver trusts a caller-passed manifest. | **Recorded.** `main` measures the manifest itself. Lazily imported modules are a known gap (§6). |

## 5. Decisions the owner must take

Each row states what the draft assumes. *Recommended* repeats the audit's recommendation; it is not an approval.

### ODC-05a — form and scope of the informativeness bound

- **Question.** Which form: (i) a ratio cap; (ii) graded credit by log-width; (iii) no bracket credit. **And which
  scope:** the bracket route only, or every hit.
- **Drafted as.** (i), bracket route only.
- **Notes.** Scope is a new sub-question.
  - The generator's honest rival is `law·(1 + 0.5σ (g/g_max)^m)`, with m in [3, 4.5]. The region is pushed until 90 %
    of points differ by more than 3·tol. Its ratio is therefore unbounded by design, so a cap on every hit would score
    correct (law, rival) pairs as misses.
  - Sign changes and zeros fail closed.

### ODC-05b — the value and form of `w`

- **Question.** The value of `w`, and whether it is absolute or a multiple of `tol`.
- **Drafted as.** No value: `OWNER_DECISION_REQUIRED`. Once decided, the value is bound into the evaluator (and, per
  §6, into the escrow config).
- **Notes.**
  - `w ≤ tol` is option (iii).
  - **Threshold gaming.** An uninformed pair with spread just under 1 + w hits whenever the in-box fit extrapolates
    to within about w of the truth. Measuring that rate on generator, pilot or formal worlds would be tuning, which is
    forbidden. A synthetic study needs its own approval.

### ODC-05c — retroactivity

- **Question.** Apply the rule to v0.3 only, never retroactively?
- **Drafted as.** v0.3 only.
- **Notes.** The v0.2 tests still pin the v0.2 behaviour.

### ODC-05d (new) — the pass route

- **Question.** Keep v0.2's +1.0 for a passing law with an arbitrary partner? Or constrain the partner (for example
  require it to pass on the in-box data within σ and be admissible by the same family)? Or score a pass-route pair at
  the `law_pass` credit?
- **Drafted as.** Kept, as in v0.2.
- **Notes.** Review finding 2. In an INDISTINGUISHABLE world, (L, J) with any diverging J weakly dominates L alone.
  This is exploitable with the kind tell (FDA-22, `region_tell`), and interacts with FDA-18.

### ODC-06a — which contract governs the cap

- **Question.** Genesis §10.5 rule 4, or the v0.2 "discoverable only" wording?
- **Drafted as.** §10.5 (*recommended*).

### ODC-06b — which kinds are capped

- **Question.** Which kinds the cap covers.
- **Drafted as.** discoverable + spurious_correlate + confounded (*recommended*), **plus indistinguishable** (review
  finding 1), all derived from the frozen table.
- **Notes.** The cap uses the arms' actual searched family (`in_monomial_family`), not library reach (BVB handoff §4).

### ODC-O1a — significance procedure

- **Question.** Which significance procedure.
- **Drafted as.** Route B (*recommended*): an exact or Monte-Carlo sign-flip p, the bootstrap for the bound only,
  Holm unchanged.
- **Notes.** **Live-document tension, OWNER_DECISION_REQUIRED.**
  - `BVB_RESUME_HANDOFF_2026_10_19.md` §3 row 2 says "not automatic sign-flip". §4 lists what O-1 depends on: the final
    scoring, the strongest baseline, multiplicity, a proper null, non-inferiority and repeated submissions.
  - **Null scope.** The test is valid for exchangeability within a world set; capping makes it conservative. It does
    not cover a composite null "mean ≤ 0" with an asymmetric difference distribution.
  - The Monte-Carlo path's size is approximately α for the one fixed stream.
  - Repeated submissions are **not** limited by anything drafted here (review finding 5).
  - Choices: B as drafted, B with changes, A, or defer O-1 until the scoring is frozen.

### ODC-O1b — null-calibration study

- **Question.** Authorise a bounded, non-formal null-calibration study?
- **Drafted as.** Not run.
- **Notes.** Relevant to the composite-null concern, the fixed stream, or route A.

### OD-19 (v0.3) — approve and freeze

- **Question.** Approve and freeze the v0.3 identity.
- **Drafted as.** DRAFT.
- **Notes.**
  - Freezing needs every row here decided, the decisions written into `PAIR_BOUND`, `FORMAL_ROOT_COMMITMENT`,
    `ENVIRONMENT_MANIFEST_SHA256` and `STATUS`, a regenerated digest, and §6 done.
  - `build()` refuses FROZEN while any `OWNER_DECISION_REQUIRED` remains.

### OD-20 — escrow deployment

- **Question.** Choose the escrow deployment, with an independent rerun of the isolation probe.
- **Drafted as.** Not in scope.
- **Notes.** The driver cannot verify the deployment. With FDA-19, the probe must cover the Genesis-lite root file,
  derived masters, run logs and answer keys.

### OD-8 — external evaluator

- **Question.** Name the external evaluator, or a selection process and deadline.
- **Drafted as.** Open.
- **Notes.** Needed before Graduation, and before the A1 freeze names its held-out protocol.

### OD-18 — compute budget and formal machine

- **Question.** The formal compute budget, **and the formal machine and interpreter**.
- **Drafted as.** Open.
- **Notes.** The chosen machine fixes the manifest digest. Mind, LLM and harness overheads are UNMEASURED.

### OD-3 — recertification after Batch A

- **Question.** Recertify after Batch A: the escrow half of FDA-05 and the FDA-19 probe scope (with FDA-01/02/03 per
  ODC-SQ1).
- **Drafted as.** Open.
- **Notes.**
  - Until the escrow half lands, a v0.3 run on a gamed pair is `EVALUATOR_DISAGREEMENT` (tested), and no v0.3 harness
    can be bound.
  - Landing this package also triggers recertification through `assurance_suites`.

## 6. Specified only, or still to design before a freeze

**Escrow half of FDA-05** (certified, OD-3). In `escrow._assess_pair`:
- apply exactly (d') with the same `PairBound`;
- bind `w` into the escrow's `EvaluatorConfig` digest;
- bump the assessment version.

Tests:
- the R-05 pair is an escrow miss for both truths;
- the informative pair still hits;
- the in-box-disagreeing pair still misses;
- the agreement test covers the bounded bracket route;
- a "vacuous pair" attack arm is refused.

**FDA-19 / ODC-BL1** (certified, OD-3). `isolation_probe.scan_for_leaks` matches by content the root hex, every derived
master, `runs.jsonl` and the answer-key digests, with one planted-artefact test per item.

**One-attempt enforcement** (review finding 5). Needs:
- an operator-side used-root registry, written before the first world set;
- a head hash of the run log, published outside the operator's control;
- a post-reveal recomputation of every master and key digest by the evaluator.

**Also open:**
- FDA-18 (campaign answer exclusivity);
- FDA-21 (baseline σ ignores fitted degrees of freedom);
- FDA-22 (per-kind form-prior tell);
- P-1 to P-3 (isolation wiring, its harness, attack arms per measured attack);
- the v0.3 harness binding (`formal.unbound_runner` refuses, citing OD-3);
- lazily imported modules in the manifest.

## 7. What this package does not do or authorise

- No push, PR or merge.
- No change to v0/v0.1/v0.2, the certified files, the active epic, certification manifests or historical bundles.
- No re-scoring of v0.2 records.
- No pilot or formal run.
- No root generated or retired.
- No benchmark freeze.
- No claim that a Mind lift exists or does not exist.
