# Genesis-lite v0.4: isolated Julia performance controls, 2026-10-31

Status: local implementation and public-control report complete; measurements are DEVELOPMENT
software controls. They are not formal Genesis results, scientific validation or
certification. The runtime and deadline implementation is local to
`codex/genesis-v04-performance`; no push, merge, preregistration freeze or OD-3 run.

## Result and scope

At four workers, the package image reduced the six-campaign PySR batch from
1,124.512 s to 72.300 s; representative function precompilation reduced it to
52.474 s (**21.43 times the measured baseline throughput**). All six controlled
campaigns match on complete proposal and query/response hashes, scientific scores
and failure classifications. Each campaign still creates six independent,
outside-verified isolated proposers. The image contains compiled code, not a live
Julia runtime or fitted search state.

The original baseline actually ran **20 Julia threads and 11 GC threads**, despite
`JULIA_NUM_THREADS=1`. Explicit JuliaCall and GC settings produced **1 and 1**.
Thread correction alone increased four-worker throughput by only 2.3%; one sequential
A/B sample does not establish a robust throughput improvement. Repeated Julia
initialization and dependency loading dominate the original runtime.

The dedicated branch starts at PR #187's
`83e13ae1a344c661f8ef9e71870bc70ad00beab3` and preserves its 80 prior commits.
The original dirty checkout was retained. The existing experimental Python/Julia
environment was not modified; owner-approved PackageCompiler installation and
build dependencies live in a separate environment.

## Requested comparison

Seconds for startup/campaign columns; PSS in GiB. A/B/C/D are matched two-arm,
six-task pool controls. S8/S12 are the separate matched 24-task bounded controls,
three batches each. The last column uses the separate complete 19-arm mixture.

| Configuration | Workers | Julia startup | PySR units/campaign | PySR symbolic/campaign | Campaigns/hour | Peak RAM | VALID | Speedup | Estimated formal hours |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Original baseline (A) | 4 | 42.479† | 711.246 | 685.042 | 19.21 | 9.765 | 6/6 | 1× | 253.6 historical |
| Corrected threading (B) | 4 | 44.385† | 692.591 | 666.823 | 19.65 | 9.698 | 6/6 | 1.023× vs A | ≈247.2 model‡ |
| Julia Sysimage, packages (C) | 4 | 1.743† | 50.390 | 31.165 | 298.76 | 2.514 | 6/6 | 15.55× vs A | 37.00 |
| Julia Sysimage, functions (D) | 4 | 1.735† | 31.396 | 26.102 | 411.63 | 2.214 | 6/6 | 21.43× vs A | 30.36 |
| Optimized configuration (S8) | 8 | 1.735† | 41.924 | 34.663 | 630.61 | 3.984 | 72/72 | 1.53× vs S4 | 18.84 |
| Best safe configuration measured (S12) | 12 | 1.735† | 49.310 | 41.177 | 776.35 | 5.749 | 72/72 | 1.88× vs S4 | 15.26 |

† Separately measured one-worker JuliaCall diagnostic probe, **not concurrent
startup at the listed outer-worker count**. S8/S12 use the same function-image
probe as D. See the phase table and its authority/one-sample limits below.
A is the original runtime configuration on the instrumented branch, not a timing
run of pristine PR #187. The historical 253.6-hour value is not a measured duration.

‡ Thread-only estimate rescales historical G10 PySR arm means by their matched B/A
service ratios, retaining the other 17 historical means and perfect four-worker
packing: `(66.60 + 741.79×692.59/711.25 + 713.36×666.82/685.04) / 6` hours.
It is a model-based comparison, not a new full-mixture measurement or a confidence
claim. All other new formal estimates below use measured complete-mixture rates.

All campaign seconds are parent-observed service times; campaigns/hour uses
completed VALID records divided by whole batch elapsed time. `VALID` is a harness
status, not physical validation. RAM is sampled aggregate process-tree **PSS**,
with RSS reported separately below. Sampling gives a lower bound, not a guaranteed
maximum. Julia startup is a separately labelled diagnostic probe, not inferred
from campaign time. Formal hours are explicitly **estimates**, not measured runs.

