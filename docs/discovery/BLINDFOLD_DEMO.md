# Blindfold public demonstration

**DEMO / NON-FORMAL / SECURITY_BOUNDARY_NOT_PROVEN**

This public-seed rehearsal executes the existing v0.3 development harness with
trusted built-ins only: careful, always_law, always_insufficient. Six synthetic
world kinds × raw (`anonymous` in source) / `paraphrased` × three arms produce
36 card executions, followed by 36 semantic replay executions. The fixed seed is
`forge-blindfold-demo-public-seed-v1-2026-10-20`; arm seed is 0. It was selected
before execution and never changed in response to outcomes.

The existing bounded escrow seals/scores proposals, then the independent v0.3
evaluator re-scores the freshly derived public fixtures. No formal admission,
registry storage, private root, sealed holdout or formal driver is used. The
preregistration builder imports formal/registry modules for code identity; that
is distinct from calling formal entrypoints or opening registry storage.

Run from the repository with its existing environment:

```sh
PYTHONPATH=src:. python tools/forge_blindfold_demo.py --output NEW_DIRECTORY --timeout 30
```

The output directory must not already exist. The timeout applies separately to
each six-card worker, is capped at 120 seconds, and is a reliability boundary,
not security isolation. No configurable seed, plugins, arbitrary callable/module,
formal tier, private input/root or registry path is accepted. The internal worker
interface also accepts only the three built-ins and two presentations.

`index.html` contains all primary card outcomes/proposals/refusals, observation
counts, evaluator agreement, replay results and provenance, with a self-contained
embedded JSON download. `records.json` contains full primary and replay records,
including failures, diagnostics and timings. Missing/incomplete results remain
UNKNOWN. INVALID_BENCHMARK remains invalid, even if some credits exist.

Semantic replay compares proposals, outcomes, credits, world identity (key/card
digests), configuration and provenance. It excludes ephemeral report digests and
timings. This is a deterministic rerun, **not cryptographic verification of an
archived record**. No lift, maturity, A2/B1 or formal discovery claim is made.
The eight writable pseudo/device mount isolation blockers remain unresolved.

## Executed result — 2026-10-20

HEAD: `1cb5e187ef46ba2735fa292112a5e2bfd2334007` plus uncommitted demo/test/docs
and preserved checkpoint-2 work. Runtime: existing Linux Python 3.12.3 venv.
Source hashes in records.json bind the executed glue and scientific dependencies;
HEAD alone does not identify the local edits. No scoring/preregistration changes.

- Targeted tests: **15 passed in 0.83 s**. Initial test attempt: 1 failed, 14 passed
  in 0.19 s because an overly broad test guard rejected identity-builder imports;
  corrected to forbid actual formal entrypoints/registry construction. Both kept.
- Actual demo: **36 primary cards + 36 replay cards**, exit 0.
- Independent evaluator agrees on **36/36** primary cards; six semantic comparisons MATCH.
- Outcomes: 19 insufficient_evidence, 3 law_pass, 2 no_law, 2 confounded, 10 law_fail.
- Primary observation calls: **660**. These are demonstration counts, not lift metrics.
- HTML structural check: 36 cards; embedded JSON equals records.json.
- Visual rendering: **NOT VERIFIED**. Browser blocked local file URL by protocol
  policy; no workaround attempted. Codex file opening was queued. Open the local
  HTML manually in a browser; the supervisor handles any approved Library upload.

Evidence, exact commands and raw outputs:
[public-demo evidence](../work/evidence/blindfold_public_demo_2026_10_20_v1/).
[HTML](../work/evidence/blindfold_public_demo_2026_10_20_v1/report/index.html) /
[JSON](../work/evidence/blindfold_public_demo_2026_10_20_v1/report/records.json).
These are repository-local files, not externally hosted download URLs.

All 4,608 tracked benchmarks/ and src/ file hashes still match HEAD; prior CP2
source/evidence hashes still match. No dependency installs, OS security changes,
CP3 implementation, commit, push, merge, freeze or recertification. Full regression
pack and changed-file gate NOT RUN; validation here is the authorized targeted
suite, actual demo, semantic replay and artifact checks.
