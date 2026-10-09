# Forge project review — 2026-10-05

## A. Scope

Baseline: `main`, `a3f757eb5fdb` (BIG 13 merge). The existing uncommitted
`ACTIVE_PLAN.md` edit was preserved. This is a broad repository review, not a
claim that every line or numerical model has received an exhaustive audit.

Reviewed strategic/current plans, architecture and Core policies; inspected
provider discovery/identity/process handling, units, system runtime preflight,
assessment/replay, engineering references/bundles, related tests, packaging and
the Tests workflow. Executed architecture/regression, FAST, SCIENTIFIC and
focused tests. Production code and frozen artifacts were not changed.

Independent Forge scientific reviewer inspected supplied literal excerpts of
bundle export and reference-ID validation only. Its verdict was CHANGES
REQUIRED for the export path issue; it did not independently inspect the whole
project or execute tests. The other findings are the primary reviewer's work.

## B. Authority boundary

The implemented layer map separates scientific authority from MCP transport.
The changed-file gate's architecture tests passed. Provider capability is
explicitly descriptive, and process completion is distinguished from scientific
success. Identity handling still has the two defects described below.

## C. Applicability and model use

Preflight explicitly rejects missing providers, mismatched versions, unknown
materials and incompatible units. Applicability waivers are identified as caller
statements. This inspection does not establish correctness of every adapter's
applicability model. The current plan correctly retains insufficient evidence
for all four flagships and records unmet criteria.

## D. Verification / validation

Execution, replay, solver comparison and validation are distinguished in the
reviewed APIs. Neither the test counts below nor this review validates a physical
model. Full merged-tree assurance remains unestablished. Current local failures
require classification before recertification, rather than edits to pinned
certificates to make tests pass.

## E. Uncertainty

UNKNOWN uncertainty is explicitly carried through runtime and engineering
summaries. No quantified flagship uncertainty or model discrepancy was established
by this review. Unit-registry execution/replay binding remains an explicit BIG 14
follow-up; the reviewed runtime/provider/replay paths did not cite the units
registry fingerprint. This is recorded debt, not a newly proved counterexample.

## F. Evidence / context / policy

Bundle documentation correctly limits its guarantee to consistency and explains
that the manifest is unkeyed. Bundles must not be advertised as authenticated.
Existing claim replay tests passed in isolation. Broader context binding and
evidence admission were exercised by the fixed regression pack, but a passing
sentinel pack does not prove the entire authority graph safe.

## G. Provenance / replay

Provider execution identity includes problem/configuration/input content,
provider information, requested outputs and scenario state. The discovery
defects below weaken its provider-content guarantee. Run comparison also accepts
nonfinite tolerances. Export paths need containment independently of scientific
assurance semantics.

## H. Adversarial test coverage and executed checks

Environment: Windows, Python 3.14.2. CI declares Python 3.11/3.12. The root
`python` command is a Windows Store alias; commands below used `py -3.14`.
Missing MCP, meshio, provider-adapter and flagship installations affect this
local environment. This is not a supported-environment CI reproduction.

| Check | Observed result |
|---|---|
| `py -3.14 tools/forge_check.py --changed` | 40 passed |
| Regression, with explicit writable pytest basetemp | 225 passed |
| FAST, explicit basetemp, four workers | 8640 passed, 33 failed, 88 skipped, 20 collection errors; exit 1 |
| SCIENTIFIC, explicit basetemp, four workers | 9196 passed, 33 failed, 88 skipped, 20 collection errors; exit 1 |
| Engineering/provider boundary/review-fix tests | 52 passed, 1 skipped |
| Claim impact/replay tests, isolated after cleanup | 24 passed |
| `git diff --check` | Exit 0 |

FAST and SCIENTIFIC overlapped. Their results are diagnostic observations, not
isolated clean-source acceptance baselines. SCIENTIFIC regenerated 17 tracked
benchmark JSON files; the generated versions were preserved under the local
review evidence directory, then restored to their initial Git state. The
initial plan edit was retained. Three claim replay failures in the broad runs
did not recur in the isolated run; changing source fingerprints during the
overlap is consistent with the reported runtime/source identity differences.

Failure groups:

- Missing separately installed adapter/flagship packages and MCP produced
  collection errors and several runtime failures. Missing meshio affected
  spatial tests. These local dependency failures are not solver defects.
- Freeze/certificate tests reported dirty-tree, API surface and certificate
  differences. Dirty-tree failure is expected for this checkout; the remaining
  differences need a clean supported-environment diagnosis and recertification.
- Schema-reader, freeze-policy package inventory and domain/documentation guards
  failed. Their exact names and diagnostics are in the saved logs. Some nested
  record readers intentionally omit schemas, so the schema guard's result needs
  review before being classified as twelve independent defects.