## Measurements and reproducibility

Host: WSL2 Ubuntu 24.04, Intel Core i7-14650HX, 20 logical CPUs, 24,030 MiB available
to the VM and 8 GiB swap. Python 3.12.3, Julia 1.11.9, PySR 2.7.2, JuliaCall 0.9.36,
SymbolicRegression 2.7.2. Each manifest records CPU information, environment,
source SHA, dirty status, runtime/asset commitments and (for later runs) boot ID.
WSL restarted between some batches; zero swap-counter deltas are assessed within
each boot, never by subtracting counters from different boots.

Evidence directory on this host:
`C:/Users/dev_kaeem/.codex/forge-perf-evidence-20261031`.
Linux originals: `/root/forge-perf-evidence-20261031`.
Raw JSONL, manifests, summaries, command ledgers, logs, comparisons and the final
checksum inventory are retained there. `report-data.json` is derived by the
included `consolidate.py`; the repository comparator verifies raw JSONL hashes.

All public controls use fixed published keys from `performance_v4.py`, anonymous
presentation, the registered arm specifications and full per-world budgets. The
two-arm A/B/C/D controls have three shared public world/seed sets per arm (six
campaigns, 36 universes), four outer workers, the same pool executor and diagnostic
annotations disabled. The original A batch excludes one-time manifest preflight;
B/C/D include 1.7–2.3 s of preflight and stronger shared-depot hashing. This accounting
difference is retained; it slightly penalizes the optimized measurements.

Run from a clean native LF clone, one batch at a time, using the existing interpreter:

```bash
cd /opt/forge-perf-20261031
bash tools/genesis_performance/run_control.sh baseline --mode campaign --repeats 3 --workers 4 --out /root/new-A
bash tools/genesis_performance/run_control.sh threads --mode campaign --repeats 3 --workers 4 --out /root/new-B
bash tools/genesis_performance/run_control.sh sysimage-packages-reviewed --mode campaign --repeats 3 --workers 4 --out /root/new-C
bash tools/genesis_performance/run_control.sh sysimage-functions-reviewed --mode campaign --repeats 3 --workers 4 --out /root/new-D
bash tools/genesis_performance/run_control.sh sysimage-functions-reviewed --mode campaign --repeats 12 --workers 8 --executor bounded --deadline-seconds 3600 --out /root/new-S8
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.analyse /root/new-A /root/new-B /root/new-C /root/new-D --out /root/new-comparison.json
```

Output directories must be new. [The build and control README](../../tools/genesis_performance/README.md)
documents the separate builder, environment settings, immutable sealing and
mutation/deadline commands. Exact executed commands and native return codes are
also retained in external ledgers and [PROGRESS](../work/PROGRESS.md).

## Bottleneck and phase evidence

Single-worker public analytic-fit probe, one fresh symbolic proposer per row,
full registered search budget; seconds unless stated:

| Configuration | Total parent wall | JuliaCall initialization* | Dependency load, inclusive* | PySR fit, inclusive* | Equation conversion* | Julia / GC threads* |
|---|---:|---:|---:|---:|---:|---:|
| A: original | 132.207 | 42.479 | 122.125 | 5.466 | 0.0084 | 20 / 11 |
| B: explicit threads | 131.894 | 44.385 | 122.506 | 5.522 | 0.0085 | 1 / 1 |
| C: native package image | 11.043 | 1.743 | 1.821 | 4.876 | 0.0084 | 1 / 1 |
| D: native function image | 9.637 | 1.735 | 1.817 | 3.595 | 0.0081 | 1 / 1 |
| Native import-cache control | 12.434 | 0.957 | 3.112 | 5.475 | 0.0083 | 1 / 1 |

