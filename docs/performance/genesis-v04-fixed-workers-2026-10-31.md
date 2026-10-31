# Genesis-lite v0.4: fixed-worker follow-up, 2026-10-31

Status: local development optimization and ordinary gates complete; the ordinary
gates remain NOT GREEN because of two reproduced baseline certificate failures.
No scientific validation, certification, formal run, OD-3, push or merge is claimed.

## Result

On the same six-campaign public workload, **four workers before and after**, three
alternating-order paired batches took **55.362 +/- 0.714 s** before and
**25.864 +/- 0.721 s** after (mean +/- sample SD). This is **2.141x throughput** or
**53.28% less batch time**, relative to the already optimized native function image.
All 36 records across both sides are VALID. Each pair matches complete scientific
outputs, proposal/query-response digests and refusal/failure classifications,
with each source revision and immutable runtime independently bound.

| Fixed four-worker measure | Before | After |
|---|---:|---:|
| Batch 1, baseline then candidate | 56.124 s | 25.413 s |
| Batch 2, candidate then baseline | 54.710 s | 26.695 s |
| Batch 3, baseline then candidate | 55.253 s | 25.484 s |
| Mean PySR symbolic campaign service time (9 records/side) | 26.115 s | 10.943 s |
| Mean PySR units campaign service time (9 records/side) | 32.724 s | 13.596 s |

Campaign service times include concurrent contention; they are not serial CPU
times. Batch clocks include manifest preflight and use the existing hard-deadline
executor. Work is always two arms x three public seed/world sets, six worlds per
campaign, with unchanged settings/budgets and one Julia/GC/BLAS thread per proposer.
Repetitions measure timing variability on the same three fixture sets; they are not
18 independent scientific world sets. No scaling benefit is included.

Mean recorded child-process CPU time (`RUSAGE_CHILDREN`, excluding the trusted
parent) fell from **198.911 to 87.567 CPU-seconds** per six-campaign batch. Maximum
observed sampled aggregate PSS across the three runs was **2.216 -> 2.046 GiB**.
Memory samples are lower bounds, with short-lived process races recorded; they are
not guaranteed maxima. Runtime worker/thread settings were identical. These CPU
observations support reduced work rather than increased concurrency.

A separate one-pair coverage control ran every registered arm (19 campaigns per
side), also at four workers: **70.661 -> 44.014 s**, with all 38 records VALID and
19/19 exact cross-revision matches. This broader timing is a single sample, not
the repeated PySR estimate above. Across both campaign controls, all **74 campaigns**
were VALID, with **444 distinct recorded proposer processes within the same recorded
WSL boot** and none still live
at the final process-identity check.

The previous report's 1,124.512 -> 52.474 s result used the earlier pool control.
It remains historical evidence; multiplying its speedup by this bounded-executor
ratio would not be a new measured end-to-end result. No full-grid runtime was measured.

The planned grid in `preregistration_v4.FORMAL_GRID` has 19 arms x 30 campaigns x
four presentations (`anonymous`, `renamed`, `paraphrased`, `trap`) x 20 seeds =
45,600 campaigns (273,600 world-proposals). The user's total-time question can be
given a simple conditional extrapolation: `44.014 / 19 x 45600 / 3600 = 29.343 h`
at four workers. **This is a weak single-fixture extrapolation, not a qualified
full-grid estimate or an uncertainty interval.** Only anonymous presentation and
one public seed were measured in the 19-arm control; seed mix, tail amortization,
other presentations, long-run host load and formal-world costs are unresolved.
The repeated PySR-only rate projects 1,000 PySR campaigns to about 71.84 minutes;
that number must never be substituted for the complete 19-arm grid. No extra
formal run or protocol change was performed to answer this planning question.

## Implementation and identities

Baseline: `368d085ec0b2ffdeb631fea6df7d44d67a8d0da8`.
Measured candidate: `847283119c7207d4e63483c1e81c719672bb3f8b`.
Import change: `6fa867f3e24b462fbef13e9ff2dc615e85c759d0`.

`src/engcore/mind/grammar/evidence.py` imports the multiplicity ledger when
selection runs. Importing dimensions or PySR arms no longer initializes the whole
claims/evaluation stack. Selection arithmetic, ledger construction/calls and
exceptions are unchanged. The AST-based source identity follows function-local
imports; its closure is unchanged and still binds the claims code.

Three alternating fresh-process import pairs measured `arms_v4` import mean
0.790771 -> 0.215154 s (3.68x); whole process mean 0.846526 -> 0.248128 s.
These microbenchmarks isolate startup and are not campaign gains by themselves.

`tools/genesis_performance/precompile_pysr.py` traces full-budget PySR calls on
analytic arrays, without importing Forge. The builder receives 313 compilation
statements and the existing native image, never the fitted process/population.
The incremental build took 119.298 s using the existing PackageCompiler installation,
an offline separate project/depot and unchanged experiment Project/Manifest files.

| Asset | SHA256 |
|---|---|
| Parent `functions-reviewed.so` | `dddf152e429348eb8bcc519d377e7fc8151f3f10a9a5b0b0b0458d7e77090698` |
| Child `bridge-candidate-1.so` | `4870c813abc90d06c8bb335a55f89cd311718ab1cd675cfa4fcc7ecfb3fc021e` |
| Child build manifest | `3f5f917f4dab68f39fbb88d7fe9b613473e9ac16d431feb317d64ab9378f9d81` |
| Baseline runtime identity | `1e38bad1c39018ef0da3bce02eae66f33002613d2180031046edb291913723f3` |
| Candidate runtime identity | `82bfb4361c6127ad71c0543662d45c759608a6a33f9cdfa2b76e07213d18bafd` |