Exact commands/failure names are appended to PROGRESS. Local evidence:
`.pytest-review-temp/full-project-logs-20261005/{fast,scientific,regression}.log`.
External providers, mutations, hardened recertification, remote CI and GitHub
branch protection were NOT RUN / NOT inspected in this review.

## I. Findings

### R1 — HIGH / P1: Bundle export can overwrite files outside its directory

Location: `src/engcore/engineering/bundle.py:112-123`;
`ReferenceRecord.__post_init__`, `reference.py:140-143`.

Reference IDs are only stripped/nonempty-checked before becoming output paths.
Artifact names reject `/` and a leading `.`, but accept Windows drive paths and
backslashes. Counterexample: a valid reference changed to
`reference_id='..\\..\\outside'` actually wrote `outside.json` beside the bundle
in a disposable temporary directory using the existing run/summary fixtures.
The artifact guard also accepts `C:\outside.bin`, which Windows path joining
resolves as that absolute destination (its receipt must first be admitted).

Correction: reject both separators, traversal, drive/UNC/absolute paths in
names; resolve and check containment for every destination before writing.
Account for existing symlinks/reparse points too. Add export traversal tests.
The independent reviewer agreed with this finding.

### R2 — HIGH / P1: A failed version probe can mint an available identity

Location: `src/engcore/providers/catalog.py:225-227`, `executable_probe`.

Discovery parses stdout/stderr without checking `returncode`. A mocked process
returning exit code 7 and printable version 1.2 produced AVAILABLE, and
`ProviderExecutionIdentity.from_content` accepted it and generated a digest.
The registry can cache this available status. A failure banner with a version
is sufficient; successful identity establishment never occurred.

Correction: refuse nonzero exit before parsing or publishing version/digests;
retain diagnostics. Keep timeout/exception refusal. Test failure text containing
a valid version and registry caching. This confirms debt already named in BIG 14.

### R3 — HIGH / P1: Library identity hashes metadata without checking solver bytes

Location: `src/engcore/providers/catalog.py:116-123`, `distribution_digest`,
and its consumption by `python_package_probe`.

The digest hashes RECORD text; if absent, it hashes names or name/version. It
does not verify the installed files against RECORD. Editing a provider module
or binary while preserving metadata leaves identity unchanged; editable
distributions can be particularly exposed. A disposable synthetic distribution
with unchanged RECORD and changed solver bytes reproduced equal digests.
The environment digest also hashes distribution names/versions, so it does
not restore the missing content check.

Correction: verify relevant installed content against recorded hashes and
refuse mismatches; bind verified content, including editable source and relevant
dependencies. Explicitly distinguish release-manifest identity from measured
installed-content identity. Test modified code and binaries with stable metadata.

### R4 — MEDIUM / P2: Infinite replay tolerance accepts arbitrary drift

Location: `src/engcore/system_runtime/replay.py:59-63`, `compare_runs`.

Only negative tolerances are rejected. `rel_tol=float('inf')` is accepted.
A minimal in-memory fixture comparing 1 meter with 1,000,000 meters returned
`numerical_reproducibility=True`. NaN tolerances are accepted too, although
their comparison generally fails rather than raising assurance.

Correction: require finite, nonnegative numeric tolerances and reject booleans;
add NaN/positive-infinity/negative-infinity regression cases. No scientific
validation verdict is granted by this API, so the consequence is a false
reproducibility report rather than direct physical validation.

### R5 — HIGH / P1: Default CI collection lacks separately packaged adapters

Location: `.github/workflows/tests.yml:101-111,142-156`; provider and flagship
test module imports; root `pyproject.toml` test/dependency configuration.

The workflow installs only `.[dev,mcp,oracles]`, then invokes pytest without
restricting collection. Provider and flagship tests are collected from the
repository but import `forge_calculix`, `forge_fenicsx`, `forge_flagships`, etc.
Those are separate distributions, absent from the root installation extras and
test search paths. Local full-tier collection reproduced those import errors.
Examples are `providers/calculix/tests/test_calculix_provider.py:20` and
`flagships/tests/test_flagship_ladders.py:14-16`.

Correction: declare and install the lightweight adapter/flagship distributions
needed for default collection; run provider suites in their declared backend
environments. Alternatively explicitly separate collection into root and
provider jobs while preserving required coverage and refusal tests. Do not
silently skip scientific obligations to obtain a passing gate. Impact on the
remote workflow is inferred from its configuration; remote CI was not read.

## J. Verdict

CHANGES REQUIRED

Prioritize export containment, trustworthy provider identity and a reproducible
CI/package setup. Then diagnose the clean supported-environment baseline,
complete the missing BIG 12/13 reviews and BIG 14 assurance campaign. The
current architecture supports substantial integration breadth, but this review
does not establish validated flagship capability or release readiness.