`*` Diagnostic labels or introspection supplied by the controlled proposer;
intervals use parent arrival clocks. One observation gives no repeat-variance
estimate. All accepted rows match the entire public Pareto equations/losses,
not merely the best equation. A generic package image took 11.384 s but failed
that comparison and is excluded. Package/function native binary bytes are the
same as the later `*-reviewed.so` assets; the latter have new complete manifests.

A separate units-aware analytic-fit control also compares the **entire Pareto
equations/losses**, so acceptance does not depend only on final refusal decisions
in campaign controls. One fresh full-budget fit per configuration at code
`129388b32936386f95a75dd01a5044e0c97663c4`: baseline 132.733 s, package image
15.358 s, function image 10.506 s; both image outputs match the baseline exactly.
These diagnostic single-fit times include manifest preflight and have no repeat
variance estimate. Commands and comparisons are in `units-pareto-commands.jsonl`
and `C-units-pareto-comparison.json` / `D-units-pareto-comparison.json`.

The baseline parent measured process creation 0.00427 s, launch-to-Python-hello
0.07108 s, outside verification 0.000406 s and teardown 0.21441 s. The Python hello
precedes Julia import and must not be called Julia startup. Its per-universe
process tree reached sampled PSS 2.484 GiB / RSS 3.647 GiB and 192 threads; waited
child CPU was 397.636 s (378.638 user + 18.998 system), 228 major and 6,651,936 minor
faults. Baseline Julia JIT-counter growth during fit was 4.525 s, versus 3.941 s
for package preloading and 2.665 s for function precompilation. Those counters do
not measure all compilation during imports and do not isolate search-only time.

The separate `JULIA_DEBUG=loading` probe identifies a concrete cause: the original
shared depot's PythonCall cache is rejected because a required Printf build ID
is missing; StructUtils and JSON caches also refer to different package source
paths than the pinned project selects. Julia then recompiles PythonCall and its
dependencies into `/tmp/jdepot`. That private cache disappears with each proposer,
so the work repeats. `loader-diagnostic.log` retains the loader messages; this is
diagnostic corroboration, not a trusted-proposer timing claim. The import-cache
control and native sysimages demonstrate the corresponding wall-time reduction.

A later diagnostic-only two-campaign function-image probe matched both baseline
tasks exactly. All 12 proposers were outside-verified; ten initialized Julia and
reported 1 Julia / 1 GC thread, the expected image and SymbolicRegression 2.7.2.
The two early-return worlds did not initialize Julia. Mean parent intervals were
0.00401 s process creation, 0.07027 s launch-to-hello, 0.00224 s outside verification
and 0.16454 s teardown. Across the ten Julia loads, initialization was
1.627 ± 0.056 s and inclusive dependency loading 1.703 ± 0.060 s. Inclusive PySR
Python import was 4.037 ± 0.199 s (including its nested imports/Julia work), fit
3.904 ± 0.327 s, and 15 observed equation-table conversions averaged 0.0601 s.
These are profiled intervals, not interchangeable with unprofiled throughput.

Trusted independent evaluation took 0.000294 s mean across the two campaigns;
v0.3 identity work took 0.01548 s mean. These particular campaigns returned
refusal/no-law answers, so `adjudicate_v3` had zero calls: its timing is **UNKNOWN**,
not zero. This does not establish the cost of law-bearing adjudication. Full
per-function counts/distributions and the ten runtime probes are retained in
`profile-summary.json`. Additional immutable runtime/depot hashing remains in
every campaign and in the reported whole-batch costs; it was not bypassed with a
digest memoization shortcut.

Parent process creation, launch-to-hello, outside verification and teardown are
measured independently. `host_start_seconds` now sums actual launch-to-hello
durations, instead of relabelling total campaign time as startup. Opt-in profiling
also records trusted evaluator, adjudication and identity work separately.

Python/Julia phase boundaries originate in the proposer. Their arrival times use
the parent's monotonic clock, but their labels remain **UNTRUSTED diagnostics**.
Inclusive import/loading/fit intervals overlap and cannot be added. Julia's
cumulative JIT counters are diagnostic only; a standalone, externally isolated
JIT duration was not established. Full parent-observed batch time is the authority
for speedup. Profiling runs are excluded from throughput comparisons.

