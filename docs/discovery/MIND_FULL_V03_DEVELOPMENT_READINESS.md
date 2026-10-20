# mind_full v0.3 — bounded development readiness result

**NON-FORMAL / SECURITY_BOUNDARY_NOT_PROVEN. Recommendation: do not spend the
formal attempt on this candidate yet. Targeted diagnosis/improvement is warranted;
no frozen/formal claim is established.**

## Scope and fixed protocol

Owner approved mind_full as a development starting point; evaluator selection
remains the owner's choice. This does not appoint D6, select/freeze the formal
D4 candidate, authorize OD-3 or admit a formal root. No deployment/CP3 changes.
Existing worktree HEAD1cb5e187ef46ba2735fa292112a5e2bfd2334007 plus explicit
uncommitted additions.12 candidate files imported byte-identically from
feat/br-mind-01-minimal-mind at20069cc2e9aadea6c5662a872626c1b8ef3dadd0.
No Mind behavior, scientific thresholds, baseline registry file or v0.3 scoring
was changed. A development-only in-memory adapter registers the actual pinned
Mind callable in each fresh worker AFTER development binding.

Final plan SHA256:
`5d40f4c8e51696fedc4078efac91beb63685afb2597b93b5d97d427072294bbc`.
Written before final tests/fixed-grid execution; hash is local content identity,
not independent witnessing or formal preregistration. Prior plans are preserved;
no fixed-grid world was run under them. The seed/grid never changed.

5 new public-development campaigns ×4 presentations ×2 seeds=40 world sets.
20 registered baseline arms (19 non-adversarial, one adversarial) plus mind_full:
840 six-card runs /5040 primary card executions, followed by4 predetermined Mind
semantic replays /24 cards. Masters derive from public development seed plus
campaign/presentation/seed, excluding arm; pairing/different-world checks passed.
All four presentations were included, unlike the two-presentation public demo.

Fresh process/private temp per six-card run; trusted in_process behavior retains
module state across six cards, unlike formal per-card processes. No security
claim.4 workers,60s/run,1200s workers/replay budget,1500s outer cap; no retries or
tuning. Existing v0.3 cap, sign-flip, Holm and noninferiority calculations retained.
Formal refusals remain in the machine-readable analysis; lift_claimed=False.

## Executed results

| Check | Observed |
|---|---|
| Adapter/reporting tests |16 passed in12.25s |
| Primary runs |840 valid,0 invalid,0 screened,0 missing |
| Automated evaluator re-score |Agrees on5040/5040 primary cards; no external evaluator appointed |
| World identity |40 distinct world-set key digests, same key across21 arms per set |
| Semantic replay |4/4 MATCH; not cryptographic verification of archived logs |
| Dependencies |Unchanged before/after; candidate/adapter hashes match source |
| Runtime |197.00s outer elapsed, exit0;196.37s measured run/analysis |
| Formal lift |False; developmental grid, draft identity and security/approval gates remain |

## Performance assessment

| Metric | Result |
|---|---:|
| Mind raw mean six-kind credit |3.675 |
| Strongest non-adversarial baseline, careful |3.250 |
| Raw paired difference |+0.425 |
| v0.3 capped pooled difference |−0.025 |
| Capped bootstrap95% lower bound |−0.200 |
| Uncapped sign-flip p, descriptive |0.015625 |
| Pooled Holm condition |Not met |

Do not interpret the raw rank as discovery lift. Control-solved and
representation/out-of-family caps remove gains the registered scientific
contract does not permit as evidence of improvement. The uncapped p concerns a
different statistic from the capped effect and is not corrected evidence of
success: the Holm family condition fails, and the capped effect is nonpositive.
All confidence bounds/p-values here are exploratory on40 development world sets.

