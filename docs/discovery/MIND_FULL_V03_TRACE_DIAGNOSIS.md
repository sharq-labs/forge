# mind_full: bounded development trace diagnosis

**COMPLETE FOR THE BOUNDED DIAGNOSTIC SCOPE. Behavior and thresholds unchanged.
Do not spend a formal attempt yet. One false-positive path reproduced; historical
confounded misses were not reproduced. The proposed change below is NOT IMPLEMENTED.**

## Scope and execution

Owner authorized fresh development cases with Mind step tracing, followed by a
report before any behavior change. HEAD:
`1cb5e187ef46ba2735fa292112a5e2bfd2334007`, plus the previously documented unchanged
Mind import from `20069cc2e9aadea6c5662a872626c1b8ef3dadd0` and uncommitted diagnostic
tools/tests. No candidate, scoring, priors, thresholds, certification or deployment
source was edited.

Final fixed plan SHA256:
`c99ed3462cd16eb47bd4502e54876263b5ace50fe111794fa16d1016bb3a6d54`.
Three new public-development campaign labels × four presentations × seed 17:
12 world sets, 72 primary cards. All six kinds retained; no replacement or tuning.
All 12 world-key digests are distinct and disjoint from the prior screen's 40.
Same synthetic generator family; this is not independent real-world validation.

Execution used the dedicated Linux checkout and Python 3.12.3. Every world set
ran unchanged mind_full through the v0.3 development harness in a fresh worker,
with private working/temp directories and trusted in-process execution across its
six cards. Existing trace export was enabled. SECURITY_BOUNDARY_NOT_PROVEN.
The observer reads step records; it does not expose ground truth to the candidate.

| Executed check | Result |
|---|---|
| Final diagnostic tests | 9 passed in 13.69s |
| Primary collection | 12 valid runs / 72 cards, all evaluator re-scores agree |
| Recorded-observation replay | 72/72 agree on step chain, conclusion and final stop/state |
| Trace-disabled control | First predeclared world set, six cards: semantic MATCH |
| Stop | All 72 primary cases exhausted their existing query budgets |
| Child receipts | 13/13 exit 0: 12 primary/replay workers plus control |
| Original driver | Exit 1 after collection, during prior-record path lookup |
| Offline finalization | Exit 0; all identities, disjointness and control checked from saved files |

The original end-to-end command did **not** pass. Its final lookup expected old
evidence inside the Linux repository, whereas it was stored beside the checkout.
The missing comparison was completed offline using that evidence; its hash also
matches the Windows copy. No world execution or replay was repeated to repair
this reporting failure.

Replay uses the recorded observations, not new independent evidence. A read-only
profile hook captures each refit's state during replay; matching step/conclusion
digests and final state constrain instrumentation effects. Multiplicity-ledger
metadata is outside the replay check. The existing trace records selected/top
candidates and a digest of the candidate set, not every candidate's full payload.
The single trace-disabled control is not a universal noninterference proof.

## Observations

| Kind | Outcomes across the fixed 12 cases |
|---|---|
| no_solution | 6 no_law; 5 insufficient_evidence; 1 confounded |
| confounded | 12 confounded |
| discoverable | 3 law; 9 insufficient_evidence |
| spurious_correlate | 3 law; 9 insufficient_evidence |
| indistinguishable | 12 insufficient_evidence |
| insufficient_evidence | 12 insufficient_evidence |

These are case counts, not formal rate/sensitivity estimates or a comparison
against baselines. Different presentations contain different worlds: no lexical
causation can be inferred.

## What explains the no_solution misses

Full per-case evidence is in `v3/results/target-diagnostics.json`; each `job-*`
also contains scored records, original traces and replay-derived diagnostics.