## Immutable runtime and implementation

The selected function image is
`/opt/forge-sysimage-20261031/functions-reviewed.so`, SHA256
`dddf152e429348eb8bcc519d377e7fc8151f3f10a9a5b0b0b0458d7e77090698`.
Its manifest SHA256 is
`48fb14097fe566ea1e15c6b490f7511505e873c0d8ed72c593fab96eeb20cbb2`.
The package-only image is `packages-reviewed.so`, SHA256
`4bcbf3a5b62e7c9c66f2efa7be33f7870a4118c152cf87f474f1d9d03158f71f`,
manifest SHA256
`b9809c5a2cdaf588e908e0172bfb90d8f84ecde9fa537d0350e24d70fba8f386`.
Both use CPU target `native` and are specific to the measured environment.

PackageCompiler 2.4.4 is installed only in
`/opt/forge-sysimage-build-20261031/compiler`. Its resolved build manifest is
embedded in the sealed asset metadata. The runtime Project and Manifest remain
byte-identical to the experiment:

- Project SHA256: `82b5f5e3878bc2035aa96730adf82354a3bee1b1950299deb489b6f31310b732`.
- Manifest SHA256: `958661e2ee61f0c4a1c99e3799e4177d9db943722a96da26c3a201912525296e`.

Function tracing runs analytic synthetic arrays for ordinary and units-aware
PySR in a separate PackageCompiler subprocess, before campaign controls. No world,
root, campaign result or discovered law enters the builder. Runtime package
versions and Julia's actual selected image are probed, and parent `/proc` mappings
confirm the image is mapped. Incremental images may also map Julia's stock image.
Assets and shared depots are root-controlled and read-only; each proposer gets
its own writable `/tmp` and first depot.

Changes are confined to v0.4 runtime/telemetry, the public performance helpers and
tests/documentation. v0.2-pinned files, algorithms, serial deterministic settings,
operators, seeds, budgets, scoring and registered statistical decisions are unchanged.

| Local commit | Change |
|---|---|
| `a70b8f0f0f5dd5e9d007e8aec32496fc851aefff` | Parent instrumentation and public controls |
| `ff723f8c43fcf1bcf3fd13a4d6d529102b45a9d4` | Separate hard-budget executor |
| `ba9c9f84c8b7b27603d96286cc790b963db27b18` | Immutable runtime assets and exact traces |
| `f796744abba4a9ca1499dfbef1516cddf348da73` | Parent-death, late-result and runtime replay review fixes |
| `9d3535943851080ea8447dcc492e6f7ef9e209d5` | PID reuse protection and link adapter |
| `89ddd787db6b09b64063e9c60787a0c766a48d76` | Native images/import-cache controls; A baseline source |
| `076625030a7ccd32d9b43a38aa1b166dc3126d39` | Bind every shared depot, trusted operator phases |
| `afdd693bf6a41dcd3f3589c9288b48b8edb8fa82` | Fail-closed scientific equivalence checks |
| `97167b0453c2d8afb784b993086a6b1e0d543e2e` | Guard-sensitive development mutations; B source |
| `b4f835ff439ec0348e3eb41edb0c90883964cfe1` | Reproducible build/control and regression documentation |
| `0068bb367ce17083548402946d20601f2216722d` | Actual bounded executor scaling; legacy UNKNOWN fields; C/D source |
| `129388b32936386f95a75dd01a5044e0c97663c4` | Correct escrow/presentation ID comparison and exclude only timing fields |

Runtime identity covers Julia/Python package sources and versions, executable,
Project/Manifest, every actual shared depot entry, sysimage bytes and its sealed
build metadata. Omitting an optional cache marker cannot bypass content binding.
Identity scanning remains deliberately uncached: changing shared bytes must
change the identity. Eventual formal preregistration must bind this identity;
the current candidate remains unfrozen, with the missing binding explicit.