Images are root-owned read-only native-CPU artifacts under
`/opt/forge-sysimage-20261031`. The child is 496,859,568 bytes. Each proposer retains
a fresh process, private writable depot/tmp and all outside isolation checks.
Runtime hashing and security verification are unchanged; no mutable cache is shared.
The sealer verifies the exact parent binary plus package/runtime/Julia/CPU/thread
metadata before writing the child manifest, retaining the parent-manifest digest.
That check resolved the scientific review's initial MEDIUM finding.

## Comparison integrity

The repository's strict same-source analyzer is unchanged. It correctly reports
FAIL on the changed `development_identity`; that original result is retained in
each comparison report. It is not relabelled PASS.

An external cross-revision comparator independently recomputes v3/v4 source
identities and complete runtime identities, requires clean exact expected Git
heads, unchanged source closure and the single expected source-file delta, then
binds every run to its own source and manifest runtime. It requires identical
workload, workers, settings and explicit exposure/hidden-path sets; all six outside
checks must pass and all six `(pid, start_ticks)` identities must differ per campaign.
Only the already verified source-identity field is excluded from scientific-field
equality. All existing semantic and complete trace checks remain in force.

The comparator's in-memory positive control passed and **15 negative controls**
rejected altered v3/v4/runtime identities, a missing identity, duplicate/missing
tasks, changed credit/query/proposal, failed isolation, reused process and extra
source changes. Independent scientific review of the supplied logic passed
statically; it did not execute the tests or confer validation.

## Acceptance tests and gates

- Initial targeted grammar/arm pack: **78 passed / 1 skipped**, 17.07 s.
- Corrected import guard: old source **1 failed / 1 passed**, candidate **2 passed**.
  The initial failure-injection test incorrectly patched a bound import alias;
  it was corrected to patch the actual ledger constructor and both sides rerun.
- Parent-image compatibility and unchanged runtime verifier: **20 passed**, 2.10 s.
- Initial isolated analytic fits: complete Pareto equations/losses **2/2 exact**;
  same one-worker batch 20.580 -> 9.503 s. Expanded coverage: **6/6 exact** across
  both arms and seeds 0, 1, 2; same one-worker batch 51.631 -> 25.658 s.
- Final root/Linux v0.4 plus grammar pack: **204 passed / 3 expected skips**, 44.00 s.
  The skips cover an absent-PySR path with PySR installed, a non-`/opt` checkout
  path with this clone under `/opt`, and an unsupported-host path on a supported host.
- Adversarial deadline check: **PASS**; killing the campaign left no live namespace
  init, busy proposer or detached child, with passing outside verification.
- Serial dependency guard: **1 passed**. Focused certificate baseline and candidate:
  **27 passed / 2 failed** on each; identical existing certificate failure names.
- Ordinary FAST: **13,785 passed / 2 failed / 184 skipped**, 348.83 s. The only
  failed nodes are the same two certificate failures reproduced on baseline.
- Ordinary SCIENTIFIC: **14,369 passed / 2 failed / 185 skipped**, 535.97 s.
  The only failed nodes are the same two certificate failures. Both ordinary
  tiers remain **NOT GREEN**:
  `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` and
  `tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully`.

Ordinary tiers use separate clean native LF clones as unprivileged `dev_kaeem`,
the existing Python 3.12.3 and `-n 4 --dist loadfile`, with CI's documented deselects.
The historical battery-source object `e2b8037c881847a497c32f7ca56f82b95b493727`
is present before these tiers. The two pre-existing certificate failures were
reproduced in the focused baseline module without changing certificates or
weakening gates. Full baseline tiers were not rerun; the final ordinary tiers
bind candidate `84728311`. The later launcher/docs change has syntax/help checks
for the wrapper; it changes no scientific source or test implementation.
Both final tier skip-ID sets match the prior `129388b3` tier records exactly;
this is a comparison to retained earlier evidence, not a new baseline tier run.

## Reproduction and limits

Raw immutable-input manifests, run JSONL, digests, commands and logs live in
`/root/forge-perf2-evidence-20261031`; ordinary gate evidence is under
`/home/dev_kaeem/forge-perf2-gate-evidence-20261031`. The task workspace retains the
drivers and comparison code alongside the earlier diagnosis. The original checkout
remained untouched throughout measurement. Final local delivery uses a separate
native checkout at `/opt/forge-perf2-final-20261031`; the measured native clones
are retained for replay. Any original-branch update must be a clean, checked local
fast-forward preserving all previous commits.

Use the measured candidate checkout, existing explicit pinned runtime, and
`sysimage-bridge-candidate-1` in the public control launcher. Every paired comparison
must retain the same worker count. The final launcher resolves its own checkout
instead of silently selecting the old hardcoded native clone; benchmark runs above
called the module directly in their recorded clean checkout.

The CPU-specific image and public fixtures support only this environment and
workload. They establish no formal-world accuracy or long-duration thermal behavior.
No screening, dropped worlds, shared live processes, changed solver budgets,
result memoization or physics-component caching was implemented. Formal binding,
preregistration, OD-3 and unresolved certificate drift remain separate decisions.