| Cases | Observed decision path | What it establishes |
|---|---|---|
| job-02, `bf-4a35362ba9c95365` | 12 observations; passive inclusion 0.933495675 exceeds existing 0.9; copied-covariate screen R² 0.281822480; no rival refuted; association branch returns confounded | Reproduced false classification on a no-solution world; a relative posterior within this fitted family sufficed without prospective corroboration distinguishing association from no association |
| job-01, `bf-b8af776bd6927869` | 12 observations; replicate sd 0.012353107, upper95 0.054543753, only 2 replicate degrees of freedom; eight rivals refuted; no qualifying surviving decisive test; pure-null remains fitted with weight 0.444519446 but is set aside | The existing survivorship safeguard causes the final abstention. Small replicate estimate and refutations coexist; a causal claim that the estimate caused erroneous refutations is not established |
| jobs 05 / 08 / 11 | No-settable-input mass 0.367412536 / 0.427064549 / 0.350840031, below 0.5; extrapolated region cannot be supported | Null decision not earned, then extrapolation refusal; not a reason to move/remove the extrapolation guard |
| job-10 | No-settable-input mass 0.258728195; region sd 0.4101 and disagreement 0.3953 exceed precision 0.02 | Budget exhausted with insufficient support and precision; no proven code defect in refusing |

Job-02's passive-only rival has weight 0.625740132, fitted R² 0.596600258 and
log-Bayes-factor versus pure-null 2.636864591. Its status remains PROPOSED.
There were zero sealed falsifiers; 29 attempted entries report predictions too
uncertain to seal. A prediction digest is not a successful admissible falsifier.
Low R² against settable inputs passes the current copy screen; it does not prove
statistical independence or identify a hidden cause.

Important: job-02's raw no-settable-input mass is
**0.670533969 = 0.625740132 passive-only + 0.044793837 pure-null**.
It is not a 67% posterior on pure noise. Reordering the null branch before the
association branch would misinterpret passive-only support as no dependence.
Raw trajectory weights precede conclusion filters and are not always the masses
used by the final decision; unavailable fitted support is recorded as None.

Four of the five abstentions had budget 12; job-05 had budget 60. This does not
prove that extra observations or a different allocation would resolve them.
In job-05 the null mass rose and later fell before the fixed budget ended:
choosing the earlier favorable stopping point after inspection is not a valid fix.

## What remains unknown about confounded

All 12 new confounded cases were recognized. The four misses in the earlier
screen had rationales citing fit mismatch twice and extrapolation twice, but
that screen retained no full traces. This experiment does not reproduce or
causally explain those old misses. No sensitivity-specific change is justified
by the present sample.

All 12 successful confounded cases also have zero qualifying decisive survivors.
Simply adding `faced_decisive_test()` as a gate would suppress every observed
correct confounded classification as well. That Boolean is not an established
discriminator, and no such patch is proposed.

## Smallest proposed change: association-specific confirmation

Limit the proposed change to the passive-association conclusion. Before returning
confounded, require prospective admissible predictive evidence distinguishing an
association-bearing model from an appropriate no-association comparator, using
observations reserved within the existing budget. If such support is unavailable,
return insufficient evidence. Preserve the current null, extrapolation and
precision guards.

This is a **design proposal**, not a ready approved one-line patch. Before any
implementation, specify the comparator, how predictions are fixed before
observations, evidence allocation, conditional versus marginal prediction,
uncertainty treatment and acceptance rule. Reuse existing provenance records
where their timing/content supports the comparison. Do not invent a new numerical
threshold from these results.

Conditional prediction using a newly observed passive covariate needs particular
care: the predictive function must be fixed before its target outcome is seen;
the present marginal predictions cannot simply be relabeled conditional evidence.
Re-scoring these inspected traces is exploratory, not independent confirmation.
Any eventual improvement claim requires a newly declared development comparison.

The objective is to reduce false association conclusions, not guarantee more
no_law answers or higher credit. Recall may fall. No benefit, calibration or
formal-readiness improvement has yet been measured for this proposal.

**Next owner decision:** whether to authorize designing that narrow confirmation
rule before a separate implementation review. No threshold choice or behavior
change is implied by approving this diagnosis. Evaluator selection remains with
the owner; no formal root, freeze, admission, OD-3 or CP3 was used.

## Evidence and limits

[Evidence directory](../work/evidence/mind_full_v03_diagnosis_2026_10_20_v1/README.md),
[finalization](../work/evidence/mind_full_v03_diagnosis_2026_10_20_v1/finalization.json),
[case diagnostics](../work/evidence/mind_full_v03_diagnosis_2026_10_20_v1/v3/results/target-diagnostics.json).
Exact commands, earlier failed unit test and subsequent results are recorded in
PROGRESS and the versioned receipts. Independent read-only scientific review:
PASS for corrected tooling and for interpretation/proposed scope; neither is
certification or a scientific validation result. Full regression and actual
changed-file pytest gate NOT RUN; gate selection only was inspected.