## Outer-worker scaling and full-grid estimate

Scaling uses the pilot's actual bounded executor (a fresh trusted worker per
campaign), with the same 24 fixed public campaigns at each worker count, repeated
three times. That is 216 campaigns / 1,296 fresh proposer instances. Each batch
has 144 distinct recorded PID/start-time pairs and passes the six-world outside
checks. PID identities are assessed within their recorded boot. All candidate
records match the S4 reference on scientific content and exact traces.

| Workers | Batch seconds, mean ± SD | VALID/h, pooled (batch SD) | Units mean / p95, s | Symbolic mean / p95, s | PSS / RSS peak, GiB | Mean child CPU cores | Speedup vs S4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4 | 209.52 ± 1.18 | 412.37 (2.33) | 35.43 / 48.82 | 29.36 / 41.97 | 2.22 / 3.48 | 4.09 | 1× |
| 8 | 137.01 ± 2.52 | 630.61 (11.51) | 41.92 / 58.56 | 34.66 / 49.79 | 3.98 / 6.81 | 7.41 | 1.53× |
| 12 | 111.29 ± 1.18 | 776.35 (8.23) | 49.31 / 71.01 | 41.18 / 60.68 | 5.75 / 10.16 | 10.99 | 1.88× |

Every worker configuration completed 72/72 VALID campaigns, with zero errors,
deadline terminations, unstarted tasks, OOM events or swap-in/out counter changes.
Twelve workers were admitted only after the measured eight-worker memory peak
left ample headroom. The maximum sampled thread counts were 36, 68 and 100. Higher
concurrency raises individual latency while improving completed throughput;
doubling four to eight workers delivered 1.53×, not 2×. The best observed count in
these repeated PySR controls is twelve. Three repeats share twelve public
world/seed clusters; they are not 36 independent world samples per arm.

The four-worker D/A throughput gain is **21.43×** on the matched six-task pool
control. The mean paired service-time ratio is 24.21×, with conditional public
world-cluster bootstrap percentile range 22.58–25.71×. These are different
statistics. C/A throughput is 15.55×; its paired service mean is 17.89× with range
16.74–18.83×. Only three public clusters underlie those intervals. No product of
the A/D and S4/S12 ratios is presented as a measured end-to-end speedup: the
fixtures, executor and batch sizes differ.

The full-mixture public control uses **all 19 registered arms**, each on the same
three public world/seed sets: 57 campaigns / 342 universes per batch. A baseline
for the other 17 arms produced 51/51 VALID; together with A's six PySR records it
provides the 57-task semantic reference. This assembled reference is used only
for equivalence, never as a fictitious simultaneous baseline throughput run.

| Image / workers | Batches | Batch seconds, mean ± SD | Mixed VALID/h | VALID | Estimated 45,600-campaign hours |
|---|---:|---:|---:|---:|---:|
| Packages / 4 | 1 | 166.493; SD UNKNOWN | 1,232.48 | 57/57 | 37.00 |
| Functions / 4 | 1 | 136.639; SD UNKNOWN | 1,501.77 | 57/57 | 30.36 |
| Functions / 8 | 1 | 84.786; SD UNKNOWN | 2,420.21 | 57/57 | 18.84 |
| Functions / 12 | 3 | 68.690 ± 0.466 | 2,987.34 | 171/171 | **15.26** |

All 342 optimized mixed records exactly match their reference tasks; no error,
deadline loss, OOM or swap-counter increase occurred. These rates include
per-campaign runtime/depot identity verification, fresh trusted-worker startup,
ledger retention, setup and short-batch tail costs. They are much higher than the
PySR-only rates because most arms are inexpensive. Do not interchange the rates.

