# Local Assurance

FORGE's authoritative hardened-core assurance runs on a controlled local
workstation, not automatically on GitHub Actions.

The purpose is not to run a lighter test set. It is to execute the same
scientific source gates locally, record their exact evidence, bind it to the
source commit, and refuse to produce `SAFE_TO_PUSH: YES` if any required fact
is missing.

## Required environment

Use a Linux environment (WSL2 is suitable) with:

- Git
- Python 3.11
- Python 3.12
- `venv` support for both interpreters
- ngspice
- the repository checked out with a clean working tree

Python 3.14 results do not substitute for the required 3.11/3.12 gates.

Local environments, receipts and evidence are written below `.forge/`, which
is ignored by Git.

## 1. Prepare the local environments

From the repository root:

```bash
python -m tools.certification.local_assurance prepare
```

If the interpreters are not discoverable as `python3.11` and `python3.12`,
pass their executable paths explicitly:

```bash
python -m tools.certification.local_assurance prepare \
  --python311 /path/to/python3.11 \
  --python312 /path/to/python3.12
```

Preparation creates isolated environments below:

```text
.forge/venvs/3.11
.forge/venvs/3.12
```

and installs `.[dev,mcp,oracles]` into both.

## 2. Run source assurance

Commit the source change first. The working tree must be clean.

Then run:

```bash
python -m tools.certification.local_assurance run
```

The runner records the exact source SHA and tree SHA before execution and
refuses if HEAD moves or the tracked tree becomes dirty.

It runs:

- FAST on Python 3.11;
- FAST on Python 3.12;
- SCIENTIFIC on Python 3.12 with ngspice;
- campaign gate;
- false-confidence regression gate;
- all four formal mutation shards;
- all eight V4 mutation shards;
- trust-hardening mutations;
- a clean-tree proof after every gate;
- an optional-provider availability probe in each FAST/SCIENTIFIC gate, and semantic
  admission of every skipped test (see "Skipped tests" below).

The official gate evidence is stored under:

```text
.forge/assurance/<SOURCE_SHA>/evidence/
```

The runner freezes every official evidence file into an SHA-256 manifest,
builds the hardened-core assurance record using the existing assurance
validator, and then writes `certification/current_core_v2.json`.

A successful source run ends with:

```text
LOCAL_ASSURANCE: SOURCE_PASS
SOURCE_SHA: <sha>
SKIP_ADMISSION: skipped <n>, accepted <n>, unexpected 0
CLAIM: CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE ...
RECEIPT_SHA256: <sha256>
READY_TO_COMMIT_CERTIFICATE: YES
SAFE_TO_PUSH: NO
```

This is intentionally **not** the final push signal.

## 3. Commit the certificate-only child

Use the reserved subject exactly:

```bash
git add certification/current_core_v2.json
git commit -m "certification: recertify hardened core"
```

Do not include another path in this commit.

## 4. Verify the certificate child

Run:

```bash
python -m tools.certification.local_assurance verify
```

This step verifies:

- exactly one parent;
- certificate-only child shape;
- every parent-bound source field;
- certified bytes and current scope;
- the local assurance schema;
- the frozen local evidence manifest and every file hash;
- the assurance record against the source tree;
- all deferred certificate/freeze self-checks;
- a clean checkout before and after verification.

Only this output authorizes a push:

```text
LOCAL_ASSURANCE: PASS
SOURCE_SHA: <sha>
CERTIFICATE_CHILD_SHA: <sha>
RECEIPT_SHA256: <sha256>
SAFE_TO_PUSH: YES
```

Any partial run, missing runtime, test failure, mutation survivor, unexpected
skip, missing evidence, modified evidence, dirty tree, changed source commit or
failed child check ends, with exit code 1 and no traceback, with:

```text
LOCAL_ASSURANCE: REFUSED
REFUSAL_KIND: EXPECTED_ASSURANCE_REFUSAL
REFUSED_BY: <LocalAssuranceError | AssuranceError | CertificationError>
<every reason>
FAILURE_RECORD: .forge/assurance/<SOURCE_SHA>/local-assurance-failure.json
FAILURE_RECORD_SHA256: <sha256>
SAFE_TO_PUSH: NO
```