| Kind | Mind outcomes /40 | Existing guardrail |
|---|---|---|
| no_solution |27 no_law;10 insufficient;3 confounded |Fails vs always_refuse: mean−0.325, lower−0.475, margin0.15 |
| confounded |36 confounded;4 insufficient |Fails vs single_setting: mean−0.100, lower−0.200, margin0.15 |
| discoverable |11 law_pass;28 insufficient;1 confounded |Passes this exploratory guardrail vs extrapolating_fit |
| spurious_correlate |13 law_pass;27 insufficient |Passes this exploratory guardrail |
| indistinguishable |40 insufficient |Passes guardrail; no distinguishable-pair capability demonstrated |
| insufficient_evidence |40 insufficient |Passes guardrail |

Mind has24 law_pass,0 law_fail and0 negative-credit outcomes in240 primary cards.
That is measured conservatism in this sample, not a general false-law guarantee;
four false confounded classifications still occur (3 no_solution,1 discoverable).
The trap-presentation guardrail also fails: lower−0.700 vs required greater than
−0.600. Different presentations have different worlds in this plan; this does
NOT identify wording sensitivity or textbook leakage as the cause. No_solution
recognition was4/10 in trap-labelled worlds versus9/10 paraphrased-labelled worlds;
these are separate draws, not a controlled vocabulary intervention.

## Smallest justified next improvement target (not implemented)

Prioritize **null-versus-effect and passive-association decisions**, not a larger
Mind or relaxed benchmark rules. The concrete target is13 missed no_solution
classifications, including3 spurious confounded conclusions; the4 missed
confounded classifications are secondary. Preserve successful refusal behavior.

Recorded rationale for no_solution misses:7 extrapolation refusals,3 precision
refusals,3 passive-association conclusions. Static inspection shows the null
posterior decision already precedes the extrapolation gate; therefore simply
reordering that gate is not supported. The next bounded task should inspect why
the null hypothesis fails to accumulate sufficient standing, whether evidence
allocation and the association decision remain calibrated under pure noise, and
how to distinguish passive association from absence of a controllable effect.

These are diagnostic hypotheses, not proven root causes or promised fixes.
Full per-step Mind traces were not captured in this screen; retained sealed
proposals/rationales cannot establish which experiment-selection or posterior
update caused a miss. Before changing behavior, reproduce the decision-path issue
on new development fixtures with traces, then test a narrowly specified change
on a new predeclared development set, preserving the false-law/refusal checks.
Do not lower thresholds, suppress UNKNOWN/refusals, permit unsupported
extrapolation, add benchmark-kind tells, or rescore/tune against these40 worlds.
No ablations were run: adaptive selection, belief update and falsifier contribution
cannot be attributed by this result.

A larger sample of the unchanged candidate could reduce uncertainty, but there
is no current basis to promise that it will reverse the capped−0.025 mean or
repair the no_solution deficit. Close the targeted issue before spending the
formal attempt; external evaluator/isolation/certification remain separate gates.

## Cost and practical stop

Mind harness wall time summed over40 runs:84.059s (~2.10s per six-card run).
careful:2.754s (~0.069s/run). These concurrent development timings exclude worker
startup/identity validation and are NOT a formal deployment budget prediction.
No formal baselines, official root, admission/registry storage, freeze, OD-3,
commit/push/merge or evaluator selection occurred. No candidate tuning occurred.

Existing4608 production file hashes and CP2 source/evidence hashes remain intact;
only new candidate source, development driver/tests and docs were added. Candidate
source is an uncommitted import, not a claim of integration/certification. Full
regression, changed-file gate and formal deployment timing NOT RUN in this bounded
screen. Original main and divergent Linux checkout were preserved.

## Evidence

[Plan, tests, raw records, replay and commands](../work/evidence/mind_full_v03_readiness_2026_10_20_v1/).
[Machine-readable summary](../work/evidence/mind_full_v03_readiness_2026_10_20_v1/v3/results/summary.json).
[Raw per-run/card records](../work/evidence/mind_full_v03_readiness_2026_10_20_v1/v3/results/runs.jsonl).
Pre-run independent static review PASS. Final independent read-only interpretation review: PASS; raw-record checks corroborated counts, pairing and numerical conclusions. This is review evidence, not certification or formal validation. See [review](../work/evidence/mind_full_v03_readiness_2026_10_20_v1/final-review.md).