The estimate is `19 × 2400 / 2987.34 = 15.26 hours`. Observed repeat projections
range **15.19–15.38 h**. Resampling the three public world/seed clusters 10,000 times
(seed 20261031), retaining all 19 arms together and holding measured effective
capacity fixed, gives a **conditional public-sample percentile band of
13.12–17.43 h**. It is **not a 95% confidence interval for the formal grid**. The
full-grid prediction uncertainty remains unquantified: hidden-world complexity,
formal presentation mix (these controls are anonymous only), long-run thermal/load changes and scheduler differences have
not been measured. Short-batch extrapolation also repeats preflight/tail overhead
that a longer run may amortize. No formal run was launched to reduce this uncertainty.

The three-cluster conditional bands for four/eight workers are 27.21–34.53 h and
16.16–21.71 h; their batch-to-batch variability is UNKNOWN because each full-mixture
configuration was measured once. Twelve received extra repeats after winning the
initial comparison. It is the **best observed configuration under these controls**,
also supported by the balanced three-repeat PySR scaling study, not a claim of a
globally optimal worker count. The ratio 253.6/15.26 ≈ 16.6 is a **ratio of
estimates**, not a matched measured speedup.

A separate fourth mixed twelve-worker control, excluded from configuration
selection and the three-repeat estimate, completed 57/57 VALID with exact
equivalence. An external parent measured 69.914 s whole-command wall time and
671.280 CPU s (604.570 user + 66.710 system), including the trusted driver and its
descendants: **9.60 mean CPU-core equivalents**. Linux `/proc/stat` deltas across
the VM measured **47.02% utilization of its 20 logical CPUs**, with idle/iowait
excluded from busy time and guest counters not double-counted. This is VM-wide
load, not host Windows utilization. `resource-accounting.json` retains raw
counters, command, boot ID and the complete run summary. The scaling table's
separate `RUSAGE_CHILDREN` values exclude the trusted parent and must not be
mislabelled total host utilization.

## Deadline and scientific/security regression

The hard-budget repair is separate from A/B/C/D timing. At the monotonic cutoff,
running workers are terminated; atomic ledgers retain completed races. Late
completion is labelled `DEADLINE_COMPLETED`, never counted as within-budget VALID;
killed and unstarted tasks remain accounted for. Teardown grace is reported.
Linux parent-death signalling, `unshare --kill-child`, and a surviving trusted PID
namespace init close the setuid parent-death gap. The busy/detached-child check
first verifies isolation and then confirms no surviving namespace init/proposer/child.

Each proposer still receives fresh PID/mount/IPC/network/user namespaces, a private
keyring and writable state, with hidden paths unavailable. Direct process-memory
and file-descriptor attacks are refused. The comparison admits no duplicate task,
missing trace, empty comparison or incomplete proposal/failure evidence. Six
distinct escrow IDs and six presented aliases are checked in their respective
namespaces; only random transport query IDs and timing fields are excluded from
the scientific comparison.

At code SHA `129388b32936386f95a75dd01a5044e0c97663c4`, the targeted root/Linux pack
executed **174 passed, 3 expected environment skips** in 35.68 s. The bounded
development mutation control executed **9/9 KILLED**, with native exit 1 and named
assertion failures for every mutant; exact source restoration was checked. These
are not the OD-3 certified mutation population. The separate deadline integration
probe passed with no surviving processes. Independent scientific review was
read-only/static; it is not test execution or validation.

Ordinary gates use clean native LF clones, the same existing Python 3.12.3, four
xdist workers with `--dist loadfile`, and unprivileged `dev_kaeem`. The root-only
isolation pack above supplies the privileged checks. The serial dependency guard
passed; FAST then deselects it, exactly as CI does. SCIENTIFIC uses all six CI
deselects from [TESTING](../TESTING.md). No dependencies were installed for gates.
The Julia project/executable are explicit, offline mode enabled, a separate test
depot is writable, and no sysimage is selected for these ordinary tier runs.