(`FAILURE_RECORD` lines appear when a `run` wrote one.) A defect in the runner
itself is not a refusal and is never swallowed: it prints
`LOCAL_ASSURANCE: INTERNAL_ERROR` / `REFUSAL_KIND: UNEXPECTED_INTERNAL_ERROR`,
the full traceback and `SAFE_TO_PUSH: NO`, and exits 2. Neither path can print
`SAFE_TO_PUSH: YES`.

## Re-running a source

A previous assurance directory is never silently mixed with a new run. To
discard the prior local evidence for the same source and execute every source
gate again:

```bash
python -m tools.certification.local_assurance run --reuse
```

`--reuse` means "discard admission and re-run"; it does not reuse prior gate
results. Previous directory bytes are kept in a unique quarantine sibling, not
recursively deleted based on a caller-supplied local-root path.

## Trust model

Local assurance is strong evidence about **what ran on this controlled
workstation**. It is not independent third-party attestation.

The receipt records the source identity, runtime identities, gate durations,
evidence-manifest digest and certificate digest. For high-stakes releases,
independent reproduction can still be added as a separate scientific or
release-level assurance activity without making GitHub CI authoritative again.

## Skipped tests: semantic admission (Pass 13)

### Why the skip ceilings were invalid

Assurance schemas /5 and /6 accepted a functional suite with at most FAST 19 and
SCIENTIFIC 5 skips (dependency guard, campaign and regression 0) — the counts the
last certificate measured. A count cannot say *which* test skipped or why. It
would admit a newly skipping trust test whenever some provider test stopped
skipping, and it refused the first complete local run (source d5d886f9,
2026-10-08): every execution gate passed (FAST 3.11/3.12 9275 passed, SCIENTIFIC
9826 passed, Formal 284/284, V4 666 killed + 12 declared survivors + 2
NOT_MUTATED, trust 20/20), then `build_assurance` raised on 142 skips per suite.
The extra skips were BIG 12/13 provider and flagship tests whose external solvers
the assurance runtime does not install.

### The policy

`tools/certification/skip_admission.py` (certification control plane) holds the
committed rules and providers. Assurance /7 admits **each** observed skip, and the
authority is `unexpected == 0` in every functional suite. A skip is admitted only
when all of these hold:

1. its node id is in a rule's exact file and — unless the module's own top-level
   `pytestmark` skips every test in it on exactly that reason — among the rule's
   exact test names (no wildcard, no directory scope; a module-scoped rule is
   refused unless the file really carries that `pytestmark`);
2. JUnit records it as `pytest.skip`, raised in the test's own module;
3. its reason equals the rule's reason **rendered from the provider probe's own
   detail** (e.g. `FEniCSx: {fenicsx}; Gmsh: {gmsh}`), not from the test's words;
4. for a provider rule, at least one declared provider is `UNAVAILABLE` and none is
   `UNKNOWN` in the availability record the same gate wrote, under the same
   interpreter, immediately after its suite
   (`python -m tools.certification.skip_admission probe`);
5. the test is not a Formal TARGET, a V4 target test, a trust-mutation test, a
   certificate self-check or the dependency guard — those are refused even if a
   rule names them, and a rule naming one makes the policy invalid;
6. the suite is FAST or SCIENTIFIC. A skip in the dependency guard, campaign or
   regression suite is always unexpected.

Provider availability reuses the existing authority — `engcore.providers.default_registry()`
and the adapters' own `fenicsx_available` / `precice_available` /
`engcore.spatial.gmsh_available` — run with pytest's import roots. Every registry
answer is corroborated by an independent facet (the module spec or the executable
the adapter looks for). Only an exact registry absence reason (`python module '…'
is not installed`, `executable '…' not found`, the OpenFOAM prefix message) counts
as absent; present-but-refused, broken, timed-out, raising or disagreeing probes
are `UNKNOWN`, and `UNKNOWN` never admits.

Admitted classes:

