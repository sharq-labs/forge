# Persistent mutation workspace static review - 2026-10-07

Base: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Scope is the uncommitted
optimization pass 2 implementation. No code/test execution, assurance or
performance measurement occurred. TESTS_RUN: 0.

A. Scope: workspace/telemetry utilities, V4 and Formal adaptations, Local
Assurance parent cleanup/telemetry, control-plane registration and proposed tests.

B. Authority boundary: storage/lifecycle errors invalidate rounds; performance
metadata denies certification and SAFE_TO_PUSH authority and is outside evidence.

C. Applicability/model use: scientific/domain implementation is unchanged.

D. Verification/validation: mutation attribution stays verification evidence.
No physical validation claim, speedup claim or executed-test result is made.

E. Uncertainty: no uncertainty or discrepancy behavior changes.

F. Evidence/context/policy: selection populations, expected verdicts, JUnit
rules, Formal guard attribution, deterministic shard IDs and control ordering
remain unchanged by source inspection. Failed restoration cannot return a verdict.

G. Provenance/replay: complete deterministic manifests cover copied bytes,
entry topology, modes, link counts and V4 .git. No hardlink or cross-run cache is
used. Resume remains absent. Unsupported linked/external Git storage/configuration
is refused; the pristine seed is never a target execution directory.

H. Adversarial specifications: new tests describe contamination, restoration,
seed independence, cleanup, paths/links, distinct shard workspaces, unchanged
transcript contracts, diagnostic separation, descendant drain and retained
storage. All are NOT RUN, including future real subprocess specifications.

I. Findings and disposition: initial independent reviewer found P1 - process
group signaling plus leader wait did not prove descendant drain; detached
children could survive and contaminate reuse. Replaced with Linux subreaper
adoption, exclusive per-shard target ownership, kernel child enumeration and
confirmed reaping. Failed drain poisons the round and retains owned external
storage. Parent cleanup respects retention and refuses apparent success with
unreleased workspaces. Independent re-review found no remaining actionable
findings under the dedicated sequential Linux shard-process contract. Builder
also checked external Git configuration cannot redirect a worker to source.

J. Verdict: independent source-only review returned PASS. This is a review
result, not executed verification. Implementation remains unverified by execution.

Remaining risks: Linux /proc and child-subreaper behavior must be exercised in
the supported environments later. A dedicated shard must not launch unrelated
children during ownership. Hard termination may leave external scratch behind.
Full SHA-256 scanning can still dominate I/O; expected copying savings have not
been measured. Arbitrary malicious processes are outside the controlled local
workstation trust model; this storage lifecycle is not a security sandbox.

Next: another static optimization pass on restore/hash overhead and failure
telemetry completeness. Execution and benchmarking require separate explicit
user authorization; do not auto-run tests or full assurance.


# Optimization pass 3 — independent final static review

## A. Scope
Independent read-only reviewer inspected the complete pending implementation,
runner/orchestration adaptations, control registration, documents and proposed
tests. No project execution, imports, tests, compilation or measurements.

## B. Authority boundary
Diagnostics deny certification and SAFE_TO_PUSH authority. Restoration,
ownership and cleanup failures refuse results or reuse.

## C. Applicability and model use
No scientific/domain model or applicability changes.

## D. Verification / validation
Mutation attribution remains verification evidence. Review does not establish
scientific validation or a measured speedup.

## E. Uncertainty
No uncertainty or discrepancy behavior changed.

## F. Evidence / context / policy
Populations, expectations, attribution, shard identities, default worker count
and control ordering remain preserved by static inspection.

## G. Provenance / replay
Immutable index bytes and entries support sparse repair. Full worker SHA catches
same-size corruption; complete seed bytes remain checked. Component inspection
prevents repair through substituted ancestor links. Drain covers interrupted
subprocess construction; unproven ownership retains storage.

## H. Adversarial test coverage
Specifications cover mixed-case Git config, immutable indexing, sparse repair,
hidden corruption, ancestor links, invalid hints, lifecycle failures, descendant
drain and retention. All tests NOT RUN.

## I. Findings
P1, PersistentWorkspace.__enter__: case-sensitive ConfigParser section admission
missed Git [Core] worktree=/external/source. Corrected by casefolding every section
before worktree refusal; uppercase/mixed-case specs added. Reviewer reinspection
explicitly resolved the finding. Obsolete copy2 fault injection specifications
now inject _restore_file failures.

No remaining actionable finding within documented dedicated Linux shard-process
assumptions. Memory cost and OS compatibility remain unmeasured and unverified
by execution. Builder inspection also corrected ancestor symlink chmod and
invalid-hint poisoning before final reviewer reinspection.

## J. Verdict
PASS

This is an independent static review result only, not executed tests or scientific
validation. TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.


# Optimization pass 4 — accumulated Pass 2–4 final static review

## A. Scope
Independent read-only review of accumulated helpers, runners, orchestration,
control registration, documentation and proposed tests. No project execution.

## B. Authority boundary
Performance/failure telemetry remains outside evidence and denies certification
and SAFE_TO_PUSH authority. Counters never determine gate control flow.

## C. Applicability and model use
No scientific/domain model changes. Provider/solver configuration retains the
documented trusted-toolchain contract.

## D. Verification / validation
Mutation attribution retains verification scope. No validation, executed
verification or measured speedup established by this review.

## E. Uncertainty
No uncertainty or discrepancy behavior changed.