| Gate | Current `129388b3…` | Pristine base `83e13ae1…` | New failed nodes |
|---|---|---|---:|
| Dependency reachability, serial | 1 passed | NOT RUN | — |
| FAST | 13,772 passed / 3 failed / 184 skipped; 342.19 s | 13,728 passed / 3 failed / 184 skipped; 340.10 s | 0 |
| SCIENTIFIC | 14,356 passed / 3 failed / 185 skipped; 526.31 s | 14,312 passed / 3 failed / 185 skipped; 413.34 s | 0 |

The ordinary tiers are **not green**. The observed failure names are:

- `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`;
- `tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully`;
- `benchmarks/battery_rediscovery_v0/tests/test_battery_rediscovery_v0.py::test_mind_source_is_byte_identical_to_its_source_commit`.

The first two expose existing certificate/continuity drift; no certificate or
frozen artifact was rewritten. The third revealed that the branch-only Linux
transfer omitted a non-ancestor historical commit referenced by that test. The
original repository contains `e2b8037c881847a497c32f7ca56f82b95b493727`; the test
clones initially did not. After both complete tiers, that historical ref was
imported from the original repository's bundle into both test clones, without a
tree/source change. The affected test then passed independently on current and
base (1 passed in 0.90 s / 0.66 s). Full-tier records remain the original failing
runs; that recheck does not retroactively turn them green. The two certificate
failures remain unresolved and owner-controlled.

Both full tiers have identical current/base failed-node sets and identical
skipped-node sets: no added or removed skip IDs. This comparison is not OD-3 skip
admission. Both checkouts were clean before and after every full tier. SCIENTIFIC
wall times are test-run observations, not a performance comparison: the baseline
could reuse the ordinary test depot populated by the preceding run.

Full native commands, per-command return codes, clean-tree snapshots, JUnit files
and failure-set comparisons are retained under `gates/` in the evidence directory.
`run_gates.py` describes the exact environment. The ordinary driver completing
successfully does not change individual pytest failures into passes. All reported
code tests bind the code SHA above; the final documentation-only commit is not a
new certification result. `python docs/ai/check_docs.py` printed AI_DOCS PASS for
nine opted-in documents (metadata/local paths only); it is not a science gate.

## Failed approaches, limits and next owner-controlled steps

- A generic CPU-target package image was fast but changed the complete Pareto
  equations/losses on the public fixture. It is **rejected** and retained as failed
  evidence. Native images matched. Sharing only the selected best law would have
  concealed this regression.
- GCCBootstrap required an unavailable musl loader. The build instead uses Julia's
  bundled LLD through a link-only adapter, without a system toolchain install. The
  attempted unused dependency remains in the separate build manifest. An initial
  link failure and duplicate-verbosity function workload error were corrected and
  their logs retained.
- The native import-cache-only control also improved loading (12.43 s public fit),
  but function precompilation was faster (9.64 s); the cache-only option is not the
  selected configuration.
- Earlier review found an optional-marker depot-identity bypass, missing build
  entrypoint digest, late-completion admission and comparison evidence gaps. These
  were fixed and directly tested. The first analyzer also confused escrow IDs with
  presented aliases and compared diagnostic clocks; both caused conservative
  UNKNOWN/FAIL and were corrected before accepting comparisons.
- Some early `.exit` files used unreliable PowerShell-to-bash exit interpolation.
  They are not evidence of success. Final runs use native tool return codes or
  Python subprocess ledgers. Original failure logs remain available.
- Performance is conditional on this CPU/VM, public workload, artifact and host
  load. PSS/RSS are sampled lower bounds; a short control cannot establish long-run
  thermal stability, formal-world costs, physical validity or absence of every
  possible information leak.

Remaining owner-controlled operations are the exact final runtime binding and
preregistration freeze, full OD-3/hardened recertification on the intended final
tree, and any formal run/push/merge. Ordinary gate failures remain failures even
when reproduced on the pristine base. This report grants none of those approvals.
The live Session A queue/candidate also retains D15 crash/timeout classification,
OD-18 compute-budget approval, the control-kind margin, the owner-run D12 Codex
preregistration review and Session B rehearsal. A performance review does not
discharge that preregistration review or resolve those scientific decisions.