- `OPTIONAL_PROVIDER_UNAVAILABLE` — an external solver adapter or Gmsh;
- `OPTIONAL_EXTRA_UNAVAILABLE` — a declared optional-dependency group that
  `pip install -e ".[dev,mcp,oracles]"` does not install (symbolic, mesh, benchmarks);
- `DECLARED_CONDITIONAL_SKIP` — an exact node id whose skip is a stated property of
  the tree (two reason-truth cases whose violated conditions are all
  NOT_REPAIRABLE; the exact-freeze domain-digest check, which skips only in
  DESCENDANT mode).

Anything else is `UNEXPECTED_SKIP` and refuses assurance; the failure record lists
every unexpected skip with the reason it was refused.

### What an admitted skip means — and does not

The assurance record's `skip_admission` section lists every admitted skip per
gate (node id, reason, location, classification, rule, provider statuses, gate,
interpreter), the probe facets, the inventory digest per suite, and a claim such
as `CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE`. An admitted
skip is a test that **did not execute**. Nothing bound to an unavailable provider
was tested, and **provider qualification remains a separate activity from Core
assurance**; the record never says "all providers tested". The historical counts
(19, 5, 142) are kept only as telemetry.

Revalidation: on the certificate child every stored row is re-admitted against the
committed policy, the protected tests of the tree and the statuses re-derived from
each recorded facet observation; `local_assurance verify` additionally re-derives
the whole section from the frozen JUnit and availability evidence and requires
equality. A /5 or /6 record keeps its old meaning and is revalidated against the
historical ceilings.

Pass 13 review fixes that changed tests rather than the policy: the blind-challenge
dynamic import guard now runs in a fresh interpreter (it had skipped in every gate);
the PDE contract refusals (missing boundary condition, missing coefficient, unit and
role refusals, fabricated-field refusal) now also run on a hand-built mesh, so they
no longer depend on Gmsh; the reason-truth repair test names its two skip causes
separately.


## Persistent isolated mutation workspaces (optimization passes 2–5)

Implementation status: source changes and static review only. This pass ran
zero tests, no assurance, no smoke tests and no performance measurements.
Behavior is unverified by execution. No measured speedup is claimed.

Repeated full-tree population is replaced with one private pristine seed and
one independent mutable worker per shard process. This is expected to reduce
repeated filesystem I/O, especially redundant file creation and copying. Full
SHA-256 scans remain deliberate; hashing and ownership overhead still require
measurement before any performance conclusion.

V4 retains its exact COPY_TREES/COPY_FILES/COPY_GLOBS selection, including .git.
Formal retains its broader _COPIED selection. Population definitions, shard
identities, expectations, JUnit named-test attribution, mutation token/parse
checks and Formal guard mechanisms stay unchanged. Formal control remains
first; V4 control remains last. This changes how the same required evidence is
produced, not the evidence bar.

Each shard's lifecycle is:

1. Create storage outside the source checkout, populate its private seed and
   copy independent worker files. No hardlinks are created. Never execute tests
   in the seed. Remove seed write permissions after worker initialization; this
   limits accidental writes but is not an operating-system sandbox.
2. Build one immutable in-memory index of metadata and digests over relative
   paths, types, sizes, SHA-256 values, modes and link counts. Stream file contents
   in 1 MiB chunks; retain no byte cache. The seed filesystem supplies restoration. Empty directories and the entire copied .git are covered. Existing
   runner exclusions during population are unchanged; nothing else is silently
   dropped from the baseline.
3. Verify complete seed metadata and file SHA-256 against the immutable index,
   and SHA-256 every worker file before an attempt. Apply only the declared edit
   to an independent regular worker file. Traversal and linked targets are refused.
4. Execute the existing target command in the worker. Linux child-subreaper ownership adopts orphaned/detached descendants.
   The shard must be the Linux main thread, have exactly one kernel thread,
   default/unblocked SIGCHLD, no prior subreaper role and no unrelated children. Kernel child enumeration and reaping
   must confirm drain before restoration; unsupported/ambiguous ownership refuses.