## F. Evidence / context / policy
Population definitions, verdict expectations, attribution, controls, default
worker count and disabled resume remain preserved by static inspection.

## G. Provenance / replay
Index retains metadata/digests without pristine content bytes. Complete seed
checks precede restoration; streamed seed restoration checks metadata and digest.
Full worker hashing remains. Git stays independently copied and inherited
redirects are neutralized. Dedicated ownership checks and descendant drain gate
repair; uncertainty retains storage.

## H. Adversarial test coverage
Specifications cover seed contamination, bounded storage, Git config/environment
refusal, process ambiguity, descendants, descriptors, runtime retention and
diagnostic failures. All tests NOT RUN.

## I. Findings
P1, _check_git_seed: ConfigParser admitted Git trailing-whitespace sections
([core ], [extensions ]) and deprecated dotted subsection names ([filter.driver],
[diff.driver]) that bypassed exact/prefix checks. Corrected by conservative canonical
section grammar admission; unfamiliar forms refuse. Refusal specs added. Reviewer
reinspection explicitly resolved the finding. Prior mixed-case Core finding and
stale restoration fault-injection specifications remain corrected.

No remaining actionable finding within the documented dedicated Linux process
and controlled-toolchain assumptions. OS lifecycle, compatibility and memory/
runtime performance remain unverified by execution.

## J. Verdict
PASS

Review result only. TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.


# Optimization pass 5 — fresh independent final static review

## A. Scope
Fresh read-only review of accumulated Pass 2–5 implementation, integration,
telemetry, test specifications, registration and Pass 5 contract. No imports,
execution, compilation, tests or assurance.

## B. Authority boundary
Diagnostics have no verdict/restore/gate/manifest/SAFE_TO_PUSH authority. Helper
source remains certificate-bound. Controlled mutation/passive input isolation
is implemented; arbitrary target filesystem access is not restricted by the OS.

## C. Applicability and model use
No scientific/domain/model applicability changes. Controlled interpreter,
toolchain and non-malicious target assumptions are explicit.

## D. Verification / validation
Review is neither executed verification nor scientific validation. Specs NOT RUN.

## E. Uncertainty
No uncertainty defaults changed; Linux behavior, compatibility and performance
remain unmeasured.

## F. Evidence / context / policy
Distinct shard paths/names, duplicate rejection and completion barriers prevent
demonstrated controlled-path collisions. Required failure blocks SOURCE_PASS.

## G. Provenance / replay
No resume/cache admission. Complete seed/worker identity remains required.
Git closure remains copied for historical/pinned/ancestor reads in V4.

## H. Adversarial test coverage
Specs cover seed/hidden contamination, links, sparse repair, root substitution,
unowned basetemp, diagnostic links, partial clones/promisors, Git environment,
reapers/descendants, abnormal retention, duplicate shards and quarantine.
All tests NOT RUN.

## I. Findings
Resolved P1 controlled paths: Formal arbitrary destination deletion; caller
basetemp clearing; linked diagnostics writes; promisor lazy fetching; mixed-case
format check; host default attributes/ignore; late numeric PGID signaling;
abnormal scratch deletion; reaper-state changes; duplicate shard names.

BLOCKER, run_captured, literal target isolation: a target can open a real checkout
or another shard absolute path, or supply explicit Git -C/--git-dir/configuration
overrides. Environment sealing, modes and ownership tokens cannot deny this.
Smallest counterexample: Python open(absolute_checkout_path, "wb"). Minimal
resolution: user acceptance of controlled-runtime contract or separate OS-enforced
boundary. Documentation cannot turn this demonstrated capability into PASS.

P2 cost precision: Formal _COPIED excludes .git, so Formal Git copies=0 and G=0;
V4 Git copies=2. Builder corrected the tables and all five scan descriptions.

## J. Verdict
BLOCKER

No additional demonstrated production defect within the controlled-input contract.
Contract clarification pending. TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No unqualified readiness claim.


# Pass 5 final disposition after explicit user scope decision

## A. Scope
Fresh final static disposition under the user-selected "Controlled targets and
toolchain; seal inherited inputs and runner-owned paths" contract.

## B. Authority boundary
Telemetry data grants no restore/verdict/gate/certificate/SAFE_TO_PUSH authority;
helper source remains certificate-bound.

## C. Applicability and model use
No scientific/domain/solver/applicability changes.

## D. Verification / validation
No project execution/imports/compilation/tests/assurance. Static review only.

## E. Uncertainty
No scientific uncertainty changes. Linux/toolchain/no-external-writer/reaper
assumptions remain explicit and execution remains unverified.

## F. Evidence / context / policy
Shard-specific storage/evidence, duplicate refusal and completion barrier preserve
controlled-path separation; required failure blocks SOURCE_PASS.

## G. Provenance / replay
Complete identity, no resume/cache, no parent Git dependency; V4 closure copied.

## H. Adversarial test coverage
All specs reviewed statically, NOT RUN.

## I. Findings
All demonstrated controlled-path defects corrected. Cost P2 corrected: V4 Git
copies=2, Formal G=0. Prior literal OS-isolation blocker resolved by the user's
explicit scope acceptance, not OS enforcement. Arbitrary same-UID absolute access
and explicit target overrides remain possible outside that accepted contract.
No demonstrated defect remains within the accepted controlled-input/owned-path
contract. This review does not certify an OS sandbox.

## J. Verdict
PASS

TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