5. Collect intended paths and independently walk all worker metadata. Repair
   only dirty entries from the seed after a full seed check. Stream and hash each
   restored file against its indexed digest, remove unexpected or replaced entries
   without following ancestor links, and restore modes. SHA-256 every worker file. Unrelated same-size corruption receives
   one additional sparse repair followed by complete verification. A mismatch or repair failure invalidates
   the round; it cannot become KILLED/SURVIVED or permit another mutation.
6. Release owned storage after normal or refused attempts. If target lifetime
   cannot be proven drained, poison the round, skip restoration and retain the
   isolated workspace for diagnosis. The local parent respects retained storage.
   A cleanup failure also invalidates the round. Hard termination can leave
   isolated scratch behind; it cannot authorize continuing a prior run.

Pristine verification proves equality of the specified bytes, topology and
modes at the boundary. It does not prove physical truth or protect against
arbitrary malicious processes outside the controlled workstation trust model.
Unsupported seed symlinks/special files and external Git storage pointers are
refused. Worker-created links are detected and removed without writing through
linked targets. JUnit and pytest basetemp remain outside the worker manifest;
linked artifact paths are refused and old mutation JUnit reports are removed
before execution so a previous invocation cannot supply a verdict.

Each concurrent shard owns its seed, worker, manifest and telemetry object.
The existing --mutation-workers default remains 2. No shared seed, mutable
workspace or cross-run cache is introduced. A bounded Pass 10 measurement at
1 / 2 / 4 workers (see `docs/work/PROGRESS.md`) gave identical verdicts at every
count; 4 workers ran the Formal group in one wave with ~3.1 GB peak RSS, so
`--mutation-workers 4` is the recommended invocation. Resume and partial gate/evidence reuse
remain disabled: --reuse still means discard the run and start over.

## Non-authoritative performance diagnostics

Each execution writes forge.local_assurance_performance/1 with:

- certification_authority: false;
- safe_to_push_authority: false;
- cumulative seconds and sample counts for seed population, seed indexing, worker
  initialization, mutation application, test subprocess, descendant drain, delta
  detection, restore, cryptographic verification, seed identity verification,
  control, shard total and gate total;
- counters for seed/worker bytes read, seed/worker files hashed, entries/files
  structurally scanned, restoration bytes/files, Git bytes/files processed and
  workers retained for uncertain ownership. No byte cache exists; cache bytes
  served are always zero. Counters never drive control flow;
- lifecycle events and failures with shard, mutation ID, stage, category, safe
  relative path where available, retention state and descendant quiescence.
  An earlier failure preserves its context at that instant; later drain/cleanup
  events report the subsequent state.

Standalone shards write scratch/performance.json outside seed and worker using
exclusive temporary files and atomic replacement, with bound parent identity.
Targets use only freshly owned artifacts inside workspace home; caller scratch
basetemp/JUnit contents are never cleared. Abnormal parent/shard paths retain
the entire scratch parent regardless of visible workspace names.
Local Assurance archives shard telemetry and separate gate timing records under
.forge/assurance/<SOURCE_SHA>/performance/, a sibling of official evidence.
The official evidence manifest scans only evidence/. Neither telemetry contents
nor timing values enter certificate evidence, gate admission, mutation verdicts
or SAFE_TO_PUSH decisions. The imported telemetry implementation itself remains
registered in certification_control like other executable runner dependencies.
Clock/storage failures in diagnostic collection are best-effort and cannot
change a gate verdict. No real timing artifact was produced during this pass.

The historical Pass 3 cost model and its Pass 4 supersession are recorded in
`docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_3.md`. The current bounded-memory,
Git environment and ownership contract is in
`docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_4.md`. Pass 5 adds the exact
controlled-input boundary, cleanup ownership, Git input classification and copy/
scan distinction in `docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_5.md`. These
controls do not enforce OS isolation against arbitrary same-UID target code. Full worker hashing remains
necessary because matching size/mode/mtime cannot establish byte identity. V4
.git remains independently copied: same-UID read-only permissions cannot seal a
shared object store against a target that changes permissions.

The adversarial specifications and bounded integration checks were executed in
Pass 8 (see `docs/work/PROGRESS.md`). Do not relax full-manifest checks merely to
gain speed.


### Pass 6 integration boundaries

Prepare, run and verify hold one nonblocking repository lock under `.forge/locks`.
Concurrent invocation is refused even with a different local root. Production
manifest admission requires exactly canonical official evidence filenames, safe
regular independent files and source/tree identity; diagnostics are siblings outside
`evidence/`. JSON receipts/manifests/failure records use atomic replacement.
`--reuse` quarantines prior data and reruns all gates; resume remains disabled.
See `docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_6.md` for the static integration
audit and unresolved runtime checks. No runtime validation was authorized for Pass 6.


### Pass 7 fresh-process startup policy

Every mutation/control still starts a fresh pytest interpreter. Mutation children
force `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONDONTWRITEBYTECODE=1`; builtin
plugins and repository conftest/fixtures remain enabled. Inherited Python startup
switches are stripped. Both copy scopes exclude bytecode; no shared pycache is used.
Each shard captures an immutable environment and interpreter path/metadata identity;
each attempt checks identity and creates its own sealed child environment.
Installed toolchain/dependencies remain controlled inputs. Exact V4 nodeids/JUnit
and broad Formal attribution remain. See the Pass 7 static cost model. Runtime
compatibility was validated in Pass 8 (bounded probes and micro-runs, not
certification evidence).


### Pass 9 verification cost

Every full seed/worker SHA-256 pass is retained, including the attempt-start
checks that refuse tampering before execution. `snapshot()` builds relative names
from directory entries instead of per-entry pathlib work; its manifest, digest,
counters and errors are identical. See
`docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_9.md` for the transition model.


### Pass 12 Formal pytest-xdist (opt-in)

`local_assurance run --formal-pytest-workers N` (default 1) runs Formal attempts with
pytest-xdist inside each attempt. It is distinct from `--workers` (ordinary suite workers)
and `--mutation-workers` (concurrent shards); V4 never uses it. With the default the
Formal shard command and transcript are the historical ones.

Plugin policy amendment to Pass 7: entry-point autoload stays disabled for every child.
Formal attempts with N > 1 explicitly load exactly `xdist.plugin` and
`tools.certification.formal_xdist_guard`, with `--tx N*popen//python=<shard interpreter>
-X utf8 --dist loadfile --max-worker-restart=0`, so every worker is the shard's own
interpreter in UTF-8 mode like the serial process, without a new PYTHON* variable.

Crash semantics: under xdist a crashed worker becomes exit 1 plus a synthetic
`FAILED <nodeid>`, which the verdict rule would credit. The guard records xdist's
structured controller signals (worker ready/down with or without error, synthetic crash
reports, internal errors, per-worker collections, per-process interpreter, UTF-8 mode and
import origins) into a sentinel outside the worker tree. An xdist attempt is admissible
only with a complete, clean sentinel; anything else raises WorkspaceError: an
infrastructure failure, never a kill. The 0/1/2 exit-code rule still applies first.

Grouping semantics: `--dist loadfile` assigns files to workers by timing, so a green xdist
control proves only its own grouping. Therefore, in xdist mode:

- a per-shard named-alone control collects TARGETS serially on the unmutated copy, selects
  every test function whose name carries each named guard (the verdict rule's own match),
  and runs EACH guard's set alone, serially, with no cache; every set must pass and the copy
  must stay pristine between sets, otherwise the round is void;
- a would-be named kill is credited only if that exact set, run with the identical command
  in the mutated worker (still byte-identical to the pristine tree plus the exact post-edit
  bytes of the declared file), fails with the named guard; otherwise the transcript says
  `RED (NOT CONFIRMED SERIALLY)` and there is no credit;
- import-refusal mutations, credited on refusal text anywhere in the output, run serially
  exactly as before, against the historical serial control, which runs in any shard that
  contains one.

Mutations of `tools/` are refused in xdist mode because the guard is imported from the
verified worker copy. See `docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_12.md`.
